"""저장소 루트로 샌드박싱된 파일 시스템 도구."""
from __future__ import annotations

import re
from pathlib import Path

from ..settings import REPO_ROOT

# 에이전트가 읽거나 쓸 수 없는 경로(저장소 루트 기준 상대 경로 접두사)
DENY_PREFIXES = (".git/", "node_modules/", "hermes/.venv/")
DENY_NAMES = {".env"}
MAX_READ_CHARS = 60_000


class SandboxError(PermissionError):
    pass


def resolve_in_repo(path: str, root: Path = REPO_ROOT) -> Path:
    """경로를 저장소 루트 내부로 한정하여 절대 경로로 변환."""
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    try:
        rel = candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise SandboxError(f"path escapes repository: {path}") from exc

    rel_str = rel.as_posix()
    if any(rel_str == p.rstrip("/") or rel_str.startswith(p) for p in DENY_PREFIXES):
        raise SandboxError(f"path is denied: {rel_str}")
    if candidate.name in DENY_NAMES or (candidate.name.startswith(".env") and candidate.name != ".env.example"):
        raise SandboxError(f"path is denied: {rel_str}")
    return candidate


def read_file(path: str, start_line: int = 1, max_lines: int = 400, root: Path = REPO_ROOT) -> str:
    """파일 내용을 줄 번호와 함께 반환. 긴 파일은 start_line/max_lines로 나누어 읽는다."""
    target = resolve_in_repo(path, root)
    if not target.is_file():
        return f"ERROR: not a file: {path}"
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(start_line, 1)
    chunk = lines[start - 1 : start - 1 + max_lines]
    body = "\n".join(f"{i:5d}| {line}" for i, line in enumerate(chunk, start=start))
    footer = ""
    if start - 1 + max_lines < len(lines):
        footer = f"\n... ({len(lines)} lines total, continue with start_line={start + max_lines})"
    return (body + footer)[:MAX_READ_CHARS]


def write_file(path: str, content: str, root: Path = REPO_ROOT) -> str:
    """파일 전체를 덮어쓴다(없으면 생성). 상위 디렉터리는 자동 생성."""
    target = resolve_in_repo(path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {target.relative_to(root.resolve()).as_posix()}"


def list_dir(path: str = ".", depth: int = 2, root: Path = REPO_ROOT) -> str:
    """디렉터리 트리를 depth 단계까지 나열(node_modules, .git 등 제외)."""
    base = resolve_in_repo(path, root)
    if not base.is_dir():
        return f"ERROR: not a directory: {path}"
    skip = {".git", "node_modules", ".venv", "dist", "__pycache__", ".pytest_cache"}
    out: list[str] = []

    def walk(d: Path, level: int) -> None:
        if level > depth:
            return
        for child in sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            if child.name in skip:
                continue
            rel = child.relative_to(root.resolve()).as_posix()
            out.append(f"{'  ' * (level - 1)}{rel}{'/' if child.is_dir() else ''}")
            if child.is_dir():
                walk(child, level + 1)

    walk(base, 1)
    return "\n".join(out) if out else "(empty)"


def search_text(pattern: str, path: str = ".", max_results: int = 50, root: Path = REPO_ROOT) -> str:
    """정규식으로 텍스트 파일을 검색(grep -rn 대용)."""
    base = resolve_in_repo(path, root)
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"ERROR: invalid regex: {exc}"
    skip_dirs = {".git", "node_modules", ".venv", "dist", "__pycache__"}
    results: list[str] = []
    files = [base] if base.is_file() else base.rglob("*")
    for file in files:
        if not file.is_file() or any(part in skip_dirs for part in file.parts):
            continue
        if file.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".lock"}:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                rel = file.relative_to(root.resolve()).as_posix()
                results.append(f"{rel}:{i}: {line.strip()[:200]}")
                if len(results) >= max_results:
                    return "\n".join(results) + f"\n... (truncated at {max_results})"
    return "\n".join(results) if results else "(no matches)"
