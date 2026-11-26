# 조리읍 주민자치센터 수강시스템

경기도 파주시 조리읍 주민자치센터의 강좌 조회·수강신청·결제·환불 시스템입니다. 주민은 기본 화면과 쉬운 화면(고령·저시력 이용자용) 중 골라 쓰고, 센터 직원은 관리자 화면에서 강좌와 접수를 운영합니다.

> **현재 상태(2026-11-26)** 주민·관리자 화면과 FastAPI·MariaDB·워커의 핵심 업무가 구현돼 개발 PC에서 실제 API로 연결해 쓸 수 있습니다. **운영에 올릴 수 있는 상태는 아닙니다.** 실제 PG·문자(SMS) 연동, Ubuntu 서버 배포, 복구·부하 검증이 남아 있습니다. 세부 잔여 작업은 `checklist.md`와 최신 ADR을 확인합니다.

## 구현한 것

| 영역 | 내용 |
|---|---|
| 주민 · 강좌와 접수 | 강좌 목록(접수중·접수예정·분야별)·상세·강의계획, 수강신청(무료·대기 포함), 모의 PG 결제, 취소·영수증·환불 신청, 감면 사전심사 |
| 주민 · 계정 | 회원가입, 로그인, 아이디 찾기, 비밀번호 재설정·변경, 회원정보·이름 변경, 탈퇴 |
| 주민 · 안내와 참여 | 센터 소개·시설안내·연락처, 공지·소식·자료실·갤러리·자주 하는 질문, 질문과 답변, 수강후기, 강사은행 |
| 담당 강사 | 담당 강좌의 수업 회차별 출석 입력 |
| 관리자 | 교육기수·강좌·일정·휴보강·센터·강의실, 강사 심사, 출석 현황, 신청·대기·결제·거래 대조·환불·감면, 회원·게시판·문의·콘텐츠·약관·첨부, 대시보드·통계, 문자 발송, 권한, 운영 설정·코드, 보존·파기 |
| 서버 | 인증·권한 범위, 정원·결제기한·대기 승격, 멱등 처리, 감사 이력, 워커(만료·승격·문자 발송·결제·환불 확인·보존), MariaDB 마이그레이션 |

## 남은 것

| 항목 | 필요한 것 |
|---|---|
| 실제 PG·문자(SMS)·파일 검사 확인 | PG·문자 업체 선정과 계약, 대상 서버의 ClamAV. 지금 PG·문자는 모의 어댑터만 있습니다 |
| 운영 배포·복구·부하 검증 | Ubuntu 서버. 배포 파일 초안은 [deploy/](deploy/README.md)에 있고 서버에서 확인하지 않았습니다 |
| 기관 확정 | PRD 미결 질문, 화면설계서 미결 항목. [기관 회신 요청 요약](docs/기관_회신_요청_요약.md) |
| 지도·SNS | 네이버 지도 SDK 키와 센터 좌표, 공식 SNS 주소(받기 전까지 상단 아이콘은 연결하지 않음) |
| 시설 사진 | 3·4층 사진 확보와 1·2층 사진의 이용 허가 확인 |

만들지 않기로 한 기능(가상계좌, 관리자 MFA, PASS·카카오 인증 등)은 [PRD](docs/PRD.md) 1.3절과 [ADR](docs/ADR.md)에 있습니다.

## 구성

```
apps/
  api/           FastAPI 업무 API·MariaDB 접근·마이그레이션·별도 프로세스 워커(app/worker)
  web-user/      주민 앱 (React, 기본 화면 + 쉬운 화면)
  web-admin/     관리자 앱 (React)
packages/
  ui/            공통 스타일과 공통 코드
  api-client/    OpenAPI에서 생성한 TypeScript 타입
scripts/         개발 DB 스크립트, 전체 켜기·끄기 스크립트
deploy/          운영 서버 배포 파일 초안
docs/            PRD, TRD, ADR, TDD, 화면설계서, DB 스키마 설계안, 구동 안내서
```

## 기술 스택

- **프런트엔드** React 18, TypeScript, Vite, React Router 7, TanStack Query 5
- **백엔드** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic (패키지 관리 uv)
- **DB** MariaDB 10.11
- **시험** Vitest, Testing Library, MSW, Playwright(+axe-core), pytest, ruff, mypy
- **목표 운영 환경** Ubuntu Server (주민자치회마다 WAS·DB 분리)

## 시작하기

필요한 것은 Node.js 22.12 이상, pnpm 10, uv(Python 3.12)입니다. 계정과 자세한 절차는 [구동 안내서](docs/시스템_구동_안내서.md)에 있습니다.

### 방법 A. 모의 서버로 화면만 보기

API와 DB 없이 브라우저 안의 모의 서버(MSW)로 동작합니다. 두 앱은 터미널을 따로 열어 띄웁니다.

```powershell
pnpm install

# 터미널 1: 주민 앱  http://localhost:5173
pnpm --filter @jori/web-user exec vite --port 5173 --strictPort

# 터미널 2: 관리자 앱  http://localhost:5174
pnpm --filter @jori/web-admin exec vite --port 5174 --strictPort
```

### 방법 B. 실제 API와 DB로 쓰기 (Windows 개발 PC)

최초 한 번은 [구동 안내서](docs/시스템_구동_안내서.md) 3~5절을 따라 의존성 설치(`pnpm install`, `apps/api`에서 `uv sync`), 개발 DB 생성, 비밀키 파일, 마이그레이션, 최초 설정을 합니다. 그 뒤에는 저장소 폴더의 파일을 두 번 누릅니다.

| 파일 | 하는 일 |
|---|---|
| `프로그램_켜기.bat` | 개발 DB·API·워커·두 화면을 켜고 브라우저를 엽니다. 이미 켜진 것은 건너뜁니다 |
| `프로그램_끄기.bat` | 켜 둔 서비스와 개발 DB를 끕니다. 이 프로젝트의 것이 아닌 프로그램은 끄지 않습니다 |

API와 워커는 `JORI_ENVIRONMENT`가 없으면 켜지지 않습니다. 켜기 파일은 `development`로 설정합니다. 화면을 직접 띄울 때는 `VITE_API_MODE=live`를 줘야 실제 API를 씁니다.

### 개발 서버 전용 보조 기능

운영 빌드에는 들어가지 않으며, 섞이면 빌드가 실패합니다.

- `?view=easy` 쉬운 화면으로 전환합니다.
- `?mockNow=2026-09-08` 모의 시계를 접수 기간으로 옮겨 접수중 강좌와 수강신청 버튼을 봅니다.
- `?mockPay=success` 모의 결제 결과를 고릅니다(`success`, `failed`, `unknown`, `expired`).
- `?mockIdle=125` 관리자 세션의 유휴 만료 시간을 줄입니다.

모의 서버의 상태는 쪽을 새로 열면 처음으로 돌아갑니다.

## 시험

```powershell
pnpm check                        # 저장소 루트: 린트, 타입, 단위 시험, 빌드, 브라우저 시험(Edge, axe 포함)

cd apps\api                       # API
uv run ruff check .
uv run mypy app tests
$env:JORI_REQUIRE_DB = "1"        # DB가 없으면 건너뛰지 않고 실패
uv run pytest -q
```

- DB 시험이 건너뛰어졌다면 전체 검증 통과로 보지 않습니다. 먼저 `scripts\db\mariadb-dev.ps1 start`로 DB를 켭니다.
- GitHub 자동 검사(`.github/workflows/ci.yml`)는 푸시·PR마다 API(ruff, 서식, mypy, pytest)와 웹(린트, 타입, 단위 시험, 빌드)을 검사합니다. **브라우저 시험은 포함하지 않으므로** 로컬에서 돌립니다.
- 화면 시험 중 날짜를 다루는 것은 CI와 같은 `TZ=UTC`로도 확인합니다.
- 실행별 결과는 `context-notes.md`와 `checklist.md`에 남깁니다.
- Windows에서 pnpm 실행기가 막히면 설치된 도구를 직접 실행합니다. 예를 들어 앱 폴더에서 `node node_modules/vitest/vitest.mjs run`, API 폴더에서 `.venv\Scripts\python.exe -m pytest`를 씁니다.

## 운영 환경과 시험 DB 보호

- 운영 배포는 `JORI_ENVIRONMENT=production`을 지정합니다. PG·문자·파일 검사에 `mock`이 남거나 보안 쿠키가 꺼져 있으면 기동을 거절합니다. 실제 PG·문자 어댑터는 계약 후 구현해야 하므로 현재 소스로는 운영 기동이 되지 않습니다.
- 시험은 `jori_test` DB만 허용합니다. 앱 DB와 같은 대상이면 거절하고, 실제 접속 DB 이름을 확인한 뒤에만 테이블을 초기화합니다. `JORI_TEST_DATABASE_URL`에 개발·운영 DB를 지정하지 않습니다.
- 워커는 배포당 하나만 실행합니다(`python -m app.worker`).
- `/api/health`는 워커의 주기 작업과 일일 작업이 누락·실패·지연됐는지 확인합니다. 워커가 없으면 `503`입니다.
- `JORI_SECRET_KEY`는 휴대전화번호 암호화에도 쓰입니다. 바꾸면 저장된 번호를 읽을 수 없습니다.
- 기존 DB를 올릴 때는 OTP 관련 이행(0002·0003) 전에 발급을 중지하고 5분을 기다립니다([적용 보고](docs/OTP_재전송제한_개정안.md), ADR-095).

## 개발 원칙

- 일련번호는 22자리 숫자 문자열이며 JS 숫자로 바꾸지 않습니다.
- 금액·정원·결제기한·가능 여부·비공개 가림은 서버가 정하고 화면은 그대로 그립니다. 신청·결제·환불 요청에는 금액을 싣지 않습니다.
- 상태를 바꾸는 요청은 CSRF 토큰과 멱등키를 쓰고, 로그인·로그아웃 때 회원 전용 화면 캐시를 지웁니다.
- 접수·교육 상태는 서버가 판정하고 화면은 날짜를 비교하지 않습니다.
- 기본 화면과 쉬운 화면은 같은 API와 같은 쿼리 키를 씁니다.
- 새 기능은 시험을 먼저 쓰고, 접근성(KWCAG 2.2 AA) 검사를 통과해야 합니다.
- 사용 허가가 확인되지 않은 청사·시설 사진은 저장소에 넣지 않습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [구동 안내서](docs/시스템_구동_안내서.md) | 계정, 개발 PC에서 띄우는 방법, 문제 해결 |
| [DB 스키마 설계안](docs/PRJ_2026_002_DB스키마_설계안.md) | 데이터 모델 기준. 다른 문서와 다르면 이 문서를 따릅니다 |
| [PRD](docs/PRD.md) · [TRD](docs/TRD.md) · [TDD](docs/TDD.md) | 요구와 수용 기준, 수치 기준, 기술 설계 |
| [ADR](docs/ADR.md) | 누적 설계 결정 |
| [화면설계서](docs/화면설계서.md) | 화면 목록과 와이어프레임 |
| [스키마 개정 요청서](docs/스키마_개정_요청서.md) | 기관에 보낼 스키마 변경 요청 |

저장소 루트의 `intent.md`(확정 결정), `plan.md`(단계), `spec.md`(상세 명세와 결정 기록), `checklist.md`, `context-notes.md`에는 계획과 진행 기록이 있습니다.
