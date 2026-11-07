---
id: HX-002
title: P2P 파일 전송 청킹·진행률·메타데이터 프로토콜
priority: P0
area: frontend
status: todo
stages: [pm, design, dev, qa]
acceptance:
  - 16KB 단위 청크로 전송하며 bufferedAmount 기반 백프레셔를 적용해 수 MB 파일도 전송된다
  - sendFile(file, onProgress)의 onProgress가 0~100 정수로 호출되고 FileBox 진행률 바에 반영된다
  - 수신 측은 JSON 헤더(name, size, mime, chunkCount)로 파일을 조립하고 size 불일치 시 오류를 표시한다
  - useWebRTC의 파일 프로토콜 인코딩/디코딩 로직이 vitest로 검증된다
---
## 배경

`useWebRTC.sendFile`은 파일명 문자열 뒤에 `arrayBuffer` 전체를 한 메시지로 보낸다.
브라우저 DataChannel 메시지 크기 제한(Chrome 약 256KB) 때문에 큰 파일은 실패하고,
`FileBox.vue`가 넘기는 진행률 콜백은 무시된다. 수신 측 `setupFileChannel`은 바이너리 한 건을 파일 전체로 간주한다.

## 범위

- 전송 프로토콜: `{type:"file-meta", id, name, size, mime, chunkCount}` → 바이너리 청크 N개 → `{type:"file-end", id}`
- 청크 크기 16KB, `bufferedAmountLowThreshold`로 백프레셔
- 수신 조립과 Blob 생성, 진행률 이벤트
- 프로토콜 함수를 `frontend/src/utils/fileProtocol.js`로 분리해 단위 테스트

## 범위 외

- 전송 취소/재개, 다중 파일 동시 전송

## 참고 파일

- frontend/src/composables/useWebRTC.js (sendFile, setupFileChannel)
- frontend/src/components/FileBox.vue
