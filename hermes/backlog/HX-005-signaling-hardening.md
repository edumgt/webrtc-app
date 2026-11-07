---
id: HX-005
title: 시그널링 서버 입력 검증·메시지 크기 제한·중복 ID 처리
priority: P2
area: signaling
status: todo
stages: [pm, dev, qa]
acceptance:
  - roomId/sender는 1~64자 영숫자·-_만 허용하고 위반 시 {type:"error", code} 응답 후 무시한다
  - 64KB를 초과하는 메시지는 거부된다 (ws maxPayload)
  - 같은 방에 동일 sender가 다시 join하면 이전 소켓을 정리하고 peer-left를 전파한다
  - 각 규칙이 node --test로 검증된다
---
## 배경

서버는 모든 JSON을 신뢰하고 방/클라이언트 ID를 검증하지 않는다. 악의적 또는 버그성 클라이언트가 메모리를 소모하거나 다른 피어의 ID를 가장할 수 있다.

## 참고 파일

- signaling/server.cjs
- signaling/test/server.test.cjs (HX-001에서 도입)
