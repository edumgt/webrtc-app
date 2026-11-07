"""hermes CLI: check / backlog / validate / plan / run / new"""
from __future__ import annotations

import argparse
import sys

from .agents import load_org
from .backlog import TicketError, find_ticket, load_tickets, new_ticket
from .daemon import PAUSE_FILE, Daemon, DaemonConfig, load_state
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
        org = load_org()
        print("✓ config/org.yaml ok")
        missing = sorted({
            str(r["model"]) for r in org["roles"].values()
            if r.get("model") and info["models"] and str(r["model"]) not in info["models"]
        })
        if missing:
            for m in missing:
                print(f"✗ role model '{m}' not found on endpoint (ollama pull {m})")
            return 1
        overrides = {k: r["model"] for k, r in org["roles"].items() if r.get("model")}
        if overrides:
            print("✓ role models ok: " + ", ".join(f"{k}={v}" for k, v in overrides.items()))
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

    if PAUSE_FILE.exists():
        print(f"⏸ 데몬 일시정지 중 ({PAUSE_FILE.read_text(encoding='utf-8').strip()}) → hermes resume")
    last = load_state().get("last_merge")
    if last:
        print(f"마지막 자동 머지: {last.get('at')} merged={last.get('merged')} pushed={last.get('pushed')}" + (f" issues={last['issues']}" if last.get("issues") else ""))
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


def cmd_pause(_: argparse.Namespace) -> int:
    PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text(f"paused at {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")
    print(f"✓ paused (진행 중인 티켓은 마친 뒤 대기). resume: hermes resume")
    return 0


def cmd_resume(_: argparse.Namespace) -> int:
    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink()
        print("✓ resumed")
    else:
        print("(not paused)")
    return 0


def _merge_config(org: dict, push_override: bool | None = None) -> "MergeConfig":
    from .merge import MergeConfig  # noqa: WPS433

    mcfg = org.get("auto_merge", {})
    return MergeConfig(
        base_branch=org.get("daemon", {}).get("base_branch", "main"),
        push=bool(mcfg.get("push", True)) if push_override is None else push_override,
        delete_merged_branches=bool(mcfg.get("delete_merged_branches", True)),
        verify=bool(mcfg.get("verify", True)),
        verify_timeout=int(mcfg.get("verify_timeout", 900)),
    )


def cmd_merge(args: argparse.Namespace) -> int:
    from .merge import auto_merge  # noqa: WPS433

    org = load_org()
    report = auto_merge(_merge_config(org, push_override=False if args.no_push else None), dry_run=args.dry_run)
    for o in report.outcomes:
        print(f"{o.result:14s} {o.branch} ({o.ticket_id}) {o.detail.splitlines()[0] if o.detail else ''}")
    if report.note:
        print(f"note: {report.note}")
    print(f"merged={len(report.merged)} pushed={report.pushed}")
    return 0 if not any(o.result in ("conflict", "verify-failed") for o in report.outcomes) else 2


def cmd_daemon(args: argparse.Namespace) -> int:
    org = load_org()
    dcfg = org.get("daemon", {})
    config = DaemonConfig(
        merge_at=(args.merge_at if args.merge_at is not None else dcfg.get("merge_at")) or None,
        merge=_merge_config(org),
        active_hours=args.active_hours if args.active_hours is not None else dcfg.get("active_hours") or None,
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
    dm.add_argument("--active-hours", default=None, help='작동 시간대, 예: "01:00-07:00" (빈 문자열이면 항상)')
    dm.add_argument("--merge-at", default=None, help='일일 자동 머지 시각, 예: "07:00" (빈 문자열이면 안 함)')
    dm.set_defaults(func=cmd_daemon)

    mg = sub.add_parser("merge", help="QA PASS(review) 브랜치를 기준 브랜치에 머지·검증·푸시 (데몬이 하루 한 번 자동 실행)")
    mg.add_argument("--dry-run", action="store_true", help="대상만 보여주고 머지하지 않음")
    mg.add_argument("--no-push", action="store_true", help="원격에 푸시하지 않음")
    mg.set_defaults(func=cmd_merge)

    sub.add_parser("pause", help="데몬 일시정지 (PAUSE 파일 생성)").set_defaults(func=cmd_pause)
    sub.add_parser("resume", help="데몬 재개 (PAUSE 파일 삭제)").set_defaults(func=cmd_resume)

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
