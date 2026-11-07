"""hermes CLI: check / backlog / validate / plan / run / new"""
from __future__ import annotations

import argparse
import sys

from .agents import load_org
from .backlog import TicketError, find_ticket, load_tickets, new_ticket
from .daemon import Daemon, DaemonConfig, load_state
from .llm import check_endpoint
from .pipeline import Pipeline
from .settings import Settings


def cmd_check(_: argparse.Namespace) -> int:
    s = Settings.from_env()
    print(f"provider={s.provider} model={s.model} base_url={s.base_url}")
    info = check_endpoint(s)
    if not info["ok"]:
        print(f"✗ endpoint unreachable: {info['url']} ({info['error']})")
        return 1
    print(f"✓ endpoint ok: {info['url']}")
    if info["models"]:
        print("  models: " + ", ".join(info["models"][:20]))
    if not info.get("model_available", True):
        print(f"✗ model '{s.model}' not found on endpoint (ollama pull {s.model})")
        return 1
    try:
        load_org()
        print("✓ config/org.yaml ok")
        tickets = load_tickets()
        print(f"✓ backlog ok ({len(tickets)} tickets)")
    except (TicketError, ValueError) as exc:
        print(f"✗ {exc}")
        return 1
    return 0


def cmd_backlog(args: argparse.Namespace) -> int:
    tickets = load_tickets()
    if args.status:
        tickets = [t for t in tickets if t.status == args.status]
    print(f"{'ID':<8} {'PRI':<4} {'STATUS':<12} {'AREA':<10} TITLE")
    for t in sorted(tickets, key=lambda t: (t.priority, t.id)):
        print(f"{t.id:<8} {t.priority:<4} {t.status:<12} {t.area:<10} {t.title}")
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    try:
        load_org()
        tickets = load_tickets()
    except (TicketError, ValueError) as exc:
        print(f"✗ {exc}")
        return 1
    print(f"✓ org.yaml and {len(tickets)} tickets are valid")
    return 0


def _stages(arg: str | None) -> list[str] | None:
    return [s.strip() for s in arg.split(",") if s.strip()] if arg else None


def cmd_plan(args: argparse.Namespace) -> int:
    ticket = find_ticket(args.ticket)
    pipe = Pipeline(ticket, stages=_stages(args.stages), max_iterations=args.max_iter)
    print(f"# {ticket.id} {ticket.title}  [{ticket.priority} / {ticket.status}]")
    for i, step in enumerate(pipe.plan(), start=1):
        print(f"{i}. {step['stage']:<12} {step['role']:<28} → {step['output']}")
        if step["tools"]:
            print(f"   tools: {', '.join(step['tools'])}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    ticket = find_ticket(args.ticket)
    settings = Settings.from_env()
    info = check_endpoint(settings)
    if not info["ok"]:
        print(f"✗ LLM endpoint unreachable: {info['url']} ({info['error']})")
        return 1
    pipe = Pipeline(ticket, settings=settings, stages=_stages(args.stages), max_iterations=args.max_iter)
    try:
        result = pipe.run(create_branch=not args.no_branch, commit=args.commit)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    verdict = "PASS" if result.passed else "FAIL" if result.passed is False else "N/A"
    print(f"\n=== {ticket.id} finished: verdict={verdict} iterations={result.iterations} ===")
    print(f"artifacts: {pipe.workspace}")
    return 0 if result.passed is not False else 2


def cmd_approve(args: argparse.Namespace) -> int:
    ticket = find_ticket(args.ticket)
    if ticket.status != "proposed":
        print(f"✗ {ticket.id} is '{ticket.status}', not 'proposed'")
        return 1
    ticket.set_status("todo")
    print(f"✓ {ticket.id} approved → todo ({ticket.path.name})")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from .discover import run_discover  # noqa: WPS433

    settings = Settings.from_env()
    info = check_endpoint(settings)
    if not info["ok"]:
        print(f"✗ LLM endpoint unreachable: {info['url']} ({info['error']})")
        return 1
    created = run_discover(settings, max_proposals=args.max)
    print(f"\n{len(created)} proposal(s) written. Review and approve with: hermes approve <ID>")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    """사람이 확인해야 할 것: 승인 대기 제안, 리뷰 대기 브랜치, 막힌 티켓."""
    tickets = load_tickets()
    state = load_state().get("tickets", {})
    proposed = [t for t in tickets if t.status == "proposed"]
    review = {tid: e for tid, e in state.items() if e.get("status") == "review"}
    blocked = {tid: e for tid, e in state.items() if e.get("status") == "blocked"}
    todo = [t for t in tickets if t.status == "todo" and t.id not in state]

    print(f"승인 대기 (proposed): {len(proposed)}")
    for t in proposed:
        print(f"  {t.id} [{t.priority}] {t.title}   → hermes approve {t.id}")
    print(f"리뷰 대기 (QA PASS, 머지 필요): {len(review)}")
    for tid, e in review.items():
        print(f"  {tid} on {e.get('branch')}  iterations={e.get('iterations')}  → git diff main..{e.get('branch')}")
    print(f"막힘 (QA FAIL/오류, 사람 판단 필요): {len(blocked)}")
    for tid, e in blocked.items():
        print(f"  {tid} on {e.get('branch')}  verdict={e.get('verdict')}  {e.get('error', '')}")
    print(f"대기 중 (todo, 데몬이 처리 예정): {len(todo)}")
    for t in todo:
        print(f"  {t.id} [{t.priority}] {t.title}")
    return 0


def cmd_daemon(args: argparse.Namespace) -> int:
    org = load_org()
    dcfg = org.get("daemon", {})
    config = DaemonConfig(
        base_branch=args.base or dcfg.get("base_branch", "main"),
        poll_seconds=args.poll or int(dcfg.get("poll_seconds", 600)),
        endpoint_retry_seconds=int(dcfg.get("endpoint_retry_seconds", 60)),
        discover=not args.no_discover,
        once=args.once,
        max_tickets=args.max_tickets,
    )
    return Daemon(config).run()


def cmd_new(args: argparse.Namespace) -> int:
    path = new_ticket(args.id, args.title)
    print(f"created {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hermes", description="Hermes 가상 소프트웨어 조직 파이프라인")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="LLM 엔드포인트/설정/백로그 점검").set_defaults(func=cmd_check)

    b = sub.add_parser("backlog", help="티켓 목록")
    b.add_argument("--status", choices=["proposed", "todo", "in-progress", "review", "done", "blocked"])
    b.set_defaults(func=cmd_backlog)

    sub.add_parser("validate", help="org.yaml과 백로그 검증").set_defaults(func=cmd_validate)

    pl = sub.add_parser("plan", help="티켓 실행 계획 출력(LLM 미사용)")
    pl.add_argument("ticket")
    pl.add_argument("--stages", help="예: pm,design,dev,qa")
    pl.add_argument("--max-iter", type=int, default=None)
    pl.set_defaults(func=cmd_plan)

    r = sub.add_parser("run", help="티켓 파이프라인 실행")
    r.add_argument("ticket")
    r.add_argument("--stages", help="예: dev,qa (이전 산출물 재사용)")
    r.add_argument("--max-iter", type=int, default=None)
    r.add_argument("--no-branch", action="store_true", help="hermes/<id> 브랜치를 만들지 않고 현재 트리에서 작업")
    r.add_argument("--commit", action="store_true", help="완료 후 변경 사항을 커밋")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("approve", help="proposed 티켓을 todo로 승인")
    a.add_argument("ticket")
    a.set_defaults(func=cmd_approve)

    d = sub.add_parser("discover", help="Tech Lead 에이전트가 새 티켓을 제안(proposed)")
    d.add_argument("--max", type=int, default=None, help="최대 제안 수")
    d.set_defaults(func=cmd_discover)

    sub.add_parser("status", help="사람이 확인할 항목: 승인 대기/리뷰 대기/막힘").set_defaults(func=cmd_status)

    dm = sub.add_parser("daemon", help="자율 모드: todo 티켓 순차 처리, 비면 발굴 후 대기")
    dm.add_argument("--once", action="store_true", help="한 사이클만 실행")
    dm.add_argument("--no-discover", action="store_true", help="Tech Lead 발굴 비활성화")
    dm.add_argument("--poll", type=int, default=None, help="대기 시간(초)")
    dm.add_argument("--base", default=None, help="기준 브랜치 (기본 org.yaml daemon.base_branch)")
    dm.add_argument("--max-tickets", type=int, default=None, help="이 수만큼 처리 후 종료")
    dm.set_defaults(func=cmd_daemon)

    n = sub.add_parser("new", help="새 티켓 파일 생성")
    n.add_argument("id", help="예: HX-010")
    n.add_argument("title")
    n.set_defaults(func=cmd_new)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TicketError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
