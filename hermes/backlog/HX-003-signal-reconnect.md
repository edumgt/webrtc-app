---
id: HX-003
title: 시그널링 WebSocket 자동 재연결(지수 백오프)과 연결 상태 UX
priority: P1
area: frontend
status: todo
stages: [pm, design, dev, qa]
acceptance:
  - 비정상 종료(code != 1000) 시 1s→2s→4s… 최대 30s 백오프로 재연결하고 join-room을 재전송한다
  - 사용자가 명시적으로 나가면 재연결하지 않는다
  - connectionState에 reconnecting 상태가 추가되고 App.vue 연결 패널에 시도 횟수가 표시된다
  - 백오프 계산 유틸이 vitest로 검증된다
---
## 배경

시그널링 서버 롤아웃이나 네트워크 순단 시 WebSocket이 닫히면 사용자는 수동으로 다시 입장해야 한다.

## 범위

- `useWebRTC.joinRoom`에 재연결 스케줄러 추가, `leaveRoom()` API 추가
- 재연결 성공 시 기존 피어 연결은 유지, 새 피어 탐색은 new-peer 이벤트로 처리
- 연결 패널 상태 문구/색상

## 참고 파일

- frontend/src/composables/useWebRTC.js
- frontend/src/App.vue (conn-panel)
