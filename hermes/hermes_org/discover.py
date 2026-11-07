"""Tech Lead 역할: 저장소를 분석해 새 티켓을 제안(status: proposed)한다. 승인은 사람이 한다."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import yaml

from .agents import build_agent, build_tools, load_org
from .backlog import (
    BACKLOG_DIR,
    VALID_AREA,
    VALID_PRIORITY,
    VALID_STAGES,
    TicketError,
    load_tickets,
    next_ticket_id,
    write_ticket,
)
from .llm import build_llm
from .settings import WORKSPACE_DIR, Settings

_YAML_BLOCK = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)
_KV_LINE = re.compile(r"^(\s*(?:- )?)([A-Za-z_][\w-]*):[ \t]+(.+?)\s*$")
_ITEM_LINE = re.compile(r"^(\s*- )(.+?)\s*$")
SIMILARITY_THRESHOLD = 0.5


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _needs_quote(value: str) -> bool:
    if not value or value[0] in "\"'[{|>":
        return False
    return ": " in value or value.endswith(":") or " #" in value


def repair_yaml(raw: str) -> str:
    """소형 모델이 자주 내는 YAML 오류(값 안의 ': ', ' #')를 따옴표로 감싸 복구한다."""
    fixed = []
    for line in raw.splitlines():
        m = _KV_LINE.match(line)
        if m and _needs_quote(m.group(3)):
            fixed.append(f"{m.group(1)}{m.group(2)}: {_quote(m.group(3))}")
            continue
        m = _ITEM_LINE.match(line)
        if m and ":" not in m.group(2).split(" ")[0] and _needs_quote(m.group(2)) and not _KV_LINE.match(line):
            fixed.append(f"{m.group(1)}{_quote(m.group(2))}")
            continue
        fixed.append(line)
    return "\n".join(fixed)


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"[\s·,.;:()\[\]/\-_]+", "", text.lower())
    return {t[i : i + 2] for i in range(len(t) - 1)} if len(t) > 1 else {t}


def similarity(a: str, b: str) -> float:
    """문자 바이그램 Jaccard 유사도 (제목 중복 판정용)."""
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


SOURCE_DIRS = ("frontend/src", "signaling", "frontend/frontend-server.cjs")
SOURCE_SUFFIXES = {".js", ".cjs", ".mjs", ".vue"}
MARKER = re.compile(r"TODO|FIXME|XXX|HACK|console\.warn|catch \(")


def repo_digest(root: Path, max_chars: int = 5000) -> str:
    """소형 모델이 도구를 쓰지 않아도 근거를 갖도록 저장소 요약을 미리 계산한다."""
    rows: list[str] = []
    untested: list[str] = []
    markers: list[str] = []
    for base in SOURCE_DIRS:
        path = root / base
        files = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for f in files:
            if not f.is_file() or f.suffix not in SOURCE_SUFFIXES or "node_modules" in f.parts or "dist" in f.parts:
                continue
            rel = f.relative_to(root).as_posix()
            if ".test." in f.name or "/test/" in rel:
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rows.append(f"- {rel} ({len(lines)} lines)")
            stem = f.name.rsplit(".", 1)[0]
            has_test = any(stem in t.name for t in root.rglob(f"*{stem}*.test.*") if "node_modules" not in t.parts)
            if not has_test and f.suffix != ".vue":
                untested.append(rel)
            for i, line in enumerate(lines, start=1):
                if MARKER.search(line) and len(markers) < 25:
                    markers.append(f"- {rel}:{i}: {line.strip()[:120]}")
    out = "### 소스 파일\n" + "\n".join(rows)
    out += "\n\n### 테스트가 없는 소스 파일\n" + ("\n".join(f"- {u}" for u in untested) or "- (없음)")
    out += "\n\n### 주석 마커 / 경고 / 예외 처리 위치\n" + ("\n".join(markers) or "- (없음)")
    return out[:max_chars]


def discover_prompt(org: dict[str, Any], existing_titles: list[str], max_proposals: int, digest: str = "") -> str:
    conventions = "\n".join(f"- {c}" for c in org["project"].get("conventions", []))
    existing = "\n".join(f"- {t}" for t in existing_titles) or "- (없음)"
    return f"""
당신은 '{org['project']['name']}' 프로젝트의 Tech Lead입니다. 저장소를 분석해 다음에 처리할 개선 티켓을 제안하세요.

## 프로젝트 개요
{org['project']['description'].strip()}

## 규약
{conventions}

## 저장소 분석 자료 (자동 생성)
{digest or "(없음)"}

## 이미 존재하는 티켓 — 이 주제들과 같거나 비슷한 제안은 전부 버려진다. 제목을 바꿔 다시 내도 소용없다.
{existing}

## 절차
1. 위 분석 자료에서 의심되는 파일을 고르고 read_file로 실제 코드를 읽는다 (특히 테스트가 없는 파일, 예외 처리 위치).
2. 버그, 결함 가능성, 테스트 공백, 운영 리스크, 사용성 문제를 찾는다. 추측이 아니라 코드에서 확인한 근거를 적는다.
   **도구로 파일을 읽지 않고 쓴 제안은 무효 처리된다.** background에는 read_file로 확인한 파일 경로와 줄 번호를 반드시 인용한다.
   이미 존재하는 티켓과 같은 주제(예: 시그널링 입력 검증, 파일 전송 청킹, 재연결, TURN, getStats, 화이트보드, 채팅 구조화, 레거시 정리)는 제안하지 않는다.
3. 최대 {max_proposals}개의 티켓을 제안한다. 각 티켓은 하루 안에 끝낼 수 있는 작은 범위여야 한다.

## 출력 형식 (반드시 이 YAML 블록 하나만, 다른 설명 없이)
```yaml
- title: 제목(한국어, 60자 이내)
  priority: P0|P1|P2|P3
  area: frontend|signaling|infra|docs
  stages: [pm, design, dev, qa]      # UI 변경 없으면 design 제외
  acceptance:
    - 테스트로 검증 가능한 완료 조건 1
    - 완료 조건 2
  background: 왜 필요한지. 근거가 된 파일 경로와 줄을 명시
  scope:
    - 해야 할 일
  files:
    - 관련 파일 경로
```
"""


def parse_proposals(text: str) -> list[dict[str, Any]]:
    """LLM 출력에서 YAML 블록을 찾아 제안 목록으로 파싱. 블록이 없으면 전체를 YAML로 시도."""
    candidates = _YAML_BLOCK.findall(text) or [text]
    for raw in candidates:
        for attempt in (raw, repair_yaml(raw)):
            try:
                data = yaml.safe_load(attempt)
            except yaml.YAMLError:
                continue
            if isinstance(data, dict) and "title" in data:
                data = [data]
            if isinstance(data, list) and data and all(isinstance(d, dict) for d in data):
                return data
    return []


def normalize_proposal(p: dict[str, Any]) -> dict[str, Any]:
    stages = p.get("stages") or list(VALID_STAGES)
    if isinstance(stages, str):
        stages = [s.strip() for s in stages.strip("[]").split(",") if s.strip()]
    stages = [s for s in stages if s in VALID_STAGES]
    if "dev" in stages and "qa" not in stages:
        stages.append("qa")
    acceptance = p.get("acceptance") or []
    if isinstance(acceptance, str):
        acceptance = [acceptance]
    priority = str(p.get("priority", "P2")).upper()
    area = str(p.get("area", "frontend")).lower()
    body_parts = [f"## 배경\n\n{p.get('background', '').strip()}"]
    if p.get("scope"):
        scope = p["scope"] if isinstance(p["scope"], list) else [p["scope"]]
        body_parts.append("## 범위\n\n" + "\n".join(f"- {s}" for s in scope))
    if p.get("files"):
        files = p["files"] if isinstance(p["files"], list) else [p["files"]]
        body_parts.append("## 참고 파일\n\n" + "\n".join(f"- {f}" for f in files))
    body_parts.append("## 출처\n\nTech Lead 에이전트 제안. 사람이 검토 후 `hermes approve <ID>`로 승인한다.")
    return {
        "title": str(p.get("title", "")).strip(),
        "priority": priority if priority in VALID_PRIORITY else "P2",
        "area": area if area in VALID_AREA else "frontend",
        "stages": stages or ["pm", "dev", "qa"],
        "acceptance": [str(a) for a in acceptance],
        "body": "\n\n".join(body_parts),
    }


def _cited_files_exist(raw: dict[str, Any], repo_root: Path | None) -> bool:
    """제안이 인용한 파일 중 하나 이상이 실제로 존재해야 한다(환각 방지). files가 없으면 통과."""
    files = raw.get("files")
    if not files or repo_root is None:
        return True
    files = files if isinstance(files, list) else [files]
    return any((repo_root / str(f).strip().split(":")[0]).exists() for f in files)


def write_proposals(
    proposals: list[dict[str, Any]],
    directory: Path = BACKLOG_DIR,
    log=print,
    repo_root: Path | None = None,
) -> list[Path]:
    existing = [t.title.strip() for t in load_tickets(directory)]
    created: list[Path] = []
    for raw in proposals:
        p = normalize_proposal(raw)
        if not p["title"]:
            log("[discover] skip: empty title")
            continue
        dup = next((e for e in existing if similarity(p["title"], e) >= SIMILARITY_THRESHOLD), None)
        if dup:
            log(f"[discover] skip duplicate of existing ticket: {p['title']!r} ≈ {dup!r}")
            continue
        if not _cited_files_exist(raw, repo_root):
            log(f"[discover] skip: cited files do not exist: {raw.get('files')}")
            continue
        try:
            path = write_ticket(directory, next_ticket_id(directory), status="proposed", **p)
        except TicketError as exc:
            log(f"[discover] skip invalid proposal: {exc}")
            continue
        existing.append(p["title"])
        created.append(path)
        log(f"[discover] proposed {path.name}")
    return created


def run_discover(settings: Settings | None = None, max_proposals: int | None = None, log=print) -> list[Path]:
    """Tech Lead 에이전트를 실행해 제안 티켓 파일을 만든다."""
    from crewai import Crew, Process, Task  # noqa: WPS433

    settings = settings or Settings.from_env()
    org = load_org()
    cfg = org.get("discover", {})
    max_proposals = max_proposals or int(cfg.get("max_proposals", 3))
    existing_titles = [f"{t.id} {t.title} ({t.status})" for t in load_tickets()]

    llm = build_llm(settings)
    tools = build_tools(settings)
    agent = build_agent(cfg.get("role", "techlead"), org, llm, tools, settings=settings)
    digest = repo_digest(settings.repo_root)
    task = Task(description=discover_prompt(org, existing_titles, max_proposals, digest), expected_output="YAML 블록", agent=agent)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)

    output = crew.kickoff()
    text = getattr(output, "raw", None) or str(output)

    out_dir = WORKSPACE_DIR / "discover"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.md").write_text(text, encoding="utf-8")

    proposals = parse_proposals(text)[:max_proposals]
    if not proposals:
        log("[discover] no parsable proposals in model output")
    return write_proposals(proposals, log=log, repo_root=settings.repo_root)
