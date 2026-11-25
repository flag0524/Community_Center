---
name: verify
description: 조리읍 수강시스템 변경을 실제 API·워커·두 웹 앱을 띄워 확인하는 방법. 시험 실행이 아니라 구동 검증에 쓴다.
---

# 구동 검증 방법 (Windows 개발 PC)

## 준비
1. DB 기동: `scripts/db/mariadb-dev.ps1 start` (127.0.0.1:33306).
2. 개발 DB는 건드리지 않는다. `jori_dev`를 `jori_test`로 복제해 쓴다(DB 시험이 다시 초기화한다). `mariadb-dump.exe`에는 `--skip-add-locks`를 반드시 준다. 없으면 시퀀스 때문에 적재가 실패한다. 접속값은 `%USERPROFILE%\dev-tools\mariadb-credentials.json`이고 비밀번호는 `MYSQL_PWD`로 넘긴다.
3. 환경변수는 `docs/시스템_구동_안내서.md` 5.2절을 따르되 DB 이름만 `jori_test`, 첨부 폴더는 임시 폴더로 한다. 모의 PG·문자·검사 어댑터가 켜진다.

## 띄우기 (각각 백그라운드)
- API: `apps/api`에서 `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`
- 워커: `apps/api`에서 `.venv/Scripts/python.exe -m app.worker`
- 화면: `apps/web-admin`(5174)·`apps/web-user`(5173)에서 `VITE_API_MODE=live`로 `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port <포트> --strictPort`
- 계정: 개발 DB의 시험 계정(`devadmin`, `devmember`). 비밀번호는 모의 서버 시험 값과 같다.

## 구동 요령
- HTTP는 `.venv`의 `httpx2`를 쓴다. `GET …/auth/session`의 `csrfToken`을 `X-CSRF-Token`으로, 상태 변경에는 `Idempotency-Key`를 보낸다.
- 브라우저는 `@playwright/test`의 `chromium.launch({ channel: 'msedge' })`. 스크립트는 `apps/web-admin/*.tmp.mjs`에 두고 끝나면 지운다.
- 인증번호는 DB에 남지 않는다. 실행 파일에서 `MockSmsSender.send`를 감싸 문안을 파일에 남긴다. PG의 특이 응답(금액 불일치 등)도 `MockPaymentGateway.__init__`을 감싸 대역으로 만든다.
- 잠금 경합은 다른 DB 연결에서 대상 행을 `FOR UPDATE`로 잡고 요청을 보낸 뒤 상태를 바꿔 커밋한다.

## 함정
- 주민 결제 화면 경로는 `/payment/:applicationId`다(TDD의 `/pay/…`가 아니다). 결제 대기는 10분이라 `STLM_DDLN_DT`를 늘리고 시작한다.
- 관리자 세션 만료를 시험할 때 화면의 조회가 만료를 늘린다. `LAST_ACT_DT`를 지금으로 두면 30초 동안 늘지 않는다.
- 첫 방문 화면은 Vite의 의존성 최적화로 한 번 새로 고쳐질 수 있다. 몇 초 기다린 뒤 누른다.
- `/course-options`의 첫 교육기수는 작성 중인 기수일 수 있다.
