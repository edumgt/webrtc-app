---
id: HX-006
title: SystemPanel을 RTCPeerConnection.getStats() 실측 지표로 전환
priority: P2
area: frontend
status: todo
stages: [pm, design, dev, qa]
acceptance:
  - 피어별 RTT, 송수신 비트레이트, 패킷 손실, 선택된 candidate pair 유형(host/srflx/relay)이 2초 주기로 갱신된다
  - 피어가 없을 때는 빈 상태 UI가 표시되고 차트가 오류 없이 렌더링된다
  - getStats 리포트를 요약하는 순수 함수가 vitest로 검증된다
---
## 배경

현재 SystemPanel은 프런트 이벤트 로그에서 유추한 샘플 데이터를 표시한다. 운영 진단에는 실제 전송 통계가 필요하다.

## 참고 파일

- frontend/src/components/SystemPanel.vue
- frontend/src/composables/useWebRTC.js (peers Map, 지표 노출 API 추가 필요)
