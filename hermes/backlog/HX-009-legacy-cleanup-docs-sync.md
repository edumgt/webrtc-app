---
id: HX-009
title: 레거시 코드 정리와 문서 동기화
priority: P3
area: docs
status: todo
stages: [pm, dev, qa]
acceptance:
  - 사용되지 않는 signaling/signal.js, frontend/src/components/Video.vue 제거 여부를 PRD에서 결정하고 반영한다
  - readme-kr.md/Readme.md의 프로젝트 구조 트리가 실제 파일과 일치한다 (kube-manifests 등 존재하지 않는 항목 제거)
  - npm run build (frontend)가 통과한다
---
## 배경

README는 `kube-manifests/`를 언급하지만 저장소에 없고, `signal.js`와 `Video.vue`는 레거시로 표시되어 있다.

## 참고 파일

- readme-kr.md, Readme.md
- signaling/signal.js, frontend/src/components/Video.vue
