import subprocess
from pathlib import Path

import pytest

from hermes_org.tools import fs, shell


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.js").write_text("line1\nconst x = 1\nline3\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    return tmp_path


def test_read_file_with_line_numbers(repo: Path):
    out = fs.read_file("src/a.js", root=repo)
    assert "    1| line1" in out and "    2| const x = 1" in out


def test_read_file_paging(repo: Path):
    out = fs.read_file("src/a.js", start_line=2, max_lines=1, root=repo)
    assert "const x" in out and "line1" not in out and "start_line=3" in out


def test_write_file_creates_dirs(repo: Path):
    assert fs.write_file("src/deep/b.js", "ok", root=repo).startswith("OK")
    assert (repo / "src" / "deep" / "b.js").read_text() == "ok"


@pytest.mark.parametrize("path", ["../outside.txt", ".env", "node_modules/x.js", ".git/config"])
def test_sandbox_denies(repo: Path, path: str):
    (repo / ".git").mkdir(exist_ok=True)
    with pytest.raises(fs.SandboxError):
        fs.resolve_in_repo(path, repo)


def test_env_example_allowed(repo: Path):
    (repo / ".env.example").write_text("X=\n")
    assert fs.read_file(".env.example", root=repo).strip().endswith("X=")


def test_list_dir_and_search(repo: Path):
    tree = fs.list_dir(".", depth=2, root=repo)
    assert "src/" in tree and "node_modules" not in tree
    hits = fs.search_text(r"const \w+", "src", root=repo)
    assert hits == "src/a.js:2: const x = 1"


@pytest.mark.parametrize(
    "cmd,ok",
    [
        ("npm test", True),
        ("npm run build", True),
        ("node --test test/", True),
        ("git status --short", True),
        ("rm -rf /", False),
        ("npm test && rm -rf x", False),
        ("curl http://x", False),
        ("git push origin main", False),
        ("node script.js", False),
    ],
)
def test_shell_allowlist(cmd: str, ok: bool):
    assert shell.is_allowed(cmd) is ok


def test_run_command_executes_in_repo(repo: Path):
    out = shell.run_command("ls src", ".", root=repo)
    assert "(exit code 0)" in out and "a.js" in out


def test_run_command_rejects_outside_cwd(repo: Path):
    assert shell.run_command("ls", "..", root=repo).startswith("ERROR")


def test_run_command_rejects_forbidden(repo: Path):
    assert shell.run_command("rm -rf src", ".", root=repo).startswith("ERROR: command not allowed")
