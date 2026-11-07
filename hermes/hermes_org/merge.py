"""일일 자동 머지: QA PASS(review) 브랜치를 기준 브랜치에 머지하고, 테스트·빌드가 통과하면 확정한다.

실패(충돌, 테스트 실패)하면 머지를 되돌리고 티켓은 review 상태로 남겨 사람이 본다.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .backlog import Ticket, TicketError
from .settings import REPO_ROOT, WORKSPACE_DIR
from .tools import git

Logger = Callable[[str], None]
Verifier = Callable[[Path, Logger], tuple[bool, str]]

VERIFY_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("signaling", ["npm", "test"]),
    ("frontend", ["npm", "test"]),
    ("frontend", ["npm", "run", "build"]),
)
_BRANCH_TICKET = re.compile(r"^hermes/([A-Za-z]+-\d+)$")


@dataclass
class MergeConfig:
    base_branch: str = "main"
    push: bool = True
    delete_merged_branches: bool = True
    verify: bool = True
    verify_timeout: int = 900


@dataclass
class MergeOutcome:
    branch: str
    ticket_id: str
    result: str  # merged | conflict | verify-failed | skipped | error
    detail: str = ""


@dataclass
class MergeReport:
    started_at: str
    outcomes: list[MergeOutcome] = field(default_factory=list)
    pushed: bool = False
    note: str = ""

    @property
    def merged(self) -> list[MergeOutcome]:
        return [o for o in self.outcomes if o.result == "merged"]


def _run(args: list[str], root: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603


def has_remote(root: Path, name: str = "origin") -> bool:
    return name in _run(["git", "remote"], root).stdout.split()


def list_ticket_branches(root: Path) -> list[tuple[str, str]]:
    """로컬 hermes/<ID> 브랜치 → (branch, ticket_id)."""
    out = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/hermes/"], root).stdout
    found = []
    for name in out.split():
        m = _BRANCH_TICKET.match(name)
        if m:
            found.append((name, m.group(1)))
    return sorted(found)


def ticket_on_branch(root: Path, branch: str, ticket_id: str) -> Ticket | None:
    """브랜치의 백로그 파일에서 티켓을 읽는다(작업 트리를 바꾸지 않음)."""
    files = _run(["git", "ls-tree", "--name-only", branch, "hermes/backlog/"], root).stdout.split()
    for path in files:
        if Path(path).name.upper().startswith(ticket_id.upper() + "-"):
            text = _run(["git", "show", f"{branch}:{path}"], root).stdout
            try:
                return Ticket.from_markdown(text, root / path)
            except TicketError:
                return None
    return None


def default_verify(root: Path, log: Logger, timeout: int = 900) -> tuple[bool, str]:
    """머지된 트리에서 테스트와 빌드를 실행한다. node_modules가 없으면 npm ci."""
    for subdir, cmd in VERIFY_STEPS:
        cwd = root / subdir
        if not cwd.is_dir():
            continue
        if not (cwd / "node_modules").exists():
            log(f"[merge] npm ci in {subdir}")
            ci = _run(["npm", "ci", "--no-audit", "--no-fund"], cwd, timeout=timeout)
            if ci.returncode != 0:
                return False, f"npm ci failed in {subdir}:\n{ci.stderr[-2000:]}"
        log(f"[merge] verify: {' '.join(cmd)} ({subdir})")
        try:
            proc = _run(cmd, cwd, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f"timeout: {' '.join(cmd)} in {subdir}"
        if proc.returncode != 0:
            tail = (proc.stdout + "\n" + proc.stderr)[-3000:]
            return False, f"{' '.join(cmd)} failed in {subdir} (exit {proc.returncode}):\n{tail}"
    return True, "all verification steps passed"


def auto_merge(
    config: MergeConfig,
    root: Path = REPO_ROOT,
    log: Logger = print,
    verify: Verifier | None = None,
    dry_run: bool = False,
) -> MergeReport:
    report = MergeReport(started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    verify = verify or (lambda r, lg: default_verify(r, lg, config.verify_timeout))

    # 0) 기준 브랜치, 깨끗한 트리, 원격 최신화
    if git.current_branch(root) != config.base_branch:
        if not git.is_clean(root):
            report.note = "working tree dirty on non-base branch; skipped"
            log(f"[merge] {report.note}")
            return report
        _run(["git", "checkout", config.base_branch], root)
    if not git.is_clean(root):
        report.note = f"{config.base_branch} has uncommitted changes; skipped"
        log(f"[merge] {report.note}")
        return report

    remote = has_remote(root)
    if remote:
        fetch = _run(["git", "fetch", "--prune", "origin"], root, timeout=120)
        if fetch.returncode != 0:
            report.note = f"git fetch failed: {fetch.stderr.strip()[-300:]}"
            log(f"[merge] {report.note}; continuing offline")
            remote = False
        else:
            pull = _run(["git", "pull", "--rebase", "origin", config.base_branch], root, timeout=120)
            if pull.returncode != 0:
                _run(["git", "rebase", "--abort"], root)
                report.note = f"git pull --rebase failed: {pull.stderr.strip()[-300:]}"
                log(f"[merge] {report.note}; skipped")
                return report

    # 1) 후보: 티켓 상태가 review 인 hermes/<ID> 브랜치
    for branch, ticket_id in list_ticket_branches(root):
        ticket = ticket_on_branch(root, branch, ticket_id)
        if ticket is None:
            report.outcomes.append(MergeOutcome(branch, ticket_id, "skipped", "ticket file not found on branch"))
            continue
        if ticket.status != "review":
            report.outcomes.append(MergeOutcome(branch, ticket_id, "skipped", f"status={ticket.status} (needs review)"))
            continue
        if dry_run:
            report.outcomes.append(MergeOutcome(branch, ticket_id, "skipped", "dry-run: would merge"))
            log(f"[merge] dry-run: would merge {branch} ({ticket.title})")
            continue

        log(f"[merge] ▶ {branch}: {ticket.title}")
        head_before = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        merge = _run(["git", "merge", "--no-ff", "--no-edit", "-m", f"merge({ticket_id}): {ticket.title}\n\nQA PASS 브랜치 자동 머지 (hermes merge)", branch], root)
        if merge.returncode != 0:
            _run(["git", "merge", "--abort"], root)
            _run(["git", "reset", "--hard", head_before], root)
            report.outcomes.append(MergeOutcome(branch, ticket_id, "conflict", merge.stdout.strip()[-500:] or merge.stderr.strip()[-500:]))
            log(f"[merge] ✗ conflict on {branch}; left for a human")
            continue

        if config.verify:
            ok, detail = verify(root, log)
            if not ok:
                _run(["git", "reset", "--hard", head_before], root)
                report.outcomes.append(MergeOutcome(branch, ticket_id, "verify-failed", detail))
                log(f"[merge] ✗ verification failed after merging {branch}; merge reverted")
                continue

        # 2) 티켓을 done으로
        path = ticket.path if ticket.path and ticket.path.exists() else None
        if path:
            Ticket.from_markdown(path.read_text(encoding="utf-8"), path).set_status("done")
            _run(["git", "add", str(path)], root)
            _run(["git", "commit", "-q", "-m", f"chore({ticket_id}): status done"], root)
        if config.delete_merged_branches:
            _run(["git", "branch", "-d", branch], root)
        report.outcomes.append(MergeOutcome(branch, ticket_id, "merged", ticket.title))
        log(f"[merge] ✓ merged {branch}")

    # 3) push
    if report.merged and config.push and remote and not dry_run:
        push = _run(["git", "push", "origin", config.base_branch], root, timeout=120)
        report.pushed = push.returncode == 0
        if report.pushed and config.delete_merged_branches:
            for o in report.merged:
                _run(["git", "push", "origin", "--delete", o.branch], root, timeout=60)
        log("[merge] pushed to origin" if report.pushed else f"[merge] push failed: {push.stderr.strip()[-300:]}")

    _write_report(report, root)
    return report


def _write_report(report: MergeReport, root: Path) -> None:
    out = WORKSPACE_DIR / "merge-report.md" if root == REPO_ROOT else root / "hermes" / "workspace" / "merge-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"## {report.started_at}", ""]
    if report.note:
        lines.append(f"- note: {report.note}")
    for o in report.outcomes:
        lines.append(f"- {o.result:14s} {o.branch} ({o.ticket_id}) {o.detail.splitlines()[0] if o.detail else ''}")
    lines.append(f"- pushed: {report.pushed}")
    with out.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")
