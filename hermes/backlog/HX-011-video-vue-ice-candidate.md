---
id: HX-011
title: Video.vue에서의 ICE candidate 추가 실패 처리 개선
priority: P1
status: proposed
area: frontend
stages: [dev, qa]
acceptance:
  - ICE candidate 추가 실패 시 로그 메시지가 포함되어야 합니다.
  - ICE candidate 추가 실패 시 테스트가 추가되어야 합니다.
---
## 배경

Video.vue 파일에서 ICE candidate 추가 실패 시 로그 메시지가 포함되어 있지 않습니다. 이는 디버깅과 유지보수에 어려움을 초래할 수 있습니다.

## 범위

- Video.vue 파일에서 ICE candidate 추가 실패 시 로그 메시지를 추가합니다.
- Video.vue 파일에 대한 테스트를 추가하여 ICE candidate 추가 실패 시 로그 메시지가 올바르게 출력되는지 확인합니다.

## 참고 파일

- frontend/src/components/Video.vue

## 출처

Tech Lead 에이전트 제안. 사람이 검토 후 `hermes approve <ID>`로 승인한다.
