"""티켓 단위 파이프라인: PM → Designer → Developer ⇄ QA(리뷰 루프)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import prompts
from .agents import build_agent, build_tools, load_org
from .backlog import Ticket
from .llm import build_llm
from .settings import WORKSPACE_DIR, Settings
from .tools import git

Logger = Callable[[str], None]


@dataclass
class StageResult:
    stage: str
    iteration: int
    output_path: Path
    text: str
    seconds: float


@dataclass
class RunResult:
    ticket_id: str
    passed: bool | None
    iterations: int
    stages: list[StageResult] = field(default_factory=list)
    branch: str | None = None
    commit: str | None = None

    @property
    def workspace(self) -> Path | None:
        return self.stages[0].output_path.parent if self.stages else None


def excerpt(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (truncated, {len(text)} chars total)"


class Pipeline:
    def __init__(
        self,
        ticket: Ticket,
        settings: Settings | None = None,
        org: dict[str, Any] | None = None,
        stages: list[str] | None = None,
        max_iterations: int | None = None,
        workspace_root: Path = WORKSPACE_DIR,
        log: Logger = print,
    ) -> None:
        self.ticket = ticket
        self.settings = settings or Settings.from_env()
        self.org = org or load_org()
        self.stages = stages or ticket.stages
        self.max_iterations = max_iterations or self.settings.max_iterations
        self.workspace = workspace_root / ticket.id
        self.log = log
        self._llm = None
        self._tools: dict[str, Any] | None = None
        unknown = [s for s in self.stages if s not in self.org["stages"]]
        if unknown:
            raise ValueError(f"unknown stages {unknown}; org.yaml defines {list(self.org['stages'])}")

    # ---------- 계획(LLM 미사용) ----------
    def plan(self) -> list[dict[str, Any]]:
        steps = []
        for stage in self.stages:
            spec = self.org["stages"][stage]
            role = self.org["roles"][spec["role"]]
            steps.append(
                {
                    "stage": stage,
                    "role": role["role"],
                    "tools": role.get("tools", []),
                    "output": str((self.workspace / spec["output"]).relative_to(self.settings.repo_root)),
                }
            )
        if "dev" in self.stages and "qa" in self.stages:
            steps.append(
                {
                    "stage": "review-loop",
                    "role": "Developer ⇄ QA",
                    "tools": [],
                    "output": f"QA FAIL 시 dev→qa 재실행, 최대 {self.max_iterations}회",
                }
            )
        return steps

    # ---------- 실행 ----------
    def run(self, create_branch: bool = True, commit: bool = False) -> RunResult:
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "logs").mkdir(exist_ok=True)
        result = RunResult(ticket_id=self.ticket.id, passed=None, iterations=0)

        if create_branch:
            if not git.is_clean(self.settings.repo_root):
                raise RuntimeError("working tree is not clean; commit/stash first or pass --no-branch")
            result.branch = git.ensure_branch(f"hermes/{self.ticket.id}", self.settings.repo_root)
            self.log(f"[git] on branch {result.branch}")

        self.ticket.set_status("in-progress")
        ticket_text = self.ticket.to_prompt()
        limit = int(self.org["review_loop"].get("artifact_excerpt_chars", 6000))
        artifacts: dict[str, StageResult] = {}

        if "pm" in self.stages:
            artifacts["pm"] = self._run_stage("pm", 1, prompts.pm_task(ticket_text, self.org["project"]))
            result.stages.append(artifacts["pm"])

        prd_excerpt, prd_path = self._artifact(artifacts, "pm", limit)

        if "design" in self.stages:
            artifacts["design"] = self._run_stage("design", 1, prompts.design_task(ticket_text, prd_excerpt, prd_path))
            result.stages.append(artifacts["design"])

        design_excerpt, design_path = self._artifact(artifacts, "design", limit)

        qa_feedback: str | None = None
        iteration = 0
        if "dev" in self.stages:
            while True:
                iteration += 1
                result.iterations = iteration
                dev = self._run_stage(
                    "dev",
                    iteration,
                    prompts.dev_task(ticket_text, prd_excerpt, prd_path, design_excerpt, design_path, qa_feedback, iteration),
                )
                result.stages.append(dev)
                if "qa" not in self.stages:
                    break
                qa = self._run_stage(
                    "qa",
                    iteration,
                    prompts.qa_task(ticket_text, prd_excerpt, prd_path, excerpt(dev.text, limit), self._rel(dev.output_path), iteration),
                )
                result.stages.append(qa)
                verdict = self.parse_verdict(qa.text)
                self.log(f"[qa] iteration {iteration} verdict: {verdict}")
                if verdict == "PASS":
                    result.passed = True
                    break
                if iteration >= self.max_iterations:
                    result.passed = False
                    break
                qa_feedback = excerpt(qa.text, limit)
        elif "qa" in self.stages:
            qa = self._run_stage("qa", 1, prompts.qa_task(ticket_text, prd_excerpt, prd_path, "(개발 단계 없음)", "-", 1))
            result.stages.append(qa)
            result.passed = self.parse_verdict(qa.text) == "PASS"

        self._write_summary(result)
        # QA PASS → review(사람 검토 대기). FAIL 또는 dev/qa 미실행 → in-progress 유지
        self.ticket.set_status("review" if result.passed else "in-progress")

        if commit:
            msg = f"hermes({self.ticket.id}): {self.ticket.title}\n\nQA verdict: {result.passed}\n\nCo-Authored-By: Hermes Org <hermes@local>"
            result.commit = git.commit_all(msg, self.settings.repo_root)
            self.log(f"[git] {result.commit}")
        return result

    # ---------- 내부 ----------
    def parse_verdict(self, text: str) -> str:
        loop = self.org["review_loop"]
        tail = text.strip().splitlines()[-5:] if text.strip() else []
        for line in reversed(tail):
            if loop["pass_token"] in line:
                return "PASS"
            if loop["fail_token"] in line:
                return "FAIL"
        return "FAIL" if loop["fail_token"] in text else ("PASS" if loop["pass_token"] in text else "UNKNOWN")

    def _artifact(self, artifacts: dict[str, StageResult], stage: str, limit: int) -> tuple[str | None, str | None]:
        if stage not in artifacts:
            # 이전 실행 산출물이 있으면 재사용(단계 생략 실행 지원)
            spec = self.org["stages"].get(stage)
            if spec:
                path = self.workspace / spec["output"]
                if path.exists():
                    return excerpt(path.read_text(encoding="utf-8"), limit), self._rel(path)
            return (None, None) if stage == "design" else ("(PRD 없음: 티켓 본문을 기준으로 작업)", "-")
        art = artifacts[stage]
        return excerpt(art.text, limit), self._rel(art.output_path)

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.settings.repo_root))

    def _ensure_llm(self) -> None:
        if self._llm is None:
            self._llm = build_llm(self.settings)
            self._tools = build_tools(self.settings)

    def _run_stage(self, stage: str, iteration: int, description: str) -> StageResult:
        from crewai import Crew, Process, Task  # noqa: WPS433

        self._ensure_llm()
        spec = self.org["stages"][stage]
        suffix = "" if iteration == 1 else f".iter{iteration}"
        output_path = self.workspace / spec["output"].replace(".md", f"{suffix}.md")
        self.log(f"[{stage}] iteration {iteration} → {self._rel(output_path)}")

        agent = build_agent(spec["role"], self.org, self._llm, self._tools or {}, settings=self.settings)
        task = Task(description=description, expected_output="마크다운 문서", agent=agent)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)

        started = time.time()
        output = crew.kickoff(inputs={"ticket_id": self.ticket.id})
        text = getattr(output, "raw", None) or str(output)
        seconds = time.time() - started

        output_path.write_text(text.strip() + "\n", encoding="utf-8")
        self._event({"stage": stage, "iteration": iteration, "seconds": round(seconds, 1), "output": self._rel(output_path), "chars": len(text)})
        return StageResult(stage=stage, iteration=iteration, output_path=output_path, text=text, seconds=seconds)

    def _event(self, payload: dict[str, Any]) -> None:
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **payload}
        with (self.workspace / "logs" / "run.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _write_summary(self, result: RunResult) -> None:
        lines = [
            f"# Run Summary: {self.ticket.id} {self.ticket.title}",
            "",
            f"- model: {self.settings.litellm_model} @ {self.settings.base_url}",
            f"- branch: {result.branch or '(current)'}",
            f"- iterations: {result.iterations}",
            f"- verdict: {'PASS' if result.passed else 'FAIL' if result.passed is False else 'N/A'}",
            "",
            "| stage | iter | seconds | output |",
            "|---|---|---|---|",
        ]
        for s in result.stages:
            lines.append(f"| {s.stage} | {s.iteration} | {s.seconds:.0f} | {self._rel(s.output_path)} |")
        (self.workspace / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
