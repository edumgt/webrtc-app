---
id: HX-008
title: 채팅 메시지 구조화(발신자·시각·ID)와 시스템 메시지
priority: P2
area: frontend
status: todo
stages: [pm, design, dev, qa]
acceptance:
  - chat 채널 페이로드가 {id, sender, text, sentAt} JSON으로 바뀌고 구버전 문자열 수신도 처리된다
  - 피어 입장/퇴장 시 시스템 메시지가 채팅에 표시된다
  - 메시지 직렬화/역직렬화가 vitest로 검증된다
---
## 배경

채팅은 원시 문자열만 주고받아 3인 이상 방에서 누가 보냈는지 알 수 없다.

## 참고 파일

- frontend/src/components/ChatBox.vue
- frontend/src/composables/useWebRTC.js (sendChat/onChat)
