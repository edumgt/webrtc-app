"""org.yaml → CrewAI Agent 생성 및 도구 바인딩."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import dataclasses

from .llm import build_llm
from .settings import ORG_CONFIG, Settings
from .tools import fs, git, shell


def load_org(path: Path = ORG_CONFIG) -> dict[str, Any]:
    org = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("roles", "stages", "review_loop", "project"):
        if key not in org:
            raise ValueError(f"org.yaml missing '{key}'")
    for stage, spec in org["stages"].items():
        if spec.get("role") not in org["roles"]:
            raise ValueError(f"stage '{stage}' references unknown role '{spec.get('role')}'")
    return org


def build_tools(settings: Settings) -> dict[str, Any]:
    """순수 함수 도구를 CrewAI 도구로 래핑. 이름은 org.yaml의 roles.*.tools와 일치해야 한다."""
    from crewai.tools import tool  # noqa: WPS433

    root = settings.repo_root

    @tool("read_file")
    def read_file(path: str, start_line: int = 1, max_lines: int = 400) -> str:
        """Read a text file from the repository with line numbers. Use start_line/max_lines to page through long files. path is relative to the repository root."""
        try:
            return fs.read_file(path, start_line, max_lines, root=root)
        except fs.SandboxError as exc:
            return f"ERROR: {exc}"

    @tool("write_file")
    def write_file(path: str, content: str) -> str:
        """Overwrite (or create) a file in the repository with the full new content. Always read_file first and write the COMPLETE file, never a fragment. path is relative to the repository root."""
        try:
            return fs.write_file(path, content, root=root)
        except fs.SandboxError as exc:
            return f"ERROR: {exc}"

    @tool("list_dir")
    def list_dir(path: str = ".", depth: int = 2) -> str:
        """List the repository directory tree (node_modules/.git excluded) up to the given depth."""
        try:
            return fs.list_dir(path, depth, root=root)
        except fs.SandboxError as exc:
            return f"ERROR: {exc}"

    @tool("search_text")
    def search_text(pattern: str, path: str = ".", max_results: int = 50) -> str:
        """Search files under path for a regular expression and return 'file:line: text' matches."""
        try:
            return fs.search_text(pattern, path, max_results, root=root)
        except fs.SandboxError as exc:
            return f"ERROR: {exc}"

    @tool("run_command")
    def run_command(command: str, cwd: str = ".") -> str:
        """Run an allow-listed shell command (npm test, npm run build, node --test, git status/diff, ls, cat, grep ...) inside the repository. cwd is relative to the repository root, e.g. 'frontend' or 'signaling'."""
        return shell.run_command(command, cwd, timeout=settings.shell_timeout, root=root)

    @tool("git_status")
    def git_status() -> str:
        """Show the git working tree status (short format)."""
        return git.git_status(root)

    @tool("git_diff")
    def git_diff(path: str = "") -> str:
        """Show the current uncommitted diff, optionally limited to a path."""
        return git.git_diff(path, root)

    return {
        "read_file": read_file,
        "write_file": write_file,
        "list_dir": list_dir,
        "search_text": search_text,
        "run_command": run_command,
        "git_status": git_status,
        "git_diff": git_diff,
    }


def role_llm(role_key: str, org: dict[str, Any], settings: Settings, default_llm: Any):
    """역할별 model 오버라이드(org.yaml roles.<role>.model)가 있으면 그 모델로 LLM을 만든다."""
    override = org["roles"][role_key].get("model")
    if not override or override == settings.model:
        return default_llm
    return build_llm(dataclasses.replace(settings, model=str(override)))


def build_agent(role_key: str, org: dict[str, Any], llm: Any, tools: dict[str, Any], settings: Settings | None = None):
    from crewai import Agent  # noqa: WPS433

    spec = org["roles"][role_key]
    missing = [t for t in spec.get("tools", []) if t not in tools]
    if missing:
        raise ValueError(f"role '{role_key}' references unknown tools: {missing}")
    if settings is not None:
        llm = role_llm(role_key, org, settings, llm)
    return Agent(
        role=spec["role"],
        goal=spec["goal"],
        backstory=spec["backstory"].strip(),
        llm=llm,
        tools=[tools[t] for t in spec.get("tools", [])],
        verbose=True,
        allow_delegation=False,
        max_iter=25,
    )
