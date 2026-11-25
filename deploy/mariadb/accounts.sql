-- 초안(미검증): 서버에서 확인하기 전에는 운영 DB에 적용하지 않는다.
-- 이 파일은 app.tools.generate_grants가 만든다. 직접 고치지 않는다.
-- 1단계: 마이그레이션 전에 적용한다. 2단계 grants.sql은 마이그레이션 뒤에 적용한다.
-- 비밀번호 자리표시({{...}})는 서버에서 바꿔 넣고 이 파일에 실제 값을 남기지 않는다.
CREATE DATABASE IF NOT EXISTS `jori` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'app_jori'@'127.0.0.1' IDENTIFIED BY '{{APP_PASSWORD}}';
CREATE USER IF NOT EXISTS 'worker_jori'@'127.0.0.1' IDENTIFIED BY '{{WORKER_PASSWORD}}';
CREATE USER IF NOT EXISTS 'backup_jori'@'127.0.0.1' IDENTIFIED BY '{{BACKUP_PASSWORD}}';
CREATE USER IF NOT EXISTS 'migrate_jori'@'127.0.0.1' IDENTIFIED BY '{{MIGRATE_PASSWORD}}';

-- 배포 때만 쓰는 마이그레이션 계정(구조 변경 권한). API·워커는 구조를 바꾸지 못한다
GRANT ALL PRIVILEGES ON `jori`.* TO 'migrate_jori'@'127.0.0.1';

-- backup_jori: mariabackup이 요구하는 전역 권한만(데이터는 읽지 않는다)
GRANT RELOAD, PROCESS, LOCK TABLES, BINLOG MONITOR ON *.* TO 'backup_jori'@'127.0.0.1';

FLUSH PRIVILEGES;
