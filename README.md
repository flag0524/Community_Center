# 조리읍 주민자치센터 수강시스템

경기도 파주시 조리읍 주민자치센터의 강좌 조회·수강신청·결제·환불 시스템입니다. 주민은 기본 화면과 쉬운 화면(고령·저시력 이용자용) 중 골라 쓰고, 센터 직원은 관리자 화면에서 강좌와 접수를 운영합니다.

> **현재 상태** 설계 문서가 끝났고 주민 화면을 시안에서 React로 옮기는 중입니다. 백엔드 API는 계약(OpenAPI)과 라우터 뼈대만 있고 모든 요청이 `501`을 돌려줍니다. 화면은 모의 서버(MSW)로 동작합니다.

## 만든 것과 남은 것

| 단계 | 내용 | 상태 |
|---|---|---|
| F1~F4 | 저장소·공통 스타일·API 계약(OpenAPI)·타입 생성 | 완료 |
| F5 | 공통 레이아웃, 홈, 쉬운 화면 전환, 글자 크기 | 완료 |
| F6 | 강좌 목록·접수중·접수예정·분야별·상세·강의계획 | 완료 |
| F7 | 로그인, 회원가입 4단계, 약관 | 완료 |
| F8 | 신청 → 결제 → 내 신청 → 영수증 → 환불 | 예정 |
| F9 | 주민 나머지 화면, 관리자 앱 | 예정 |
| P2~ | DB(MariaDB) 물리 설계와 실제 백엔드 구현 | 예정 |

## 구성

```
apps/
  api/           FastAPI 백엔드 뼈대. 라우터와 Pydantic 모델로 OpenAPI를 정의한다
  web-user/      주민 앱 (React, 기본 화면 + 쉬운 화면)
packages/
  ui/            시안 CSS와 공통 자원
  api-client/    OpenAPI에서 생성한 TypeScript 타입
docs/            PRD, TRD, ADR, TDD, 화면설계서, DB 스키마 설계안
```

계획 문서는 저장소 루트의 `intent.md`(확정 결정), `plan.md`(단계), `spec.md`(상세 명세와 결정 기록), `checklist.md`, `context-notes.md`입니다.

## 기술 스택

- **프런트엔드** React 18, TypeScript, Vite, React Router 7, TanStack Query 5
- **백엔드** Python 3.12, FastAPI, Pydantic 2 (패키지 관리 uv)
- **시험** Vitest, Testing Library, MSW, Playwright(+axe-core), pytest, ruff, mypy
- **목표 운영 환경** Ubuntu Server, MariaDB 10.11 (주민자치회마다 WAS·DB 분리)

## 시작하기

필요한 것은 Node.js 22.12 이상, pnpm 10, uv(Python 3.12)입니다. 브라우저 시험은 이 PC에 설치된 Microsoft Edge를 씁니다.

```powershell
pnpm install
pnpm --filter @jori/web-user dev        # http://localhost:5173 (모의 서버로 동작)
pnpm check                              # 린트, 타입, 단위 시험, 빌드, 브라우저 시험을 모두 실행
```

개발 서버에서만 쓸 수 있는 보조 기능이 있습니다. 운영 빌드에는 들어가지 않으며, 섞이면 빌드가 실패합니다.

- `?view=easy` 쉬운 화면으로 전환합니다.
- `?mockNow=2026-09-08` 모의 시계를 접수 기간으로 옮겨 접수중 강좌와 수강신청 버튼을 봅니다.

## 개발 원칙

- 일련번호는 22자리 숫자 문자열이며 JS 숫자로 바꾸지 않습니다.
- 접수·교육 상태는 서버가 판정하고 화면은 날짜를 비교하지 않습니다.
- 기본 화면과 쉬운 화면은 같은 API와 같은 쿼리 키를 씁니다.
- 새 기능은 시험을 먼저 쓰고, 접근성(KWCAG 2.2 AA) 검사를 단계마다 통과해야 합니다.
- 사용 허가가 확인되지 않은 청사 사진은 저장소에 넣지 않습니다.

## 문서

기능 요구와 결정의 근거는 `docs/`에 있습니다. 데이터 모델은 `docs/PRJ_2026_002_DB스키마_설계안.md`가 기준입니다.
