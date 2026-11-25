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
2. MariaDB: 설정 파일을 두고 재시작한 뒤 `SELECT @@transaction_isolation, @@binlog_format`로 확인한다. DB와 계정은 `mariadb/accounts.sql`(비밀번호 자리표시를 바꿔서)로 만든다.
3. 코드: 검수 통과 빌드를 `/opt/jori/releases/<해시>`에 풀고 `current`를 바꾼 뒤 `UV_PROJECT_ENVIRONMENT=/opt/jori/venv uv sync --frozen --no-dev`로 파이썬 환경을 맞춘다. 웹 앱은 `apps/web-user/dist`, `apps/web-admin/dist` 빌드 결과를 둔다.
4. 마이그레이션: 백업 후 `alembic upgrade head`(코드표 초기값은 마이그레이션이 넣는다). 0005(휴대전화번호 암호화)는 평문을 암호문으로 바꾸므로 운영과 같은 `JORI_SECRET_KEY`가 환경에 있어야 하고(deploy.sh가 앱 설정 파일에서 읽어 준다), 번호가 있는 행이 있는데 키가 없거나 32자 미만이면 아무것도 바꾸지 않고 중단한다. 이행 뒤 이 키를 바꾸면 모든 번호를 읽을 수 없게 되므로 키를 바꾸지 않는다(교체 도구는 만들지 않았다).
   마이그레이션은 `migrate_jori` 계정으로 하고, 끝나면 `mariadb/grants.sql`을 적용해 API·워커 계정에 테이블 권한을 준다(테이블이 없으면 이 SQL은 중간에 멈춘다). 테이블을 더하는 마이그레이션 뒤에도 다시 적용한다.
   그다음 **최초 설정**을 한 번 한다. 운영묶음·행정동·최초 관리자를 한 트랜잭션으로 만들고, 이미 관리자가 있으면 거부한다(ADR-104).
   `uv run python -m app.tools.bootstrap --site-id jori --bundle-name <묶음명> --site-name <사이트명> --url https://user.<도메인> --dongs-file <기관 행정동 명단.txt> --admin-id <아이디> --admin-name <이름>`
   (`JORI_DATABASE_URL`은 API 계정 주소, 비밀번호는 프롬프트로 두 번 입력한다. 자동화는 `--password-stdin`.) 행정동 명단은 기관이 확정한 것만 쓴다. 최초 관리자는 모든 권한을 가지므로 담당자를 위임한 뒤 사용 중지를 권장한다.
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
| `mariadb/accounts.sql` | 마이그레이션 **전**에 적용. DB·계정 4개(`app_jori`, `worker_jori`, `backup_jori`, `migrate_jori`)와 마이그레이션·백업 권한. 비밀번호는 `{{…_PASSWORD}}` 자리표시 |
| `mariadb/grants.sql` | 마이그레이션 **뒤**에 적용. API·워커 계정의 테이블·시퀀스 권한. 두 파일 모두 `python -m app.tools.generate_grants`로 설계안에서 만든다 |
| `env/jori.migrate.env.example` | `deploy.sh`가 구조 변경 계정으로 마이그레이션할 때 읽는 접속 주소 |
| `systemd/jori-worker@.service` | `/etc/jori/<인스턴스>.worker.env`가 있으면 워커만 `worker_jori`로 접속하게 덮어쓴다 |
| `backup/backup.sh` | 전체 백업(mariabackup 스트림을 바로 암호화, 첨부 사본, 해시, 별도 저장소 전송, 30일 정리) |
| `backup/binlog-sync.sh` | 바이너리 로그를 별도 저장소로 전송 |
| `backup/restore-check.sh`, `restore-check.sql` | 월 1회 복구시험. 백업을 임시 서버에 풀어 건수·금액·첨부 연결을 대조 |
| `systemd/jori-backup@.service·.timer` | 매일 02:30 백업(워커 03:00 작업보다 앞) |
| `systemd/jori-binlog-sync@.service·.timer` | 15분마다 로그 전송 |
| `env/jori.backup.env.example` | 백업 스크립트 설정(`/etc/jori/jori.backup.env`, 0600) |
| `build-release.sh` | 빌드 PC에서 커밋 한 벌의 산출물(`jori-<해시12>.tar.gz`와 `.sha256`)을 만든다. 작업 트리가 깨끗해야 하고 git에 있는 파일(`apps/api`, `deploy`)과 웹 앱 dist만 담아 비밀값·node_modules가 들어가지 않는다. `--skip-build`, `--dry-run` |
| `deploy.sh` | 배포 7단계: 백업 → 풀기 → 파이썬 환경 → 커밋 해시 기록 → 마이그레이션 → 전환·재시작 → 건강 확인. 실패하면 이전 버전으로 되돌리고 DB는 되돌리지 않는다 |

서버에서 먼저 확인할 것:
- 빌드 PC에서 `build-release.sh`로 실제 산출물을 한 번 만들어 보고(`pnpm install --frozen-lockfile`, 운영 빌드), `deploy.sh <인스턴스> <커밋> <산출물.tar.gz> --dry-run`과 `backup.sh <인스턴스> --dry-run`으로 순서를 본다.
- `mariabackup`·`mbstream`·`mariadbd`·`rsync`·`openssl`·`uv`가 설치되어 있는지, `backup_jori`의 권한(`RELOAD, PROCESS, LOCK TABLES, BINLOG MONITOR`)으로 백업이 되는지
- 백업 유닛을 root로 돌리는 것을 줄일 수 있는지, 별도 저장소(`JORI_BACKUP_DEST`)와 암호화 키의 별도 보관 방법
- `accounts.sql`, 마이그레이션, `grants.sql`을 차례로 적용한 뒤 API·워커가 필요한 권한만으로 동작하는지(권한이 모자라면 시퀀스·작업 이력부터 본다)
- 복구시험을 스테이징 서버에서 한 번 실제로 돌려 결과 보고서를 확인한다
- 이 초안은 `retention_{자치회}` 계정을 두지 않았다. 파기는 워커 계정으로 돈다

## 6. 새 자치회 추가(초안, 서버에서 확인 전)

자치회마다 WAS·DB·DB 계정을 따로 둔다(ADR-002). 같은 서버에 더하는 경우의 순서다. `<이름>`은 영소문자·숫자 2~16자(예: `hwaseong`)이고 유닛·설정 파일·DB·계정 이름이 모두 이 이름을 따른다.

1. **정할 것**: 인스턴스 이름, 사이트 식별자(`SITE_ID`, 소문자·숫자·하이픈), 다른 자치회와 겹치지 않는 API 포트(`JORI_API_PORT`), 도메인
2. **DB·계정**: `uv run python -m app.tools.generate_grants --instance <이름> > accounts-<이름>.sql`과 `… --instance <이름> --grants > grants-<이름>.sql`로 만든다. `accounts-<이름>.sql`은 `{{…_PASSWORD}}`를 서버에서 바꿔 지금 적용하고, `grants-<이름>.sql`은 4번의 마이그레이션 뒤에 적용한다
3. **폴더·설정**: `install -d -o jori -g jori /data/jori/<이름>/files`, `/etc/jori/<이름>.env`(`jori.env.example`을 복사해 `JORI_DATABASE_URL`·`JORI_SITE_ID`·`JORI_FILE_ROOT`·`JORI_WORKER_STATUS_FILE=/run/jori/<이름>/worker-status.json`·`JORI_API_PORT`를 이 자치회 값으로, `JORI_SECRET_KEY`는 **새로 만든다**), `<이름>.migrate.env`, `<이름>.backup.env`. 비밀키·계정 비밀번호를 다른 자치회와 같게 쓰지 않는다
4. **마이그레이션, 권한, 최초 설정**: 3장 4번과 같다(`migrate_<이름>` 계정으로 마이그레이션, `grants-<이름>.sql` 적용, 이어서 `bootstrap`)
5. **Nginx**: `nginx/jori.conf.template`의 `{{DOMAIN}}`·`{{API_PORT}}`를 바꿔 새 사이트 파일로 둔다
6. **서비스**: `systemctl enable --now jori-api@<이름> jori-worker@<이름> jori-backup@<이름>.timer jori-binlog-sync@<이름>.timer`
7. **확인**: 최초 관리자로 로그인, `/api/health`, `/api/health/version`(커밋·리비전·코드표 체크섬이 다른 자치회와 같은지, R24), 백업 한 번 실행과 복구시험

다른 자치회의 DB와 연결하거나 데이터를 옮기지 않는다. 이 절차는 스크립트로 묶지 않았다(서버 확인 뒤 반복되는 부분만 자동화한다).

## 7. 아직 하지 않은 것

- 6장 절차를 스크립트로 묶는 일(실제 서버에서 한 번 해 본 뒤)