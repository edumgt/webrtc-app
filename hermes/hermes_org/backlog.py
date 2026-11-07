"""백로그 티켓(hermes/backlog/*.md) 로딩/검증. 포맷: YAML frontmatter + 마크다운 본문."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .settings import BACKLOG_DIR

VALID_STATUS = ("proposed", "todo", "in-progress", "review", "done", "blocked")
VALID_STAGES = ("pm", "design", "dev", "qa")
VALID_PRIORITY = ("P0", "P1", "P2", "P3")
VALID_AREA = ("frontend", "signaling", "infra", "docs")
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class TicketError(ValueError):
    pass


@dataclass
class Ticket:
    id: str
    title: str
    priority: str = "P2"
    status: str = "todo"
    area: str = "frontend"
    stages: list[str] = field(default_factory=lambda: list(VALID_STAGES))
    acceptance: list[str] = field(default_factory=list)
    body: str = ""
    path: Path | None = None

    @classmethod
    def from_markdown(cls, text: str, path: Path | None = None) -> "Ticket":
        match = _FRONTMATTER.match(text)
        if not match:
            raise TicketError(f"missing YAML frontmatter: {path}")
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()

        for key in ("id", "title"):
            if not meta.get(key):
                raise TicketError(f"frontmatter requires '{key}': {path}")
        ticket = cls(
            id=str(meta["id"]),
            title=str(meta["title"]),
            priority=str(meta.get("priority", "P2")),
            status=str(meta.get("status", "todo")),
            area=str(meta.get("area", "frontend")),
            stages=[str(s) for s in (meta.get("stages") or list(VALID_STAGES))],
            acceptance=[str(a) for a in (meta.get("acceptance") or [])],
            body=body,
            path=path,
        )
        ticket.validate()
        return ticket

    def validate(self) -> None:
        if self.status not in VALID_STATUS:
            raise TicketError(f"{self.id}: invalid status '{self.status}' (use {VALID_STATUS})")
        if self.priority not in VALID_PRIORITY:
            raise TicketError(f"{self.id}: invalid priority '{self.priority}' (use {VALID_PRIORITY})")
        bad = [s for s in self.stages if s not in VALID_STAGES]
        if bad:
            raise TicketError(f"{self.id}: invalid stages {bad} (use {VALID_STAGES})")
        if "dev" in self.stages and "qa" not in self.stages:
            raise TicketError(f"{self.id}: 'dev' stage requires 'qa' stage (review loop)")
        if not self.acceptance:
            raise TicketError(f"{self.id}: at least one acceptance criterion is required")

    def to_prompt(self) -> str:
        acceptance = "\n".join(f"- {a}" for a in self.acceptance)
        return (
            f"# Ticket {self.id}: {self.title}\n"
            f"- priority: {self.priority}\n- area: {self.area}\n\n"
            f"## Acceptance criteria\n{acceptance}\n\n{self.body}\n"
        )

    def set_status(self, status: str) -> None:
        """파일의 frontmatter status 값을 갱신한다."""
        if status not in VALID_STATUS:
            raise TicketError(f"invalid status {status}")
        self.status = status
        if not self.path:
            return
        text = self.path.read_text(encoding="utf-8")
        new_text, n = re.subn(r"^status:\s*.*$", f"status: {status}", text, count=1, flags=re.MULTILINE)
        if n == 0:
            new_text = text.replace("---\n", f"---\nstatus: {status}\n", 1)
        self.path.write_text(new_text, encoding="utf-8")


def load_tickets(directory: Path = BACKLOG_DIR) -> list[Ticket]:
    tickets: list[Ticket] = []
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        tickets.append(Ticket.from_markdown(path.read_text(encoding="utf-8"), path))
    ids = [t.id for t in tickets]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise TicketError(f"duplicate ticket ids: {sorted(dupes)}")
    return tickets


def find_ticket(ticket_id: str, directory: Path = BACKLOG_DIR) -> Ticket:
    for ticket in load_tickets(directory):
        if ticket.id.lower() == ticket_id.lower():
            return ticket
    raise TicketError(f"ticket not found: {ticket_id}")


TICKET_TEMPLATE = """---
id: {id}
title: {title}
priority: P2
status: todo
area: frontend
stages: [pm, design, dev, qa]
acceptance:
  - (검증 가능한 완료 조건을 적으세요)
---
## 배경

(왜 이 작업이 필요한지)

## 범위

- (해야 할 일)

## 범위 외

- (하지 않을 일)

## 참고 파일

- (관련 소스 경로)
"""


def new_ticket(ticket_id: str, title: str, directory: Path = BACKLOG_DIR) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "ticket"
    path = directory / f"{ticket_id}-{slug}.md"
    if path.exists():
        raise TicketError(f"already exists: {path}")
    path.write_text(TICKET_TEMPLATE.format(id=ticket_id, title=title), encoding="utf-8")
    return path


def next_ticket_id(directory: Path = BACKLOG_DIR, prefix: str = "HX") -> str:
    """백로그의 최대 번호 + 1 (파일명 기준이라 상태와 무관)."""
    nums = []
    for path in directory.glob(f"{prefix}-*.md"):
        m = re.match(rf"{prefix}-(\d+)", path.name)
        if m:
            nums.append(int(m.group(1)))
    return f"{prefix}-{(max(nums) + 1) if nums else 1:03d}"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "ticket"


def write_ticket(
    directory: Path,
    ticket_id: str,
    title: str,
    priority: str,
    area: str,
    stages: list[str],
    acceptance: list[str],
    body: str,
    status: str = "proposed",
) -> Path:
    """검증을 거쳐 티켓 파일을 생성한다."""
    stages_str = "[" + ", ".join(stages) + "]"
    acc = "\n".join(f"  - {a.replace(chr(10), ' ').strip()}" for a in acceptance)
    text = (
        f"---\nid: {ticket_id}\ntitle: {title.strip()}\npriority: {priority}\nstatus: {status}\n"
        f"area: {area}\nstages: {stages_str}\nacceptance:\n{acc}\n---\n{body.strip()}\n"
    )
    ticket = Ticket.from_markdown(text)  # raises TicketError if invalid
    path = directory / f"{ticket.id}-{slugify(title)}.md"
    if path.exists():
        raise TicketError(f"already exists: {path}")
    path.write_text(text, encoding="utf-8")
    return path
