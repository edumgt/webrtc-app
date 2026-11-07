"""단계별 Task 프롬프트. 산출물은 파일 경로로 전달해 컨텍스트 창을 절약한다."""
from __future__ import annotations

COMMON_RULES = """
## 공통 규칙
- 저장소 루트 기준 상대 경로를 사용한다. 파일을 수정하기 전에 반드시 read_file로 현재 내용을 읽는다.
- 필요한 정보만 읽는다. 큰 파일은 start_line/max_lines로 나눠 읽는다.
- 최종 답변(Final Answer)은 마크다운 문서 본문만 출력한다. 도구 호출 로그나 사족을 넣지 않는다.
- 한국어로 작성하되 코드, 파일 경로, 명령어는 원문을 유지한다.
"""


def pm_task(ticket_text: str, project: dict) -> str:
    conventions = "\n".join(f"- {c}" for c in project.get("conventions", []))
    return f"""
당신은 '{project['name']}' 프로젝트의 PM입니다. 아래 티켓을 분석하고 PRD를 작성하세요.

{ticket_text}

## 프로젝트 개요
{project['description'].strip()}

## 프로젝트 규약
{conventions}

## 해야 할 일
1. list_dir / read_file / search_text로 티켓과 관련된 현재 구현을 확인한다.
2. 아래 구조의 PRD를 작성한다.

```
# PRD: <티켓 ID> <제목>
## 1. 배경과 문제 정의
## 2. 목표 / 비목표
## 3. 현재 구현 분석 (관련 파일과 핵심 로직 요약, 파일 경로 명시)
## 4. 요구사항 (기능/비기능, 각 항목에 R-1, R-2 ... 번호)
## 5. 수용 기준 (각 항목이 테스트로 검증 가능하도록, AC-1, AC-2 ...)
## 6. 작업 분해 (WBS: 단계, 담당 역할, 산출물, 수정 예상 파일)
## 7. 리스크와 열린 질문
```
{COMMON_RULES}
"""


def design_task(ticket_text: str, prd_excerpt: str, prd_path: str) -> str:
    return f"""
당신은 UI/UX 디자이너입니다. PRD를 바탕으로 화면/컴포넌트 스펙을 작성하세요.

{ticket_text}

## PRD (발췌, 전체는 {prd_path})
{prd_excerpt}

## 해야 할 일
1. 관련 Vue 컴포넌트(frontend/src/components, App.vue)와 style.css를 읽고 기존 시각 언어를 파악한다.
2. 아래 구조의 디자인 스펙을 작성한다.

```
# Design Spec: <티켓 ID> <제목>
## 1. 사용자 흐름 (단계별, 상태 전이)
## 2. 화면/컴포넌트 구조 (컴포넌트 트리, props/emit, 신규/수정 구분)
## 3. 상태별 UI 규칙 (idle / loading / progress / success / error 등)
## 4. 스타일 토큰 (기존 CSS 변수 재사용, 신규 토큰은 명시)
## 5. 접근성 및 반응형 (aria, 키보드, 모바일 폭)
## 6. 문구 (사용자에게 노출되는 한국어 문구 목록)
```
백엔드/인프라 전용 티켓이면 UI 변경이 없음을 명시하고 운영자 관점의 로그/설정 UX만 정의한다.
{COMMON_RULES}
"""


def dev_task(
    ticket_text: str,
    prd_excerpt: str,
    prd_path: str,
    design_excerpt: str | None,
    design_path: str | None,
    qa_feedback: str | None,
    iteration: int,
) -> str:
    design_block = (
        f"## 디자인 스펙 (발췌, 전체는 {design_path})\n{design_excerpt}\n" if design_excerpt else "## 디자인 스펙\n(이 티켓은 디자인 단계가 없음)\n"
    )
    rework_block = ""
    if qa_feedback:
        rework_block = f"""
## ⚠️ QA 재작업 요청 (iteration {iteration})
이전 구현이 QA에서 FAIL 판정을 받았습니다. 아래 보고서의 결함을 모두 해결하세요.
{qa_feedback}
"""
    return f"""
당신은 시니어 풀스택 개발자입니다. PRD와 디자인 스펙에 따라 저장소 코드를 실제로 수정하세요.

{ticket_text}

## PRD (발췌, 전체는 {prd_path})
{prd_excerpt}

{design_block}
{rework_block}
## 작업 절차 (반드시 순서대로)
1. git_status로 작업 트리를 확인하고, list_dir/read_file로 수정 대상 파일의 현재 내용을 읽는다.
2. write_file로 파일을 수정한다. 파일 전체를 다시 쓰되 무관한 부분은 바꾸지 않는다.
3. 새 동작에 대한 테스트를 추가한다 (frontend: `frontend/src/**/*.test.js` + vitest, signaling: `signaling/test/*.test.cjs` + node --test).
4. run_command로 테스트와 빌드를 실행해 통과를 확인한다.
   - `npm test` (cwd: signaling), `npm test` (cwd: frontend), `npm run build` (cwd: frontend)
   - node_modules가 없으면 먼저 `npm ci` 또는 `npm install`을 실행한다.
5. 실패하면 원인을 고치고 다시 실행한다. 통과할 때까지 반복한다.

## 최종 보고서 형식
```
# Dev Report: <티켓 ID> (iteration {iteration})
## 변경 파일
- path — 변경 요약
## 구현 요약 (요구사항 R-n / 수용 기준 AC-n 과의 매핑)
## 테스트 결과 (실행한 명령과 결과 요약)
## 남은 이슈 / 후속 작업
```
{COMMON_RULES}
"""


def qa_task(ticket_text: str, prd_excerpt: str, prd_path: str, dev_excerpt: str, dev_path: str, iteration: int) -> str:
    return f"""
당신은 QA 자동화 엔지니어입니다. 개발 결과가 수용 기준을 만족하는지 검증하세요.

{ticket_text}

## PRD (발췌, 전체는 {prd_path})
{prd_excerpt}

## 개발 보고서 (발췌, 전체는 {dev_path})
{dev_excerpt}

## 검증 절차
1. git_status / git_diff로 실제 변경 내용을 읽는다. 보고서가 아닌 diff를 기준으로 판단한다.
2. run_command로 테스트와 빌드를 직접 실행한다.
   - `npm test` (cwd: signaling), `npm test` (cwd: frontend), `npm run build` (cwd: frontend)
   - node_modules가 없으면 먼저 `npm ci`를 실행한다.
3. 수용 기준(AC-n)마다 PASS/FAIL과 근거(테스트 이름, diff 위치, 재현 절차)를 기록한다.
4. 엣지 케이스(빈 입력, 연결 끊김, 대용량, 동시성)를 점검하고 빠진 테스트를 지적한다.

## 보고서 형식
```
# QA Report: <티켓 ID> (iteration {iteration})
## 실행한 명령과 결과
## 수용 기준 검증표
| AC | 결과 | 근거 |
## 발견된 결함 (심각도, 재현 절차, 기대/실제)
## 개선 제안
VERDICT: PASS   ← 또는 VERDICT: FAIL (반드시 마지막 줄, 둘 중 하나만)
```
모든 수용 기준이 PASS이고 테스트/빌드가 통과할 때만 VERDICT: PASS를 쓴다.
{COMMON_RULES}
"""
