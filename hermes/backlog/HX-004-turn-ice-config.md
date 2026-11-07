---
id: HX-004
title: ICE 서버(TURN) 설정을 런타임 환경변수로 주입
priority: P1
area: infra
status: todo
stages: [pm, dev, qa]
acceptance:
  - VITE_ICE_SERVERS(JSON 배열)가 frontend-server.cjs의 /env-config.js를 통해 주입된다
  - 값이 없으면 기존 Google STUN 기본값을 사용하고, 잘못된 JSON이면 콘솔 경고 후 기본값으로 폴백한다
  - .env.example, docker-compose.yml, readme-kr.md/Readme.md에 설정 방법이 문서화된다
  - ICE 설정 파서가 vitest로 검증된다
---
## 배경

대칭 NAT 환경에서는 STUN만으로 P2P가 수립되지 않아 TURN이 필요하다. 현재 ICE 서버 목록은 `useWebRTC.js`에 하드코딩되어 있다.

## 범위

- `frontend/src/utils/iceServers.js`: 런타임/빌드타임 env → RTCIceServer[] 파서
- `frontend-server.cjs` runtimeConfig에 VITE_ICE_SERVERS 추가
- 문서/예시 env 갱신 (예: coturn)

## 참고 파일

- frontend/src/composables/useWebRTC.js (defaultIceServers)
- frontend/frontend-server.cjs
- frontend/src/utils/signalUrl.js (우선순위 패턴 참고)
