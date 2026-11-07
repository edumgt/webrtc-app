import subprocess
from pathlib import Path

import pytest

from hermes_org.merge import MergeConfig, auto_merge, list_ticket_branches, ticket_on_branch

TICKET = """---
id: {id}
title: 티켓 {id}
priority: P2
status: {status}
area: docs
stages: [pm, dev, qa]
acceptance:
  - a
---
body
"""


def g(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    g(tmp_path, "init", "-q", "-b", "main")
    g(tmp_path, "config", "user.email", "t@t")
    g(tmp_path, "config", "user.name", "t")
    (tmp_path / "hermes" / "backlog").mkdir(parents=True)
    (tmp_path / "app.txt").write_text("base\n")
    (tmp_path / "hermes/backlog/HX-001-a.md").write_text(TICKET.format(id="HX-001", status="todo"))
    (tmp_path / "hermes/backlog/HX-002-b.md").write_text(TICKET.format(id="HX-002", status="todo"))
    g(tmp_path, "add", "-A")
    g(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def make_branch(root: Path, tid: str, status: str, change: str, file: str = None):
    g(root, "checkout", "-q", "-b", f"hermes/{tid}")
    (root / (file or f"{tid}.txt")).write_text(change)
    name = {"HX-001": "HX-001-a.md", "HX-002": "HX-002-b.md"}[tid]
    (root / "hermes/backlog" / name).write_text(TICKET.format(id=tid, status=status))
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", f"work {tid}")
    g(root, "checkout", "-q", "main")


def test_list_and_read_ticket_on_branch(repo: Path):
    make_branch(repo, "HX-001", "review", "x")
    assert list_ticket_branches(repo) == [("hermes/HX-001", "HX-001")]
    t = ticket_on_branch(repo, "hermes/HX-001", "HX-001")
    assert t.status == "review" and t.id == "HX-001"


def test_merges_review_branch_marks_done_and_deletes_branch(repo: Path):
    make_branch(repo, "HX-001", "review", "x")
    make_branch(repo, "HX-002", "blocked", "y")
    logs = []
    report = auto_merge(MergeConfig(push=False), root=repo, log=logs.append, verify=lambda r, lg: (True, "ok"))
    results = {o.ticket_id: o.result for o in report.outcomes}
    assert results == {"HX-001": "merged", "HX-002": "skipped"}
    assert (repo / "HX-001.txt").exists()
    assert "status: done" in (repo / "hermes/backlog/HX-001-a.md").read_text()
    assert "hermes/HX-001" not in g(repo, "branch")
    assert "hermes/HX-002" in g(repo, "branch")
    assert "merge(HX-001)" in g(repo, "log", "--oneline", "-3")
    assert (repo / "hermes/workspace/merge-report.md").exists()


def test_verification_failure_reverts_merge(repo: Path):
    make_branch(repo, "HX-001", "review", "x")
    head = g(repo, "rev-parse", "HEAD").strip()
    report = auto_merge(MergeConfig(push=False), root=repo, log=lambda m: None, verify=lambda r, lg: (False, "tests failed"))
    assert report.outcomes[0].result == "verify-failed"
    assert g(repo, "rev-parse", "HEAD").strip() == head
    assert not (repo / "HX-001.txt").exists()
    assert "hermes/HX-001" in g(repo, "branch")  # 사람이 볼 수 있게 남김
    assert "status: todo" in (repo / "hermes/backlog/HX-001-a.md").read_text()


def test_conflict_is_aborted_and_left_for_human(repo: Path):
    make_branch(repo, "HX-001", "review", "branch version\n", file="app.txt")
    (repo / "app.txt").write_text("main version\n")
    g(repo, "commit", "-qam", "main change")
    head = g(repo, "rev-parse", "HEAD").strip()
    report = auto_merge(MergeConfig(push=False), root=repo, log=lambda m: None, verify=lambda r, lg: (True, "ok"))
    assert report.outcomes[0].result == "conflict"
    assert g(repo, "rev-parse", "HEAD").strip() == head
    assert [l for l in g(repo, "status", "--porcelain").splitlines() if "hermes/workspace" not in l] == []


def test_dry_run_changes_nothing(repo: Path):
    make_branch(repo, "HX-001", "review", "x")
    head = g(repo, "rev-parse", "HEAD").strip()
    report = auto_merge(MergeConfig(push=False), root=repo, log=lambda m: None, dry_run=True)
    assert report.outcomes[0].result == "skipped" and "dry-run" in report.outcomes[0].detail
    assert g(repo, "rev-parse", "HEAD").strip() == head


def test_dirty_tree_skips(repo: Path):
    make_branch(repo, "HX-001", "review", "x")
    (repo / "dirty.txt").write_text("!")
    report = auto_merge(MergeConfig(push=False), root=repo, log=lambda m: None)
    assert report.outcomes == [] and "uncommitted" in report.note


def test_daemon_merge_due_once_per_day(tmp_path: Path, monkeypatch):
    import datetime as dt

    from hermes_org import daemon as d
    from hermes_org.settings import Settings

    dm = d.Daemon(d.DaemonConfig(once=True, merge_at="07:00"), settings=Settings(repo_root=tmp_path), backlog_dir=tmp_path, state_file=tmp_path / "s.json", log=lambda m: None, sleep=lambda s: None)
    day = dt.datetime(2026, 11, 8, 7, 30)
    assert dm.merge_due(day, {}) is True
    assert dm.merge_due(dt.datetime(2026, 11, 8, 6, 59), {}) is False
    assert dm.merge_due(day, {"last_merge_date": "2026-11-08"}) is False
    assert dm.merge_due(day, {"last_merge_date": "2026-11-07"}) is True
    off = d.Daemon(d.DaemonConfig(once=True), settings=Settings(repo_root=tmp_path), backlog_dir=tmp_path, state_file=tmp_path / "s.json", log=lambda m: None, sleep=lambda s: None)
    assert off.merge_due(day, {}) is False
