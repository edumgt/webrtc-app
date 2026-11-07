"""허용 목록 기반 셸 실행 도구. 저장소 내부에서만, 제한된 명령만 실행한다."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from ..settings import REPO_ROOT
from .fs import SandboxError, resolve_in_repo

# 명령은 첫 토큰(프로그램)과 이어지는 토큰 접두사로 매칭한다.
ALLOWED_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("npm", "ci"),
    ("npm", "install"),
    ("npx", "vitest"),
    ("npx", "vite", "build"),
    ("node", "--test"),
    ("node", "--check"),
    ("node", "-e"),
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("ls",),
    ("cat",),
    ("wc",),
    ("grep",),
)
FORBIDDEN_TOKENS = {"rm", "sudo", "curl", "wget", "ssh", "scp", "docker", "kubectl", "aws", ">", ">>", "|", "&&", ";", "`", "$("}
MAX_OUTPUT_CHARS = 12_000


def is_allowed(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or any(tok in FORBIDDEN_TOKENS for tok in tokens):
        return False
    return any(tuple(tokens[: len(prefix)]) == prefix for prefix in ALLOWED_COMMANDS)


def run_command(command: str, cwd: str = ".", timeout: int = 600, root: Path = REPO_ROOT) -> str:
    """허용된 명령만 저장소 내부 디렉터리에서 실행하고 stdout/stderr를 반환."""
    if not is_allowed(command):
        return (
            "ERROR: command not allowed. Allowed prefixes: "
            + ", ".join(" ".join(p) for p in ALLOWED_COMMANDS)
        )
    try:
        workdir = resolve_in_repo(cwd, root)
    except SandboxError as exc:
        return f"ERROR: {exc}"
    if not workdir.is_dir():
        return f"ERROR: cwd is not a directory: {cwd}"

    env = {**os.environ, "CI": "1", "FORCE_COLOR": "0", "NO_COLOR": "1"}
    try:
        proc = subprocess.run(  # noqa: S603
            shlex.split(command),
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout}s: {command}"
    except FileNotFoundError as exc:
        return f"ERROR: {exc}"

    output = f"$ {command}\n(exit code {proc.returncode})\n"
    if proc.stdout:
        output += "--- stdout ---\n" + proc.stdout
    if proc.stderr:
        output += "--- stderr ---\n" + proc.stderr
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[: MAX_OUTPUT_CHARS // 2] + "\n... (truncated) ...\n" + output[-MAX_OUTPUT_CHARS // 2 :]
    return output
