# AGENTS.md — 이 저장소에서 일하는 에이전트를 위한 헌장

이 저장소는 사람과 AI 에이전트(Hermes 가상 조직, Copilot, Claude Code, Codex 등)가 함께 고도화합니다.
에이전트는 아래 규칙을 따릅니다. Hermes 조직의 실행 방법은 [hermes/README.md](hermes/README.md)를 보세요.

## 작업 단위

- 모든 변경은 `hermes/backlog/` 티켓(HX-nnn)에서 출발합니다. 티켓이 없으면 먼저 만듭니다: `uv run hermes new HX-nnn "제목"`.
- 티켓 하나 = 브랜치 하나(`hermes/HX-nnn`) = PR 하나. 범위 밖 변경은 새 티켓으로 분리합니다.
- 산출물(PRD, 디자인 스펙, 개발/QA 보고서)은 `hermes/workspace/HX-nnn/`에 남깁니다.

## 자율 모드에서의 역할 분담

- 데몬(`hermes daemon`)은 `todo` 티켓을 브랜치 `hermes/HX-nnn`에서 처리해 커밋하고, 백로그가 비면 Tech Lead가 `status: proposed` 티켓을 제안합니다.
- 하루 한 번(`daemon.merge_at`) QA PASS 브랜치를 테스트·빌드 검증 후 `main`에 자동 머지·push합니다. 검증 실패나 충돌은 머지하지 않고 사람에게 남깁니다.
- **사람만 할 수 있는 것**: 제안 승인(`hermes approve`), 자동 머지 전 리뷰(막으려면 티켓을 `blocked`로), blocked 티켓 처리.
- 확인할 것이 있는지는 `uv run hermes status`로 봅니다.

## 코드 규약

- frontend: Vue 3 `<script setup>`, ESM, 2-space, 세미콜론 없음, Tailwind + CSS 변수(`--surface-2`, `--border`, `--text-primary`).
- signaling: CommonJS 단일 파일(`server.cjs`), 세미콜론 사용. `createSignalingServer()`를 export하고 직접 실행 시에만 listen.
- 의존성 추가는 최소화. 추가 시 `package.json`과 `package-lock.json`을 함께 갱신.
- 사용자 노출 문구는 한국어. 로그/식별자는 영어.

## 완료 정의 (Definition of Done)

1. 티켓의 모든 수용 기준이 테스트로 검증된다.
   - frontend: `npm test` (vitest, `src/**/*.test.js`), `npm run build`
   - signaling: `npm test` (`node --test`, `test/*.test.cjs`)
   - hermes: `uv run pytest`
2. 문서(readme-kr.md / Readme.md / .env.example)가 변경과 일치한다.
3. QA 보고서 마지막 줄이 `VERDICT: PASS`.

## 금지 사항

- `.env`, `.git/`, `node_modules/` 수정 금지. 비밀값을 코드나 문서에 쓰지 않습니다.
- `git push`, 배포/인프라 명령(docker, kubectl, aws) 실행 금지. 배포는 PR 머지 후 GitHub Actions가 수행합니다.
- 파일을 읽지 않고 덮어쓰기 금지. 전체 파일을 다시 쓸 때 무관한 코드를 바꾸지 않습니다.
