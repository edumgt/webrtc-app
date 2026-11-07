"""읽기 전용 git 도구 + 파이프라인이 사용하는 브랜치/커밋 헬퍼."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..settings import REPO_ROOT


def _git(args: list[str], root: Path = REPO_ROOT, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603,S607
        ["git", *args], cwd=root, capture_output=True, text=True, check=check
    )


def git_status(root: Path = REPO_ROOT) -> str:
    """git status --short 결과."""
    proc = _git(["status", "--short", "--branch"], root)
    return proc.stdout or proc.stderr or "(clean)"


def git_diff(path: str = "", root: Path = REPO_ROOT, max_chars: int = 20_000) -> str:
    """작업 트리 diff(옵션: 특정 경로)."""
    args = ["diff", "--stat", "--patch"]
    if path:
        args.append("--")
        args.append(path)
    proc = _git(args, root)
    out = proc.stdout or "(no changes)"
    return out[:max_chars] + ("\n... (truncated)" if len(out) > max_chars else "")


def is_clean(root: Path = REPO_ROOT) -> bool:
    return _git(["status", "--porcelain"], root).stdout.strip() == ""


def current_branch(root: Path = REPO_ROOT) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()


def ensure_branch(name: str, root: Path = REPO_ROOT) -> str:
    """브랜치가 있으면 체크아웃, 없으면 현재 HEAD에서 생성."""
    exists = _git(["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], root).returncode == 0
    if exists:
        _git(["checkout", name], root, check=True)
    else:
        _git(["checkout", "-b", name], root, check=True)
    return name


def commit_all(message: str, root: Path = REPO_ROOT) -> str:
    _git(["add", "-A"], root, check=True)
    if is_clean(root):
        return "(nothing to commit)"
    proc = _git(["commit", "-m", message], root)
    return proc.stdout.strip() or proc.stderr.strip()
