from pathlib import Path

import pytest

from hermes_org.backlog import BACKLOG_DIR, Ticket, TicketError, find_ticket, load_tickets, new_ticket

SAMPLE = """---
id: HX-900
title: 샘플
priority: P1
status: todo
area: frontend
stages: [pm, dev, qa]
acceptance:
  - 조건 A
---
## 배경
본문
"""


def test_parse_ticket():
    t = Ticket.from_markdown(SAMPLE)
    assert t.id == "HX-900"
    assert t.stages == ["pm", "dev", "qa"]
    assert t.acceptance == ["조건 A"]
    assert "## 배경" in t.body
    assert "# Ticket HX-900" in t.to_prompt()


def test_dev_requires_qa():
    with pytest.raises(TicketError, match="requires 'qa'"):
        Ticket.from_markdown(SAMPLE.replace("[pm, dev, qa]", "[pm, dev]"))


def test_acceptance_required():
    with pytest.raises(TicketError, match="acceptance"):
        Ticket.from_markdown(SAMPLE.replace("  - 조건 A\n", ""))


def test_invalid_status():
    with pytest.raises(TicketError, match="invalid status"):
        Ticket.from_markdown(SAMPLE.replace("status: todo", "status: wip"))


def test_real_backlog_is_valid():
    tickets = load_tickets(BACKLOG_DIR)
    assert tickets, "backlog should contain tickets"
    assert find_ticket("hx-001").id == "HX-001"


def test_set_status_rewrites_file(tmp_path: Path):
    path = tmp_path / "HX-901-x.md"
    path.write_text(SAMPLE.replace("HX-900", "HX-901"), encoding="utf-8")
    t = Ticket.from_markdown(path.read_text(encoding="utf-8"), path)
    t.set_status("review")
    assert "status: review" in path.read_text(encoding="utf-8")
    assert Ticket.from_markdown(path.read_text(encoding="utf-8")).status == "review"


def test_new_ticket_and_duplicate_detection(tmp_path: Path):
    p = new_ticket("HX-902", "새 기능 Alpha", tmp_path)
    assert p.exists() and p.name.startswith("HX-902-")
    (tmp_path / "dup.md").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(TicketError, match="duplicate"):
        load_tickets(tmp_path)
