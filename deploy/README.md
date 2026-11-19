# 배포 파일(가정한 환경 기준)

자치회 1곳(조리읍)을 Ubuntu 서버 한 대에 올리는 파일 묶음이다. 서버 업체와 구성은 기관이 확인했고(가비아 클라우드, 서버 1대에 주민용·관리자용 화면과 DB를 함께 둠, 2026-11-19), 계정·경로·포트는 아직 정해지지 않아 아래 값을 가정했다(ADR-098·100). 확정되면 이 문서의 표와 파일의 값만 바꾼다. 업체 값(PG·문자 공급자·발신번호)은 가정하지 않고 TBD로 둔다.

## 1. 가정한 값

| 항목 | 가정 | 근거 |
|---|---|---|
| 서버 업체 | 가비아 클라우드(서버 1대, 자치회 전용) | 기관 회신 2026-11-19. 서버 사양·IP·지역은 받지 못함 |
| OS·런타임 | Ubuntu Server 24.04 LTS, Python 3.12, Nginx 1.24+, MariaDB 10.11 | TRD 1장, 프로젝트 스택. 가비아 클라우드에서 이 이미지를 쓸 수 있는지는 확인하지 못함 |
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

기관이 정한 값: 관리자 접속은 주소로 제한하지 않는다(Nginx 템플릿에 allow/deny 없음), 지도는 네이버 지도(SDK 키 미정).

가정하지 않은 값: PG 업체·가맹점 아이디, 문자 공급자·발신번호(기관 답 「아직 정하지 못함」), 도메인·인증서, 센터 연락처, 네이버 지도 SDK 키. 이 값이 TBD이면 운영(`JORI_ENVIRONMENT=production`)은 의도적으로 기동하지 않는다.

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

- 가비아 클라우드에서 Ubuntu 24.04 이미지와 Python 3.12·MariaDB 10.11 설치가 가능한지, 방화벽(80·443)과 서버 사양(CPU·메모리·디스크)
- `systemd-analyze verify /etc/systemd/system/jori-*.service`
- `systemctl status jori-worker@jori`에서 `Active: active (running)`과 watchdog 갱신, 워커를 멈추게(`kill -STOP`) 했을 때 60초 안에 다시 시작되는지
- `nginx -t`, 주민 도메인으로 `/api/admin/…` 요청이 404인지, 20MB 첨부가 올라가는지
- `curl http://127.0.0.1:8001/api/health`가 정상이고 워커 상태 파일을 읽는지
- `curl http://127.0.0.1:8001/api/health/version`의 커밋 해시가 배포한 빌드와 같고 마이그레이션 리비전이 최신인지(`JORI_BUILD_COMMIT`를 환경 파일에 넣었는지)
- DB 시험을 Ubuntu에서 한 번 더 돌려 대소문자 이름 규칙과 READ COMMITTED 쓰기(바이너리 로그를 켠 상태)를 확인한다(ADR-029·038)
- 실제 ClamAV 연동(`JORI_FILE_SCANNER=clamd`)

## 5. 초안(미검증): 계정 분리·백업·배포 자동화

실제 서버에서 확인하기 전에는 운영에 쓰지 않는다(ADR-102). 시험 `apps/api/tests/test_deploy_drafts.py`는 파일 내용과 스크립트 문법·`--dry-run` 순서만 본다.

| 파일 | 내용 |
|---|---|
| `mariadb/accounts.sql` | DB·계정 4개(`app_jori`, `worker_jori`, `backup_jori`, `migrate_jori`)와 권한. `python -m app.tools.generate_grants`로 설계안에서 만든다. 비밀번호는 `{{…_PASSWORD}}` 자리표시 |
| `env/jori.migrate.env.example` | `deploy.sh`가 구조 변경 계정으로 마이그레이션할 때 읽는 접속 주소 |
| `systemd/jori-worker@.service` | `/etc/jori/<인스턴스>.worker.env`가 있으면 워커만 `worker_jori`로 접속하게 덮어쓴다 |
| `backup/backup.sh` | 전체 백업(mariabackup 스트림을 바로 암호화, 첨부 사본, 해시, 별도 저장소 전송, 30일 정리) |
| `backup/binlog-sync.sh` | 바이너리 로그를 별도 저장소로 전송 |
| `backup/restore-check.sh`, `restore-check.sql` | 월 1회 복구시험. 백업을 임시 서버에 풀어 건수·금액·첨부 연결을 대조 |
| `systemd/jori-backup@.service·.timer` | 매일 02:30 백업(워커 03:00 작업보다 앞) |
| `systemd/jori-binlog-sync@.service·.timer` | 15분마다 로그 전송 |
| `env/jori.backup.env.example` | 백업 스크립트 설정(`/etc/jori/jori.backup.env`, 0600) |
| `deploy.sh` | 배포 7단계: 백업 → 풀기 → 파이썬 환경 → 커밋 해시 기록 → 마이그레이션 → 전환·재시작 → 건강 확인. 실패하면 이전 버전으로 되돌리고 DB는 되돌리지 않는다 |

서버에서 먼저 확인할 것:
- `deploy.sh <인스턴스> <커밋> <빌드.tar.gz> --dry-run`과 `backup.sh <인스턴스> --dry-run`으로 순서를 본다.
- `mariabackup`·`mbstream`·`mariadbd`·`rsync`·`openssl`·`uv`가 설치되어 있는지, `backup_jori`의 권한(`RELOAD, PROCESS, LOCK TABLES, BINLOG MONITOR`)으로 백업이 되는지
- 백업 유닛을 root로 돌리는 것을 줄일 수 있는지, 별도 저장소(`JORI_BACKUP_DEST`)와 암호화 키의 별도 보관 방법
- `accounts.sql`을 적용한 뒤 API·워커가 필요한 권한만으로 동작하는지(권한이 모자라면 시퀀스·작업 이력부터 본다)
- 복구시험을 스테이징 서버에서 한 번 실제로 돌려 결과 보고서를 확인한다
- 이 초안은 `retention_{자치회}` 계정을 두지 않았다. 파기는 워커 계정으로 돈다

## 6. 아직 하지 않은 것

- 새 자치회를 추가하는 절차(DB·계정·백업 세트·사이트 생성)
- 웹 앱 빌드와 산출물 묶음을 만드는 절차(`deploy.sh`는 만들어진 `.tar.gz`를 받는다)