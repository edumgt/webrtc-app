---
id: HX-007
title: 화이트보드 터치/포인터 입력 지원과 늦게 입장한 피어 캔버스 동기화
priority: P2
area: frontend
status: todo
stages: [pm, design, dev, qa]
acceptance:
  - pointer 이벤트로 마우스·터치·펜 입력이 모두 동작하고 캔버스 CSS 크기와 내부 좌표가 올바르게 변환된다
  - 새 피어가 draw 채널을 열면 기존 참가자가 스트로크 히스토리(또는 스냅샷)를 전송해 동일한 화면을 본다
  - 좌표 변환·히스토리 직렬화 함수가 vitest로 검증된다
---
## 배경

Whiteboard는 mouse 이벤트만 처리하고, 캔버스 고정 크기(1440x860)와 표시 크기가 달라 좌표가 어긋날 수 있다. 늦게 들어온 피어는 빈 캔버스를 본다.

## 참고 파일

- frontend/src/components/Whiteboard.vue
- frontend/src/composables/useWebRTC.js (ondatachannel draw)
