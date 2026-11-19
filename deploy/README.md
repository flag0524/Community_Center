# 배포 파일(가정한 환경 기준)

자치회 1곳(조리읍)을 Ubuntu 서버 한 대에 올리는 파일 묶음이다. **서버·도메인·계정은 아직 정해지지 않아 아래 값을 가정했다**(ADR-098). 확정되면 이 문서의 표와 파일의 값만 바꾼다. 업체 값(PG·문자 공급자·발신번호)은 가정하지 않고 TBD로 둔다.

## 1. 가정한 값

| 항목 | 가정 | 근거 |
|---|---|---|
| OS·런타임 | Ubuntu Server 24.04 LTS, Python 3.12, Nginx 1.24+, MariaDB 10.11 | TRD 1장, 프로젝트 스택 |
| 자치회 인스턴스 이름 | `jori` (유닛 `jori-api@jori`, `jori-worker@jori`) | TDD 11장의 `{자치회}` |
| 서비스 계정 | `jori:jori` (로그인 불가 시스템 계정) | 가정 |
| 코드 위치 | `/opt/jori/releases/<커밋해시>`, 현재 버전은 `/opt/jori/current` 링크, 파이썬 환경은 `/opt/jori/venv` | 검수 통과 빌드 산출물만 배포(TRD 2장) |
| 설정 파일 | `/etc/jori/jori.env` (root:jori, 0640) | TRD 2장 |
| 첨부 저장소 | `/data/jori/jori/files` (웹 루트 밖, 서비스 계정만) | TRD 4.5 |
| 워커 상태 파일 | `/run/jori/jori/worker-status.json` (유닛의 RuntimeDirectory) | ADR-027 |
| API 주소 | `127.0.0.1:8001`, 프로세스 4개 | TDD 11장의 시작값 |
| 도메인 | `user.{{DOMAIN}}`, `admin.{{DOMAIN}}` (미정) | TRD 2.1 |
| DB | 스키마·계정 `jori`·`app_jori`, 같은 서버 `127.0.0.1:3306` | TDD 11장 |
| 파일 검사 | clamd `127.0.0.1:3310` | ADR-079 |

가정하지 않은 값: PG 업체·가맹점 아이디, 문자 공급자·발신번호, 도메인·인증서, 관리자 접속 허용 주소, 센터 연락처. 이 값이 TBD이면 운영(`JORI_ENVIRONMENT=production`)은 의도적으로 기동하지 않는다.

## 2. 파일

| 파일 | 위치에 둘 곳 |
|---|---|
| `systemd/jori-api@.service` | `/etc/systemd/system/` |
| `systemd/jori-worker@.service` | `/etc/systemd/system/` (워커가 15초마다 watchdog 신호를 보내고 60초 없으면 다시 시작) |
| `env/jori.env.example` | `/etc/jori/jori.env`로 복사해 CHANGE_ME를 채운다 |
| `nginx/jori.conf.template` | `{{DOMAIN}}`·`{{API_PORT}}`를 바꿔 `/etc/nginx/sites-available/jori.conf` |
| `nginx/jori-security-headers.conf` | `/etc/nginx/snippets/` |
| `mariadb/jori.cnf` | `/etc/mysql/mariadb.conf.d/60-jori.cnf` |

## 3. 처음 올리는 순서

1. 계정·폴더: `useradd --system --home /opt/jori --shell /usr/sbin/nologin jori`, `install -d -o jori -g jori /data/jori/jori/files /opt/jori`, `install -d -m 0750 -o root -g jori /etc/jori`
2. MariaDB: 설정 파일을 두고 재시작한 뒤 `SELECT @@transaction_isolation, @@binlog_format`로 확인한다. 스키마와 `app_jori` 계정을 만든다.
3. 코드: 검수 통과 빌드를 `/opt/jori/releases/<해시>`에 풀고 `current`를 바꾼 뒤 `UV_PROJECT_ENVIRONMENT=/opt/jori/venv uv sync --frozen --no-dev`로 파이썬 환경을 맞춘다. 웹 앱은 `apps/web-user/dist`, `apps/web-admin/dist` 빌드 결과를 둔다.
4. 마이그레이션: 백업 후 `alembic upgrade head`. 운영묶음 행(`TB_OPER_BNDL.SITE_ID` = `JORI_SITE_ID`)과 초기 코드는 시드 절차로 넣는다.
5. 설정: `/etc/jori/jori.env`의 비밀값을 채운다. `JORI_SECRET_KEY`는 서버에서 무작위로 만든다(32자 이상).
6. 서비스: `systemctl daemon-reload && systemctl enable --now jori-api@jori jori-worker@jori`
7. Nginx: `nginx -t && systemctl reload nginx`

## 4. 확인할 것(이 PC에서는 확인하지 못함)

시험 `apps/api/tests/test_deploy_files.py`는 파일 내용이 앱 설정과 맞는지만 본다. 아래는 Ubuntu 서버에서 직접 확인해야 한다.

- `systemd-analyze verify /etc/systemd/system/jori-*.service`
- `systemctl status jori-worker@jori`에서 `Active: active (running)`과 watchdog 갱신, 워커를 멈추게(`kill -STOP`) 했을 때 60초 안에 다시 시작되는지
- `nginx -t`, 주민 도메인으로 `/api/admin/…` 요청이 404인지, 20MB 첨부가 올라가는지
- `curl http://127.0.0.1:8001/api/health`가 정상이고 워커 상태 파일을 읽는지
- DB 시험을 Ubuntu에서 한 번 더 돌려 대소문자 이름 규칙과 READ COMMITTED 쓰기(바이너리 로그를 켠 상태)를 확인한다(ADR-029·038)
- 실제 ClamAV 연동(`JORI_FILE_SCANNER=clamd`)

## 5. 아직 하지 않은 것

- DB 계정 분리(`worker_jori`, `retention_jori`, `backup_jori`)와 권한 부여 SQL. 지금은 한 계정을 함께 쓴다.
- 백업(mariabackup·binlog 전송·첨부 rsync)과 월 1회 복구시험 스크립트
- `/api/health/version`(커밋 해시·마이그레이션 리비전 노출)
- 배포 자동화 스크립트와 새 자치회 추가 절차
