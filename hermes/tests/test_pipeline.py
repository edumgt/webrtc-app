from pathlib import Path

import pytest

from hermes_org.agents import load_org
from hermes_org.backlog import Ticket
from hermes_org.pipeline import Pipeline, excerpt
from hermes_org.settings import Settings

TICKET = """---
id: HX-950
title: 파이프라인 테스트
priority: P2
status: todo
area: frontend
stages: [pm, design, dev, qa]
acceptance:
  - A
---
body
"""


def make_pipeline(tmp_path: Path, **kw) -> Pipeline:
    ticket = Ticket.from_markdown(TICKET)
    settings = Settings(repo_root=tmp_path)
    return Pipeline(ticket, settings=settings, org=load_org(), workspace_root=tmp_path / "ws", log=lambda _: None, **kw)


def test_plan_lists_stages_and_review_loop(tmp_path: Path):
    plan = make_pipeline(tmp_path, max_iterations=3).plan()
    assert [s["stage"] for s in plan] == ["pm", "design", "dev", "qa", "review-loop"]
    assert plan[2]["role"] == "Senior Full-Stack Developer"
    assert "write_file" in plan[2]["tools"] and "write_file" not in plan[3]["tools"]
    assert "3회" in plan[4]["output"]


def test_plan_respects_stage_override(tmp_path: Path):
    plan = make_pipeline(tmp_path, stages=["dev", "qa"]).plan()
    assert [s["stage"] for s in plan] == ["dev", "qa", "review-loop"]


def test_unknown_stage_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown stages"):
        make_pipeline(tmp_path, stages=["deploy"])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("...\n| AC-1 | PASS |\nVERDICT: PASS", "PASS"),
        ("...\nVERDICT: FAIL\n", "FAIL"),
        ("VERDICT: PASS 라고 쓰고 싶지만\n결함 있음\nVERDICT: FAIL", "FAIL"),
        ("no verdict here", "UNKNOWN"),
    ],
)
def test_parse_verdict(tmp_path: Path, text: str, expected: str):
    assert make_pipeline(tmp_path).parse_verdict(text) == expected


def test_excerpt_truncates():
    assert excerpt("abc", 10) == "abc"
    assert excerpt("x" * 50, 10).startswith("x" * 10) and "truncated" in excerpt("x" * 50, 10)


def test_org_roles_reference_known_tools():
    org = load_org()
    known = {"read_file", "write_file", "list_dir", "search_text", "run_command", "git_status", "git_diff"}
    for name, role in org["roles"].items():
        assert set(role["tools"]) <= known, name
    assert "VERDICT" in org["review_loop"]["pass_token"]


def test_prompts_mention_artifact_paths():
    from hermes_org import prompts

    text = prompts.dev_task("T", "PRD", "hermes/workspace/X/prd.md", None, None, "QA said FAIL", 2)
    assert "hermes/workspace/X/prd.md" in text and "QA 재작업" in text and "iteration 2" in text
    assert "VERDICT: PASS" in prompts.qa_task("T", "P", "p", "D", "d", 1)


def test_role_llm_override_only_when_model_differs(monkeypatch):
    from hermes_org import agents

    built = []
    monkeypatch.setattr(agents, "build_llm", lambda s: built.append(s.model) or f"llm:{s.model}")
    org = {"roles": {"a": {"model": "other:1b"}, "b": {}, "c": {"model": "base"}}}
    settings = Settings(model="base")
    assert agents.role_llm("a", org, settings, "default") == "llm:other:1b"
    assert agents.role_llm("b", org, settings, "default") == "default"
    assert agents.role_llm("c", org, settings, "default") == "default"
    assert built == ["other:1b"]
