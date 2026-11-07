---
id: HX-001
title: 시그널링 서버 테스트 가능 구조로 리팩터링 및 node --test 도입
priority: P0
status: done
area: signaling
stages: [dev, qa]
acceptance:
  - server.cjs가 createSignalingServer()를 export하고, 직접 실행 시에만 listen한다
  - npm test (signaling)로 join-room → new-peer, target 유니캐스트, peer-left가 검증된다
  - 기존 /health 응답과 메시지 포맷이 변하지 않는다
---
## 배경

QA 에이전트가 실제로 실행할 테스트가 없으면 리뷰 루프가 동작하지 않는다.
시그널링 서버는 모듈 로드 시 바로 listen하므로 테스트에서 import할 수 없었다.

## 범위

- `signaling/server.cjs`: 서버 생성 함수 분리, `require.main === module`일 때만 listen
- `signaling/test/server.test.cjs`: ws 클라이언트로 E2E 시나리오 검증
- `signaling/package.json`: `test` 스크립트 추가

## 비고

Hermes 도입 커밋에서 사람이 직접 구현한 부트스트랩 티켓. 이후 티켓의 참고 예시로 사용한다.
