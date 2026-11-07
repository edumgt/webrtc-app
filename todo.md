> **구현 현황 (2026-11-07)**: 이 문서의 설계는 [`hermes/`](./hermes/README.md)에 구현되어 있습니다.
> `uv run hermes run <티켓ID>`로 PM → 디자이너 → 개발자 ⇄ QA 파이프라인을 실행하고, 티켓은 [`hermes/backlog/`](./hermes/backlog/)에서 관리합니다.
> 설계 항목별 구현 매핑은 hermes/README.md의 "설계 요약" 표를 참고하세요.

Hermes 모델(Nous Research의 Hermes 시리즈 계열)을 기반으로 사내 소프트웨어 개발사의 조직 구조(PM, 개발자, 디자이너, 테스터)를 구현하는 멀티 에이전트 시스템은 **오케스트레이션 프레임워크 선택**, **역할별 프롬프트 및 도구 정의**, **워크플로우 파이프라인 구성**의 3단계로 구축할 수 있습니다.

---

### 1. 전체 아키텍처 및 권장 프레임워크

Hermes 계열(예: Hermes 2 Pro, Hermes 3)은 함수 호출(Function Calling)과 구조화된 JSON 출력(JSON Mode), 그리고 시스템 프롬프트 준수 능력이 뛰어납니다. 이를 조율하기 위해 다음 오픈소스 멀티 에이전트 프레임워크 중 하나를 사용하는 것이 적합합니다.

* **CrewAI**: 역할 기반(Role-Playing) 협업에 가장 최적화되어 있어 SW 개발사 형태(PM, Dev, Designer, QA)를 직관적으로 구현하기 좋습니다.
* **AutoGen (Microsoft)**: 에이전트 간의 자유 대화형(Group Chat) 또는 상태 머신 기반 대화에 강점이 있습니다.
* **LangGraph**: 상태(State)와 분기(조건부 엣지, 루프, 피드백 반영)를 엄격히 제어해야 할 때 유리합니다.

*로컬 배포 환경:* Ollama, vLLM, 또는 LM Studio를 통해 Hermes 모델을 서빙하고 OpenAI 호환 엔드포인트(`http://localhost:11434/v1` 등)로 연결합니다.

---

### 2. 가상 조직의 역할 분담(RnR) 및 시스템 프롬프트

각 에이전트에게 명확한 목표(Goal), 배경(Backstory), 입출력 규격을 정의합니다.

| 역할 (Role) | 핵심 임무 (Responsibility) | 주요 도구 (Tools) 및 산출물 |
| --- | --- | --- |
| **PM (Product Manager)** | 요구사항 분석, PRD(제품 요구사항 정의서) 작성, 태스크 세분화 및 전체 흐름 조율 | 마크다운 PRD, 작업 티켓/마일스톤 목록 |
| **디자이너 (UI/UX Designer)** | 유저 플로우 설계, 화면 레이아웃 정의, 디자인 시스템 토큰(컬러/타이포) 및 컴포넌트 스펙 도출 | 화면 설계서, Tailwind CSS 스타일 가이드 또는 와이어프레임 구조 |
| **개발자 (Developer)** | 기능 구현, 프로젝트 디렉터리 구성, 모듈별 코드 작성 및 리팩토링 | 코드 생성기, 파일 쓰기/실행 툴, Git 연동 |
| **테스터 (QA Engineer)** | 요구사항 대비 검증, 단위/통합 테스트 코드 작성, 엣지 케이스 분석 및 버그 리포트 | 테스트 실행기(pytest, jest 등), 버그 이슈 티켓 |

---

### 3. CrewAI 기반 파이프라인 구현 예시

다음은 Hermes 모델을 로컬(또는 API 엔드포인트)에 연동하여 순차적 협업 파이프라인을 실행하는 기본 구조입니다.

```python
from crewai import Agent, Crew, Process, Task
from langchain_openai import ChatOpenAI

# 1. Hermes 모델 LLM 세팅 (OpenAI 호환 API)
hermes_llm = ChatOpenAI(
    model="hermes-3-llama-3.1-8b",
    base_url="http://localhost:11434/v1",  # Ollama/vLLM 엔드포인트
    api_key="NA",
    temperature=0.2,
)

# 2. 에이전트 정의 (RnR)
pm_agent = Agent(
    role="Product Manager",
    goal="사용자 요구사항을 분석하여 명확하고 구체적인 PRD 및 작업 명세서를 도출한다.",
    backstory="애자일 소프트웨어 개발 경험이 풍부하며, 기술적 실현 가능성과 비즈니스 가치를 조율하는 시니어 PM.",
    llm=hermes_llm,
    verbose=True,
)

designer_agent = Agent(
    role="UI/UX Designer",
    goal="PRD를 기반으로 직관적인 사용자 흐름과 컴포넌트 UI 스펙을 정의한다.",
    backstory="모던 웹/앱 UI 트렌드에 능통하며 디자인 토큰 및 인터랙션을 구조적으로 문서화하는 디자이너.",
    llm=hermes_llm,
    verbose=True,
)

developer_agent = Agent(
    role="Senior Full-Stack Developer",
    goal="PRD와 UI 스펙에 맞춰 실행 가능한 고품질 코드를 작성한다.",
    backstory="클린 코드와 모듈화를 중요시하며 견고한 소프트웨어 아키텍처를 설계하는 10년 차 엔지니어.",
    llm=hermes_llm,
    verbose=True,
)

qa_agent = Agent(
    role="QA Automation Engineer",
    goal="작성된 코드의 버그를 찾고 엣지 케이스를 테스트하며 검증 보고서를 작성한다.",
    backstory="테스트 주도 개발(TDD)과 엄격한 품질 보증 기준을 가진 꼼꼼한 테스트 엔지니어.",
    llm=hermes_llm,
    verbose=True,
)

# 3. 작업(Task) 정의 및 순서 연결
task_prd = Task(
    description="{project_idea}에 대한 요구사항 명세서(PRD)와 기능 목록을 작성하세요.",
    expected_output="마크다운 형식의 상세 PRD 문서",
    agent=pm_agent,
)

task_design = Task(
    description="PRD를 검토하여 화면 구조, 레이아웃 스펙, 사용자 인터랙션 규칙을 작성하세요.",
    expected_output="UI/UX 상세 스펙 및 컴포넌트 목록",
    agent=designer_agent,
)

task_code = Task(
    description="PRD와 UI 스펙을 기반으로 전체 동작 코드를 작성하세요.",
    expected_output="실행 가능한 파이썬 또는 자바스크립트 코드 스니펫",
    agent=developer_agent,
)

task_test = Task(
    description="구현된 코드를 검증하고 테스트 시나리오 및 테스트 코드를 작성하세요. 버그 발견 시 개선점을 제안하세요.",
    expected_output="테스트 결과 보고서 및 단위 테스트 코드",
    agent=qa_agent,
)

# 4. 크루(가상 회사) 구성 및 실행
software_company = Crew(
    agents=[pm_agent, designer_agent, developer_agent, qa_agent],
    tasks=[task_prd, task_design, task_code, task_test],
    process=Process.sequential,  # 순차 파이프라인
    verbose=True,
)

result = software_company.kickoff(
    inputs={"project_idea": "실시간 마크다운 협업 에디터 웹 애플리케이션"}
)

print(result)

```

---

### 4. 실전 배포 시 핵심 고려사항

1. **피드백 루프(Review Loop) 구성**:
* 단순 순차 진행(`Process.sequential`)을 넘어, QA 단계에서 결함이 발견되었을 때 다시 Developer 에이전트로 작업을 되돌리는 분기 제어가 필요하다면 **LangGraph**를 도입하여 조건부 순환 그래프를 구성하는 것이 안정적입니다.


2. **도구(Tools) 및 환경 격리**:
* Developer나 QA 에이전트가 실제 코드를 실행하고 테스트하려면 Docker 컨테이너나 E2B, Modal 같은 **샌드박스 실행 환경**에 도구(Tool)를 바인딩하여 시스템 보안을 유지해야 합니다.


3. **컨텍스트 윈도우 관리**:
* 각 에이전트 간 주고받는 텍스트(PRD, 코드, 로그)가 누적되면 컨텍스트 제한을 초과할 수 있습니다. 각 단계 산출물을 요약해서 전달하거나, 작업 공간(Workdir) 내 파일로 저장하고 파일 경로를 참조하도록 프롬프트를 설계하는 것이 유리합니다.