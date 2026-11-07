---
id: HX-010
title: useWebRTC.js에서의 예외 처리 개선
priority: P1
status: proposed
area: frontend
stages: [dev, qa]
acceptance:
  - 모든 예외 처리 블록에서 로그 메시지가 포함되어야 합니다.
  - 예외 처리 블록에서 로그 메시지가 포함된 테스트가 추가되어야 합니다.
---
## 배경

useWebRTC.js 파일에서 여러 예외 처리 블록이 있으며, 일부는 로그 메시지가 포함되어 있지 않습니다. 이는 디버깅과 유지보수에 어려움을 초래할 수 있습니다.

## 범위

- useWebRTC.js 파일에서 모든 예외 처리 블록에 로그 메시지를 추가합니다.
- useWebRTC.js 파일에 대한 테스트를 추가하여 예외 처리 블록이 올바르게 작동하는지 확인합니다.

## 참고 파일

- frontend/src/composables/useWebRTC.js

## 출처

Tech Lead 에이전트 제안. 사람이 검토 후 `hermes approve <ID>`로 승인한다.
