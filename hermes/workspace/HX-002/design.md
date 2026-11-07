# Design Spec: HX-002 P2P 파일 전송 청킹·진행률·메타데이터 프로토콜

## 1. 사용자 흐름 (단계별, 상태 전이)

1. 사용자가 파일을 드롭 존 또는 파일 선택기로 선택합니다.
2. 선택한 파일의 이름과 크기가 표시됩니다.
3. "전송" 버튼을 클릭하여 파일 전송을 시작합니다.
4. 파일 전송 중에는 진행률 바가 표시되어 전송 진행 상황을 보여줍니다.
5. 파일 전송이 완료되면 수신 측에서 파일이 표시됩니다. 사용자가 다운로드 링크을 클릭하여 파일을 다운로드할 수 있습니다.

## 2. 화면/컴포넌트 구조 (컴포넌트 트리, props/emit, 신규/수정 구분)

- FileBox.vue (새로 생성)
  - dropZone (수정)
  - selectedFile (새로 생성)
  - sendButton (새로 생성)
  - progressBar (새로 생성)
  - receivedFilesList (새로 생성)

## 3. 상태별 UI 규칙 (idle / loading / progress / success / error 등)

- idle: 파일이 선택되지 않았을 때
  - dropZone과 inputButton이 활성화
  - selectedFile, sendButton, progressBar, receivedFilesList가 비활성화

- loading: 파일 전송 중일 때
  - dropZone과 inputButton이 비활성화
  - selectedFile이 비활성화
  - sendButton과 progressBar가 활성화
  - receivedFilesList가 비활성화

- progress: 파일 전송 진행 중일 때
  - dropZone과 inputButton이 비활성화
  - selectedFile이 비활성화
  - sendButton과 progressBar가 활성화
  - receivedFilesList가 비활성화

- success: 파일 전송 완료 및 수신일 때
  - dropZone과 inputButton이 활성화
  - selectedFile이 비활성화
  - sendButton과 progressBar가 비활성화
  - receivedFilesList가 활성화

## 4. 스타일 토큰 (기존 CSS 변수 재사용, 신규 토큰은 명시)

- 기존 스타일 토큰: $primary-color, $secondary-color, $success-color, $error-color
- 신규 스타일 토큰:
  - $file-box-background-color: 파일 드롭 존 배경 색상
  - $file-box-border-color: 파일 드롭 존 경계 색상
  - $file-box-selected-background-color: 선택된 파일 배경 색상
  - $file-box-progress-bar-background-color: 진행률 바 배경 색상
  - $file-box-progress-bar-color: 진행률 바 색상

## 5. 접근성 및 반응형 (aria, 키보드, 모바일 폭)

- 접근성: 파일 드롭 존과 파일 선택기가 키보드 사용자를 위한 접근성이 충족되어야 합니다.
- 반응형: 모바일 기기와 태블릿에서 적절한 폭과 스크린 읽기 최적화를 지원해야 합니다.

## 6. 문구 (사용자에게 노출되는 한국어 문구 목록)

- "파일을 드롭하세요": 파일 드롭 존 위에 표시되는 문구
- "파일을 선택하세요": 파일 선택기 위에 표시되는 문구
- "전송": sendButton에 표시되는 문구
- "다운로드": receivedFilesList에서 파일을 다운로드할 때 표시되는 문구

## 참고 파일

- frontend/src/composables/useWebRTC.js (sendFile, setupFileChannel)
- frontend/src/components/FileBox.vue
