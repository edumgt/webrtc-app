import json
from pathlib import Path

import pytest

from hermes_org.backlog import Ticket, load_tickets, next_ticket_id, write_ticket
from hermes_org.daemon import load_state, pick_next, save_state
from hermes_org.discover import normalize_proposal, parse_proposals, write_proposals


def mk(tid: str, priority: str, status: str = "todo") -> Ticket:
    return Ticket.from_markdown(
        f"---\nid: {tid}\ntitle: t {tid}\npriority: {priority}\nstatus: {status}\narea: docs\nstages: [pm, dev, qa]\nacceptance:\n  - a\n---\nbody\n"
    )


def test_pick_next_prefers_priority_then_id_and_skips_handled():
    tickets = [mk("HX-003", "P1"), mk("HX-002", "P0"), mk("HX-001", "P0"), mk("HX-004", "P0", "proposed"), mk("HX-005", "P0", "review")]
    assert pick_next(tickets, {"tickets": {}}).id == "HX-001"
    assert pick_next(tickets, {"tickets": {"HX-001": {}}}).id == "HX-002"
    assert pick_next(tickets, {"tickets": {"HX-001": {}, "HX-002": {}}}).id == "HX-003"
    assert pick_next(tickets, {"tickets": {"HX-001": {}, "HX-002": {}, "HX-003": {}}}) is None


def test_state_roundtrip(tmp_path: Path):
    f = tmp_path / "s.json"
    assert load_state(f) == {"tickets": {}}
    save_state({"tickets": {"HX-001": {"verdict": "PASS"}}}, f)
    assert json.loads(f.read_text())["tickets"]["HX-001"]["verdict"] == "PASS"
    assert load_state(f)["tickets"]["HX-001"]["verdict"] == "PASS"


def test_next_ticket_id(tmp_path: Path):
    assert next_ticket_id(tmp_path) == "HX-001"
    (tmp_path / "HX-007-x.md").write_text("")
    (tmp_path / "HX-012-y.md").write_text("")
    assert next_ticket_id(tmp_path) == "HX-013"


MODEL_OUTPUT = """여기 제안입니다.
```yaml
- title: 채팅 입력 공백 메시지 전송 방지
  priority: P2
  area: frontend
  stages: [pm, dev]
  acceptance:
    - 공백만 입력하면 전송되지 않는다
  background: ChatBox.vue sendChat은 trim 없이 검사한다 (frontend/src/components/ChatBox.vue:31)
  scope:
    - trim 후 빈 문자열이면 return
  files:
    - frontend/src/components/ChatBox.vue
- title: ""
  priority: P9
  acceptance: []
```
"""


def test_parse_and_normalize_proposals():
    props = parse_proposals(MODEL_OUTPUT)
    assert len(props) == 2
    n = normalize_proposal(props[0])
    assert n["stages"] == ["pm", "dev", "qa"]  # dev → qa 자동 추가
    assert n["priority"] == "P2" and n["area"] == "frontend"
    assert "## 배경" in n["body"] and "ChatBox.vue" in n["body"] and "hermes approve" in n["body"]
    assert normalize_proposal(props[1])["priority"] == "P2"


def test_parse_proposals_without_fence_and_garbage():
    assert parse_proposals("- title: X\n  acceptance: [a]\n")[0]["title"] == "X"
    assert parse_proposals("nothing useful: [") == []


def test_write_proposals_creates_valid_proposed_tickets(tmp_path: Path):
    (tmp_path / "README.md").write_text("ignored")
    logs = []
    created = write_proposals(parse_proposals(MODEL_OUTPUT), tmp_path, log=logs.append)
    assert len(created) == 1 and created[0].name.startswith("HX-001-")
    tickets = load_tickets(tmp_path)
    assert tickets[0].status == "proposed" and tickets[0].stages == ["pm", "dev", "qa"]
    assert any("skip" in m for m in logs)
    # 같은 제목은 중복으로 건너뜀
    assert write_proposals(parse_proposals(MODEL_OUTPUT), tmp_path, log=logs.append) == []


def test_write_ticket_rejects_missing_acceptance(tmp_path: Path):
    from hermes_org.backlog import TicketError

    with pytest.raises(TicketError):
        write_ticket(tmp_path, "HX-001", "x", "P2", "docs", ["pm"], [], "body")


def test_approve_transitions_proposed_to_todo(tmp_path: Path):
    path = write_ticket(tmp_path, "HX-001", "제안", "P2", "docs", ["pm", "dev", "qa"], ["a"], "b", status="proposed")
    t = load_tickets(tmp_path)[0]
    assert t.status == "proposed"
    t.set_status("todo")
    assert load_tickets(tmp_path)[0].status == "todo"
    assert path.read_text().count("status:") == 1


def test_daemon_tick_waits_when_base_dirty(tmp_path: Path, monkeypatch):
    """엔드포인트 OK라도 기준 브랜치가 더럽거나 다른 브랜치면 사람에게 맡기고 대기한다."""
    from hermes_org import daemon as d
    from hermes_org.settings import Settings

    monkeypatch.setattr(d, "check_endpoint", lambda s: {"ok": True})
    monkeypatch.setattr(d.git, "current_branch", lambda root: "feature/x")
    monkeypatch.setattr(d.git, "is_clean", lambda root: False)
    logs = []
    dm = d.Daemon(d.DaemonConfig(once=True), settings=Settings(repo_root=tmp_path), backlog_dir=tmp_path, state_file=tmp_path / "s.json", log=logs.append, sleep=lambda s: None)
    assert dm.tick() is False
    assert any("leaving it for a human" in m for m in logs)


def test_daemon_tick_retries_when_endpoint_down(tmp_path: Path, monkeypatch):
    from hermes_org import daemon as d
    from hermes_org.settings import Settings

    monkeypatch.setattr(d, "check_endpoint", lambda s: {"ok": False, "error": "refused"})
    slept = []
    dm = d.Daemon(d.DaemonConfig(once=True, endpoint_retry_seconds=7), settings=Settings(repo_root=tmp_path), backlog_dir=tmp_path, state_file=tmp_path / "s.json", log=lambda m: None, sleep=slept.append)
    assert dm.tick() is False and slept == [7]


REAL_OUTPUT = """```yaml
- title: 시그널링 서버 입력 검증 및 중복 ID 처리
  priority: P1
  area: signaling
  stages: [pm, dev, qa]
  acceptance:
    - 중복 사용자 ID가 서버에 등록되지 않음
  background: 현재 서버는 검증하지 않습니다. 관련 파일 경로: signaling/server.cjs
  files:
    - signaling/server.cjs
```"""


def test_parse_repairs_unquoted_colon_in_value():
    props = parse_proposals(REAL_OUTPUT)
    assert len(props) == 1
    assert props[0]["background"].endswith("signaling/server.cjs")


def test_similarity_flags_near_duplicate_titles():
    from hermes_org.discover import similarity

    assert similarity("시그널링 서버 입력 검증 및 중복 ID 처리", "시그널링 서버 입력 검증·메시지 크기 제한·중복 ID 처리") >= 0.5
    assert similarity("채팅 공백 메시지 전송 방지", "ICE 서버(TURN) 설정을 런타임 환경변수로 주입") < 0.5


def test_write_proposals_skips_near_duplicates_and_missing_files(tmp_path: Path):
    write_ticket(tmp_path, "HX-005", "시그널링 서버 입력 검증·메시지 크기 제한·중복 ID 처리", "P2", "signaling", ["pm", "dev", "qa"], ["a"], "b", status="todo")
    logs = []
    assert write_proposals(parse_proposals(REAL_OUTPUT), tmp_path, log=logs.append, repo_root=tmp_path) == []
    assert any("duplicate" in m for m in logs)

    fresh = [{"title": "전혀 다른 새 제안", "acceptance": ["x"], "files": ["does/not/exist.js"], "background": "b"}]
    assert write_proposals(fresh, tmp_path, log=logs.append, repo_root=tmp_path) == []
    assert any("cited files" in m for m in logs)
    (tmp_path / "exists.js").write_text("")
    fresh[0]["files"] = ["exists.js:12"]
    assert len(write_proposals(fresh, tmp_path, log=logs.append, repo_root=tmp_path)) == 1


def test_repo_digest_lists_sources_untested_and_markers(tmp_path: Path):
    from hermes_org.discover import discover_prompt, repo_digest

    (tmp_path / "signaling").mkdir()
    (tmp_path / "signaling" / "server.cjs").write_text("a\n// TODO: fix\nb\n")
    (tmp_path / "signaling" / "util.cjs").write_text("x\n")
    (tmp_path / "signaling" / "test").mkdir()
    (tmp_path / "signaling" / "test" / "server.test.cjs").write_text("")
    d = repo_digest(tmp_path)
    assert "signaling/server.cjs (3 lines)" in d and "signaling/util.cjs" in d
    assert "- signaling/util.cjs" in d.split("테스트가 없는")[1]
    assert "server.cjs" not in d.split("테스트가 없는")[1].split("주석 마커")[0]
    assert "signaling/server.cjs:2: // TODO: fix" in d
    assert "저장소 분석 자료" in discover_prompt({"project": {"name": "p", "description": "d"}}, [], 2, d)


def test_real_repo_digest_is_bounded():
    from hermes_org.discover import repo_digest
    from hermes_org.settings import REPO_ROOT

    d = repo_digest(REPO_ROOT)
    assert len(d) <= 5000 and "useWebRTC.js" in d
