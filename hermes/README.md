# Hermes 가상 소프트웨어 조직

[todo.md](../todo.md)의 설계를 구현한 멀티 에이전트 파이프라인입니다.
Hermes 모델(Nous Research Hermes 3 등, OpenAI 호환 엔드포인트)을 LLM으로 사용하는
**PM → 디자이너 → 개발자 ⇄ QA** 조직이 `hermes/backlog/`의 티켓을 받아 저장소를 고도화합니다.

```
hermes/
├── backlog/            # 작업 티켓 (YAML frontmatter + 마크다운). 조직의 입력
├── config/org.yaml     # 역할(RnR)·도구·파이프라인 단계·리뷰 루프 정의
├── hermes_org/         # 파이썬 패키지
│   ├── cli.py          #   hermes check|backlog|validate|plan|run|new|daemon|discover|approve|status
│   ├── daemon.py       #   자율 모드: 백로그 순회, 브랜치 커밋, 발굴, 대기
│   ├── discover.py     #   Tech Lead 역할: 새 티켓 제안(proposed)
│   ├── pipeline.py     #   티켓 실행 오케스트레이터 (QA FAIL → Dev 재작업 루프)
│   ├── agents.py       #   org.yaml → CrewAI Agent, 도구 바인딩
│   ├── prompts.py      #   단계별 Task 프롬프트
│   ├── backlog.py      #   티켓 로딩/검증/상태 전이
│   ├── llm.py          #   LLM 연결 및 엔드포인트 점검
│   └── tools/          #   샌드박스 도구: fs(읽기/쓰기/검색), shell(허용 목록), git(읽기 전용)
├── workspace/<ID>/     # 실행 산출물: prd.md, design.md, dev-report.md, qa-report.md, summary.md
├── systemd/            # WSL 부팅 자동 시작 유닛 (scripts/install-hermes-daemon.sh)
└── tests/              # pytest (LLM 없이 실행)
```

## 설계 요약 (todo.md ↔ 구현)

| todo.md 항목 | 구현 |
|---|---|
| 오케스트레이션 프레임워크 | **CrewAI** (역할 기반). 단계마다 단일 Agent/Task Crew를 순차 실행 |
| 피드백 루프 (QA → Dev) | `pipeline.py`가 QA 보고서의 `VERDICT: PASS/FAIL`을 읽어 Dev 단계를 최대 `HERMES_MAX_ITERATIONS`회 재실행. LangGraph 없이 파이썬 제어 흐름으로 구현 |
| 도구 및 환경 격리 | 모든 도구가 저장소 루트로 샌드박싱. `.env`/`.git`/`node_modules` 접근 차단, 셸은 허용 목록(`npm test`, `npm run build`, `node --test`, `git status/diff` 등)만 실행 |
| 컨텍스트 윈도우 관리 | 단계 산출물은 파일로 저장하고 다음 단계에는 **발췌(6,000자) + 파일 경로**만 전달. 에이전트는 필요 시 `read_file`로 추가 조회 |
| 로컬 서빙 | Ollama 기본 (`hermes3:8b`), vLLM/LM Studio/OpenRouter 등 OpenAI 호환 API 지원 |

## 다른 PC에서 받아 쓰기 (이식성)

저장소에는 기계 종속 정보가 없습니다. 아래만 갖추면 같은 방식으로 동작합니다.

| 필요 | 비고 |
|---|---|
| git, Node 20+, uv (Python 3.10~3.13) | `uv sync`가 가상환경을 자동 생성 |
| Ollama + 모델 2개 | `ollama pull hermes3:8b`, `ollama pull qwen2.5-coder:7b` (Tech Lead용, 약 9GB 다운로드) |
| `hermes/.env` | `cp .env.example .env`. Ollama가 같은 기계면 수정 불필요. WSL에서 Windows Ollama를 쓰면 `OLLAMA_HOST=<게이트웨이IP>:11434`를 셸에 export하거나 `.env`의 `HERMES_BASE_URL`에 지정 |
| 작업 트리 깨끗 | 데몬은 `main`이 깨끗할 때만 브랜치를 만듭니다 |

```bash
git clone <repo> && cd webrtc-app
(cd signaling && npm ci) && (cd frontend && npm ci)
cd hermes && cp .env.example .env && uv sync --extra dev
uv run hermes check      # 엔드포인트, 모델 2개, org.yaml, 백로그를 모두 검증
uv run hermes status
```

기계마다 달라지는 것:

- **처리 기록** `workspace/daemon-state.json`은 커밋되지 않습니다. 새 PC는 `main`의 티켓 상태(`todo`)만 보고 시작하므로, 이전 PC에서 처리한 `hermes/HX-nnn` 브랜치를 **push**해 두고 머지(또는 티켓 `done`)해야 중복 처리가 없습니다.
- **속도**: GPU 메모리에 따라 수 분에서 수십 분까지 차이가 납니다. GPU가 없으면 CPU 추론으로 매우 느립니다.
- **자동 시작**: systemd 유닛의 경로와 Ollama 주소는 `scripts/install-hermes-daemon.sh`가 그 PC에 맞게 다시 씁니다. macOS는 launchd, Windows 네이티브는 작업 스케줄러를 써야 하며(유닛 미제공), Windows 네이티브에서의 셸 도구 동작은 검증되지 않았습니다. Linux/WSL/macOS를 기준으로 합니다.

## 시작하기

```bash
# 1) 모델 준비 (Ollama)
ollama pull hermes3:8b

# 2) 파이썬 환경 (uv)
cd hermes
cp .env.example .env           # 필요 시 엔드포인트/모델 변경
uv sync --extra dev

# (선택) 전역 명령으로 설치: 이후 어디서든 `hermes <command>`
uv tool install --editable ./hermes     # 저장소 루트에서. 제거: uv tool uninstall hermes-org

# 3) 점검
uv run hermes check            # 엔드포인트, 모델, org.yaml, 백로그 검증
uv run hermes backlog          # 티켓 목록
uv run hermes plan HX-002      # 실행 계획(LLM 미사용)

# 4) 실행
uv run hermes run HX-002                 # hermes/HX-002 브랜치 생성 후 PM→Design→Dev⇄QA
uv run hermes run HX-002 --commit        # 완료 후 자동 커밋
uv run hermes run HX-002 --stages dev,qa # 이전 PRD/디자인 산출물을 재사용해 일부 단계만
uv run hermes run HX-002 --no-branch     # 현재 브랜치에서 작업
```

실행 중 콘솔에 각 에이전트의 사고/도구 호출이 출력되고, 산출물은 `workspace/<ID>/`에,
이벤트 로그는 `workspace/<ID>/logs/run.jsonl`에 기록됩니다. 종료 코드는 QA PASS면 0, FAIL이면 2입니다.

### OpenAI 호환 서버(vLLM 등) 사용

```env
HERMES_LLM_PROVIDER=openai
HERMES_MODEL=NousResearch/Hermes-3-Llama-3.1-8B
HERMES_BASE_URL=http://localhost:8000/v1
HERMES_API_KEY=NA
```

## 자율 모드 (데몬) — 사람은 승인과 머지만

```bash
uv run hermes daemon             # 백로그 순회 (Ctrl+C로 중지)
uv run hermes daemon --once      # 한 사이클만 (테스트용)
uv run hermes status             # 사람이 확인할 항목 요약
uv run hermes pause / resume     # 일시정지 / 재개
# 저장소 루트에서는 scripts/hermes <command>
```

데몬이 하는 일 (한 사이클):

1. LLM 엔드포인트 확인. 끊겨 있으면 60초 후 재시도.
2. 기준 브랜치(`main`)로 돌아가 작업 트리가 깨끗한지 확인. 더러우면 사람에게 맡기고 대기.
3. `todo` 티켓 중 우선순위(P0 먼저)가 가장 높은 것을 골라 `hermes/<ID>` 브랜치에서 PM → Design → Dev ⇄ QA 실행 후 **브랜치에 커밋**.
   - QA PASS → 티켓 `review`, FAIL/오류 → `blocked`. 처리 기록은 `workspace/daemon-state.json`.
4. `todo`가 비면 **Tech Lead** 에이전트가 저장소를 분석해 새 티켓을 `status: proposed`로 제안하고 기준 브랜치에 커밋 (승인 대기 티켓이 5개 이상이면 쉼).
5. 할 일이 없으면 10분 대기 후 반복. 작동 시간대(`active_hours`) 밖이거나 PAUSE 파일이 있으면 새 작업을 시작하지 않습니다.

데몬이 **하지 않는** 일: `main`에 머지, `git push`, 제안 티켓 자동 승인. 사람이 하는 일:

| 상황 | 사람의 행동 |
|---|---|
| `hermes status`에 승인 대기(proposed) | 티켓 파일을 읽고 `uv run hermes approve HX-0nn` (거절은 파일 삭제 또는 `status: blocked`) |
| 리뷰 대기(review) | `git diff main..hermes/HX-0nn`와 `workspace/HX-0nn/qa-report.md` 검토 → PR/머지 → 티켓 `status: done` |
| 막힘(blocked) | 브랜치의 산출물을 보고 티켓을 고쳐 `status: todo`로 되돌리거나 폐기. `daemon-state.json`에서 해당 ID를 지우면 재시도 |

### PC 성능 보호: 작동 시간대와 일시정지

- **작동 시간대**: `config/org.yaml`의 `daemon.active_hours`(기본 `"01:00-07:00"`). 이 시간 밖에서는 새 티켓을 시작하지 않고 대기합니다. 진행 중이던 티켓은 끝까지 마칩니다. 자정을 넘는 구간(`"22:00-06:00"`)도 됩니다. 항상 돌리려면 빈 문자열로 두거나 `--active-hours ""`.
- **일시정지**: `scripts/hermes pause` (PAUSE 파일 생성) / `scripts/hermes resume`. 일시정지 중엔 LLM 엔드포인트도 두드리지 않습니다. `hermes status` 첫 줄에 표시됩니다.
- **우선순위**: systemd 유닛은 `Nice=10`, I/O는 idle 클래스로 돌아 다른 작업에 양보합니다.
- **추론 부하는 Windows 쪽 Ollama**에서 발생합니다. GPU 메모리를 비워 두면(다른 GPU 앱 종료) CPU 점유가 크게 줄고, Windows 환경변수 `OLLAMA_KEEP_ALIVE=1m`(유휴 시 모델 언로드), `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_THREAD=4`(CPU 추론 시)를 권합니다. WSL 자체 상한은 `%USERPROFILE%\.wslconfig`의 `memory=8GB`, `processors=4`.

### WSL 부팅 시 자동 시작 (systemd)

```bash
sudo scripts/install-hermes-daemon.sh
# systemd가 꺼져 있으면 /etc/wsl.conf에 [boot] systemd=true를 추가하고 안내를 출력한다.
# PowerShell에서 `wsl --shutdown` 후 WSL을 다시 열고 같은 스크립트를 한 번 더 실행하면 서비스가 등록·시작된다.
systemctl status hermes-daemon
tail -f hermes/workspace/daemon.log
```

유닛 파일: `hermes/systemd/hermes-daemon.service`. Ollama가 Windows 호스트에서 돌면 `OLLAMA_HOST`가 WSL 기본 게이트웨이(`172.29.32.1:11434`)로 설정됩니다.
Windows의 Ollama가 꺼져 있으면 데몬은 멈추지 않고 60초마다 재시도합니다.

## 수동 운영 흐름 (사람 ↔ 조직)

1. **티켓 작성** — `uv run hermes new HX-010 "제목"` 후 배경/범위/수용 기준을 채운다. 수용 기준은 테스트로 검증 가능한 문장으로.
2. **실행** — `uv run hermes run HX-010 --commit`. 브랜치 `hermes/HX-010`에 코드와 산출물이 커밋된다.
3. **리뷰** — 사람이 `workspace/HX-010/qa-report.md`와 diff를 검토하고 PR을 연다. GitHub Actions `ci.yml`이 테스트/빌드를 다시 검증한다.
4. **머지** — 머지 후 티켓 `status: done`으로 변경.

GitHub에서 실행하려면 `.github/workflows/hermes-ticket.yml`(workflow_dispatch)에 티켓 ID를 입력합니다.
Secrets `HERMES_BASE_URL`, `HERMES_API_KEY`, Variables `HERMES_MODEL`, `HERMES_LLM_PROVIDER`가 필요합니다.

## 조직 커스터마이징

- 역할 추가/수정: `config/org.yaml`의 `roles`에 role/goal/backstory/tools 정의, `stages`에 단계 추가.
- 도구 추가: `hermes_org/tools/`에 순수 함수 작성 → `agents.py.build_tools`에서 `@tool`로 래핑 → `org.yaml`에서 역할에 부여.
- 프롬프트: `hermes_org/prompts.py`.
- 셸 허용 명령: `hermes_org/tools/shell.py`의 `ALLOWED_COMMANDS`.

## 테스트

```bash
uv run pytest            # hermes 자체 테스트 (LLM 불필요)
cd ../signaling && npm test
cd ../frontend && npm test && npm run build
```

## 한계와 주의

- 8B 모델은 긴 파일 전체 재작성에서 실수할 수 있습니다. 티켓 범위를 작게 쪼개고, `--max-iter`를 늘리기보다 수용 기준을 명확히 하는 편이 효과적입니다.
- 에이전트는 `git push`, 네트워크, 컨테이너 명령을 실행할 수 없습니다. 배포는 사람이 PR을 머지해 CI/CD로 수행합니다.
- `run`은 작업 트리가 깨끗할 때만 브랜치를 만듭니다. 변경 사항이 있으면 먼저 커밋하거나 `--no-branch`를 사용하세요.
