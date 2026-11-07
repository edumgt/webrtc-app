# Backlog

Hermes 조직이 처리하는 작업 티켓입니다. 파일 하나가 티켓 하나이며 YAML frontmatter + 마크다운 본문 형식입니다.

```yaml
---
id: HX-010            # 고유 ID (HX-숫자)
title: 제목
priority: P0|P1|P2|P3
status: proposed|todo|in-progress|review|done|blocked
area: frontend|signaling|infra|docs
stages: [pm, design, dev, qa]   # 실행할 단계 (dev가 있으면 qa 필수)
acceptance:
  - 테스트로 검증 가능한 완료 조건
---
```

- 새 티켓: `uv run hermes new HX-010 "제목"`
- 검증: `uv run hermes validate`
- 실행: `uv run hermes run HX-010`
- 상태 전이: proposed →(사람 `hermes approve`)→ todo →(run/daemon)→ in-progress →(QA PASS)→ review →(사람 머지)→ done
  QA FAIL 또는 오류 시 blocked (사람이 티켓을 고쳐 todo로 되돌림)
