"""자율 데몬: todo 티켓을 우선순위대로 처리하고, 비면 Tech Lead 발굴을 돌린 뒤 대기한다.

사람이 하는 일: proposed 티켓 승인(hermes approve), review 브랜치 검토·머지, blocked 티켓 처리.
데몬이 하지 않는 일: main에 코드 머지, git push, 티켓 자동 승인.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .agents import load_org
from .backlog import BACKLOG_DIR, Ticket, load_tickets
from .llm import check_endpoint
from .pipeline import Pipeline
from .settings import WORKSPACE_DIR, Settings
from .tools import git

Logger = Callable[[str], None]
STATE_FILE = WORKSPACE_DIR / "daemon-state.json"
PAUSE_FILE = WORKSPACE_DIR / "PAUSE"
_HOURS = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def parse_active_hours(spec: str | None) -> tuple[dt.time, dt.time] | None:
    """'01:00-07:00' → (time, time). 비어 있으면 None(항상 활성). 자정을 넘는 구간('22:00-06:00')도 허용."""
    if not spec or not str(spec).strip():
        return None
    m = _HOURS.match(str(spec))
    if not m:
        raise ValueError(f"active_hours must look like 'HH:MM-HH:MM', got {spec!r}")
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    return dt.time(h1, m1), dt.time(h2, m2)


def is_active(now: dt.time, window: tuple[dt.time, dt.time] | None) -> bool:
    if window is None:
        return True
    start, end = window
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # 자정을 넘는 구간
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"tickets": {}}


def save_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_next(tickets: list[Ticket], state: dict[str, Any]) -> Ticket | None:
    """처리된 적 없는 todo 티켓 중 우선순위(P0 먼저) → ID 순."""
    handled = set(state.get("tickets", {}))
    todo = [t for t in tickets if t.status == "todo" and t.id not in handled]
    todo.sort(key=lambda t: (PRIORITY_ORDER.get(t.priority, 9), t.id))
    return todo[0] if todo else None


@dataclass
class DaemonConfig:
    base_branch: str = "main"
    poll_seconds: int = 600
    endpoint_retry_seconds: int = 60
    discover: bool = True
    once: bool = False
    max_tickets: int | None = None
    active_hours: str | None = None   # 예: "01:00-07:00". None이면 항상
    pause_file: Path = PAUSE_FILE


class Daemon:
    def __init__(
        self,
        config: DaemonConfig,
        settings: Settings | None = None,
        backlog_dir: Path = BACKLOG_DIR,
        state_file: Path = STATE_FILE,
        log: Logger = print,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.settings = settings or Settings.from_env()
        self.org = load_org()
        self.backlog_dir = backlog_dir
        self.state_file = state_file
        self.log = lambda msg: log(f"{time.strftime('%H:%M:%S')} {msg}")
        self.sleep = sleep
        self.root = self.settings.repo_root
        self.processed = 0
        self.window = parse_active_hours(config.active_hours)

    # ---------- 메인 루프 ----------
    def run(self) -> int:
        self.log(f"[daemon] start base={self.config.base_branch} model={self.settings.litellm_model} @ {self.settings.base_url}")
        while True:
            try:
                did_work = self.tick()
            except KeyboardInterrupt:
                self.log("[daemon] interrupted")
                return 0
            except Exception as exc:  # noqa: BLE001
                self.log(f"[daemon] unexpected error: {exc}\n{traceback.format_exc()}")
                did_work = False
            if self.config.once:
                return 0
            if self.config.max_tickets and self.processed >= self.config.max_tickets:
                self.log(f"[daemon] processed {self.processed} tickets, stopping")
                return 0
            if not did_work:
                self.sleep(self.config.poll_seconds)

    def paused_reason(self, now: dt.time | None = None) -> str | None:
        """일시정지 사유. None이면 작업 가능."""
        if self.config.pause_file.exists():
            return f"pause file present: {self.config.pause_file} (remove it or run `hermes resume`)"
        now = now or dt.datetime.now().time()
        if not is_active(now, self.window):
            return f"outside active hours {self.config.active_hours} (now {now.strftime('%H:%M')})"
        return None

    def tick(self) -> bool:
        """한 사이클. 작업을 했으면 True, 대기해야 하면 False."""
        reason = self.paused_reason()
        if reason:
            self.log(f"[daemon] paused: {reason}")
            return False

        info = check_endpoint(self.settings)
        if not info["ok"]:
            self.log(f"[daemon] LLM endpoint unreachable ({info['error']}); retry in {self.config.endpoint_retry_seconds}s")
            self.sleep(self.config.endpoint_retry_seconds)
            return False

        if not self._return_to_base():
            return False

        state = load_state(self.state_file)
        ticket = pick_next(load_tickets(self.backlog_dir), state)
        if ticket:
            self._run_ticket(ticket, state)
            return True

        if self.config.discover and self._should_discover():
            self._run_discover()
            return True

        self.log("[daemon] nothing to do (no todo tickets); waiting for human approval/merge")
        return False

    # ---------- 단계 ----------
    def _return_to_base(self) -> bool:
        if git.current_branch(self.root) != self.config.base_branch:
            if not git.is_clean(self.root):
                self.log("[daemon] working tree dirty on a non-base branch; leaving it for a human")
                return False
            git._git(["checkout", self.config.base_branch], self.root, check=True)
        if not git.is_clean(self.root):
            self.log(f"[daemon] base branch '{self.config.base_branch}' has uncommitted changes; commit or stash them first")
            return False
        return True

    def _run_ticket(self, ticket: Ticket, state: dict[str, Any]) -> None:
        self.log(f"[daemon] ▶ {ticket.id} {ticket.title} [{ticket.priority}]")
        started = time.time()
        entry: dict[str, Any] = {"branch": f"hermes/{ticket.id}", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        pipe = Pipeline(ticket, settings=self.settings, org=self.org, log=self.log)
        try:
            result = pipe.run(create_branch=True, commit=False)
            verdict = "PASS" if result.passed else "FAIL" if result.passed is False else "N/A"
            ticket.set_status("review" if result.passed else "blocked")
            entry.update(verdict=verdict, iterations=result.iterations, status=ticket.status)
            msg = f"hermes({ticket.id}): {ticket.title}\n\nQA verdict: {verdict} (iterations={result.iterations})\nartifacts: hermes/workspace/{ticket.id}/"
        except Exception as exc:  # noqa: BLE001
            self.log(f"[daemon] ✗ {ticket.id} failed: {exc}")
            entry.update(verdict="ERROR", error=str(exc), status="blocked")
            try:
                ticket.set_status("blocked")
            except Exception:  # noqa: BLE001
                pass
            msg = f"hermes({ticket.id}): partial work (pipeline error)\n\n{exc}"

        commit = git.commit_all(msg + "\n\nCo-Authored-By: Hermes Org <hermes@local>", self.root)
        entry.update(commit=commit, seconds=round(time.time() - started), finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        state.setdefault("tickets", {})[ticket.id] = entry
        save_state(state, self.state_file)
        self.processed += 1
        self.log(f"[daemon] ■ {ticket.id} → {entry.get('status')} on {entry['branch']} ({entry['seconds']}s)")
        self._return_to_base()

    def _should_discover(self) -> bool:
        cfg = self.org.get("discover", {})
        open_proposed = [t for t in load_tickets(self.backlog_dir) if t.status == "proposed"]
        limit = int(cfg.get("max_open_proposed", 5))
        if len(open_proposed) >= limit:
            self.log(f"[daemon] {len(open_proposed)} proposals await approval (limit {limit}); skipping discover")
            return False
        return True

    def _run_discover(self) -> None:
        from .discover import run_discover  # noqa: WPS433

        self.log("[daemon] ▶ discover (Tech Lead)")
        created = run_discover(self.settings, log=self.log)
        if created:
            names = ", ".join(p.stem.split("-")[0] + "-" + p.stem.split("-")[1] for p in created)
            git.commit_all(f"hermes(discover): propose {len(created)} tickets ({names})\n\nstatus: proposed — 사람 승인 필요 (hermes approve <ID>)", self.root)
            self.log(f"[daemon] ■ proposed {len(created)} tickets; approve with: hermes approve <ID>")
        else:
            self.log("[daemon] ■ discover produced no new tickets")
        # 제안이 비어도 같은 사이클에 반복 호출되지 않도록 대기
        self.sleep(self.config.poll_seconds)
