# 배포 후속 초안(권한 SQL, 백업·복구시험·배포 스크립트, 타이머)이 서로·앱과 맞는지 보는 시험(ADR-102)
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.tools.generate_grants import AUDIT_TABLE, generate
from app.tools.schema_ddl import sequence_name
from app.tools.schema_doc import parse_schema_doc
from app.worker.schedule import DAILY_HOURS

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
SCRIPTS = ["deploy.sh", "backup/backup.sh", "backup/binlog-sync.sh", "backup/restore-check.sh"]
SERVER_PATH = "/opt/jori/current/deploy/"  # 유닛이 부르는 스크립트의 서버 쪽 위치


def find_bash() -> str | None:
    """윈도에서는 WSL이 아니라 Git의 bash를 쓴다. 없으면 시험을 건너뛴다."""
    if sys.platform == "win32":
        git = shutil.which("git")
        candidate = None if git is None else Path(git).resolve().parents[1] / "bin" / "bash.exe"
        return str(candidate) if candidate is not None and candidate.exists() else None
    return shutil.which("bash")


def posix(path: Path) -> str:
    text = str(path)
    if sys.platform == "win32" and len(text) > 1 and text[1] == ":":
        return "/" + text[0].lower() + text[2:].replace("\\", "/")
    return text


BASH = find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash가 없다")


def bash(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=60, check=False
    )


# --- DB 계정 권한 SQL ------------------------------------------------------------------------


def test_계정_SQL은_설계안에서_만든_것과_같다() -> None:
    committed = (DEPLOY / "mariadb/accounts.sql").read_text(encoding="utf-8")
    assert committed == generate(), "python -m app.tools.generate_grants 로 다시 만든다"


def test_API와_워커_계정은_모든_테이블과_시퀀스에_필요한_권한만_갖는다() -> None:
    schema = parse_schema_doc()
    sql = generate()
    tables = {table.name for table in schema.tables}
    sequences = {name for name in (sequence_name(table) for table in schema.tables) if name}
    assert len(tables) == 45 and sequences
    for user in ("app_jori", "worker_jori"):
        grants = re.findall(rf"GRANT (.+?) ON `jori`\.`(\w+)` TO '{user}'@", sql)
        by_object = {obj: privileges for privileges, obj in grants}
        assert set(by_object) == tables | sequences | {"alembic_version"}
        assert all(by_object[t] == "SELECT, INSERT, UPDATE, DELETE" for t in tables - {AUDIT_TABLE})
        assert by_object[AUDIT_TABLE] == "SELECT, INSERT"  # 작업 이력은 고치거나 지우지 못한다
        assert all(by_object[s] == "SELECT, INSERT" for s in sequences)  # NEXTVAL
        assert by_object["alembic_version"] == "SELECT"


def test_구조_변경_권한은_마이그레이션_계정에만_있고_백업_계정은_전역_읽기_권한만이다() -> None:
    sql = generate()
    all_grants = re.findall(r"GRANT ALL PRIVILEGES ON .+? TO '(\w+)'@", sql)
    assert all_grants == ["migrate_jori"]
    backup = re.findall(r"GRANT (.+?) ON \*\.\* TO 'backup_jori'@", sql)
    assert backup == ["RELOAD, PROCESS, LOCK TABLES, BINLOG MONITOR"]
    assert "'backup_jori'@'127.0.0.1' IDENTIFIED" in sql and "`jori`" in sql


def test_다른_자치회_이름으로도_같은_모양의_계정_SQL을_만든다() -> None:
    base, other = generate(), generate("hwaseong")
    assert other == base.replace("jori", "hwaseong")  # 이름만 다르고 권한 구조는 같다
    assert "CREATE DATABASE IF NOT EXISTS `hwaseong`" in other and "app_hwaseong" in other
    for bad in ("Jori", "a", "1abc", "has-dash", "x" * 17, ""):
        with pytest.raises(ValueError, match="인스턴스 이름"):
            generate(bad)


def test_계정_SQL에는_실제_비밀번호가_없고_자리표시만_있다() -> None:
    sql = generate()
    secrets = re.findall(r"IDENTIFIED BY '([^']*)'", sql)
    assert len(secrets) == 4 and all(re.fullmatch(r"\{\{[A-Z]+_PASSWORD\}\}", s) for s in secrets)


# --- 스크립트 --------------------------------------------------------------------------------


@needs_bash
@pytest.mark.parametrize("name", SCRIPTS)
def test_스크립트는_문법이_맞고_실패하면_멈추고_dry_run을_받는다(name: str) -> None:
    path = DEPLOY / name
    result = bash("-n", posix(path))
    assert result.returncode == 0, result.stderr
    text = path.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text and "--dry-run" in text and "초안(미검증)" in text
    assert b"\r" not in path.read_bytes()  # 리눅스에서 줄 끝 문자 때문에 깨지지 않게


@needs_bash
def test_백업_dry_run은_순서를_보이기만_하고_아무것도_만들지_않는다(tmp_path: Path) -> None:
    config = tmp_path / "etc"
    config.mkdir()
    backups = tmp_path / "backups"
    (config / "jori.backup.env").write_text(
        f"JORI_BACKUP_DIR={posix(backups)}\nJORI_BACKUP_KEYFILE=/k\nJORI_BACKUP_DEFAULTS_FILE=/c\n"
        "JORI_FILE_ROOT=/data/files\nJORI_BACKUP_DEST=backup@host:/b\n",
        encoding="utf-8",
    )
    env = {"PATH": "/usr/bin:/bin", "JORI_CONFIG_DIR": posix(config)}
    result = bash(posix(DEPLOY / "backup/backup.sh"), "jori", "--dry-run", env=env)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    order = [
        out.index(word)
        for word in (
            "mariabackup",
            "rsync -a /data/files/",
            "sha256sum",
            "backup@host:/b/jori/",
            "-mtime +30",
        )
    ]
    assert order == sorted(order)  # 데이터베이스 → 첨부 → 해시 → 전송 → 정리
    assert "openssl enc -aes-256-cbc -pbkdf2" in out
    assert not backups.exists()


@needs_bash
def test_백업_설정이_없으면_실패하고_별도_저장소가_비면_로컬에만_둔다고_알린다(tmp_path: Path) -> None:
    missing = bash(
        posix(DEPLOY / "backup/backup.sh"),
        "jori",
        env={"PATH": "/usr/bin:/bin", "JORI_CONFIG_DIR": posix(tmp_path)},
    )
    assert missing.returncode == 2 and "설정 파일이 없습니다" in missing.stderr
    (tmp_path / "jori.backup.env").write_text(
        "JORI_BACKUP_DIR=/b\nJORI_BACKUP_KEYFILE=/k\nJORI_BACKUP_DEFAULTS_FILE=/c\nJORI_FILE_ROOT=/f\n",
        encoding="utf-8",
    )
    local = bash(
        posix(DEPLOY / "backup/backup.sh"),
        "jori",
        "--dry-run",
        env={"PATH": "/usr/bin:/bin", "JORI_CONFIG_DIR": posix(tmp_path)},
    )
    assert local.returncode == 0 and "로컬에만 보관" in local.stderr and "backup@" not in local.stdout


@needs_bash
def test_복구시험은_운영_데이터_폴더를_스테이징으로_쓰지_않는다(tmp_path: Path) -> None:
    (tmp_path / "jori.backup.env").write_text("JORI_BACKUP_KEYFILE=/k\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "JORI_CONFIG_DIR": posix(tmp_path)}
    for bad in ("/var/lib/mysql/x", "/data/jori", "relative/path"):
        result = bash(
            posix(DEPLOY / "backup/restore-check.sh"), "jori", "/backup/one", bad, "--dry-run", env=env
        )
        assert result.returncode == 2, bad
    ok = bash(
        posix(DEPLOY / "backup/restore-check.sh"),
        "jori",
        "/backup/one",
        "/restore/stage",
        "--dry-run",
        env=env,
    )
    assert ok.returncode == 0 and "sha256sum -c SHA256SUMS" in ok.stdout and "mbstream -x" in ok.stdout


@needs_bash
def test_배포_dry_run은_일곱_단계를_순서대로_보이고_커밋_형식을_검사한다(tmp_path: Path) -> None:
    env = {"PATH": "/usr/bin:/bin", "JORI_CONFIG_DIR": posix(tmp_path)}
    result = bash(posix(DEPLOY / "deploy.sh"), "jori", "abc1234", "/tmp/build.tar.gz", "--dry-run", env=env)
    assert result.returncode == 0, result.stderr
    steps = re.findall(r"== (\d)/7", result.stdout)
    assert steps == [str(n) for n in range(1, 8)]
    out = result.stdout
    # 백업이 마이그레이션보다 앞이고, 전환은 마이그레이션 뒤이며, 건강 확인이 마지막이다
    assert (
        out.index("backup.sh")
        < out.index("alembic upgrade head")
        < out.index("ln -sfn")
        < out.index("api/health/version")
    )
    assert "JORI_BUILD_COMMIT" in out
    bad = bash(posix(DEPLOY / "deploy.sh"), "jori", "not-a-hash", "/tmp/x", "--dry-run", env=env)
    assert bad.returncode == 2 and "커밋 해시 형식" in bad.stderr


def test_배포_스크립트는_구조_변경에_마이그레이션_계정을_쓰고_실패하면_되돌린다() -> None:
    text = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert re.search(r'JORI_DATABASE_URL="\$JORI_MIGRATE_DATABASE_URL" ".+alembic" upgrade head', text)
    assert "trap rollback ERR" in text
    assert "자동으로 되돌리지 않았습니다" in text  # DB는 사람이 판단한다
    example = (DEPLOY / "env/jori.migrate.env.example").read_text(encoding="utf-8")
    assert "migrate_jori" in example and "CHANGE_ME" in example


# --- 타이머와 환경 예시 -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["jori-backup@", "jori-binlog-sync@"])
def test_백업_유닛은_존재하는_스크립트를_부르고_타이머는_주기를_갖는다(name: str) -> None:
    service = (DEPLOY / "systemd" / f"{name}.service").read_text(encoding="utf-8")
    exec_line = re.search(r"^ExecStart=(\S+) %i$", service, re.M)
    assert exec_line is not None and exec_line.group(1).startswith(SERVER_PATH)
    assert (DEPLOY / exec_line.group(1).removeprefix(SERVER_PATH)).exists()
    assert "Type=oneshot" in service
    timer = (DEPLOY / "systemd" / f"{name}.timer").read_text(encoding="utf-8")
    assert re.search(r"^OnCalendar=", timer, re.M) and "Persistent=true" in timer


def test_일일_백업은_워커의_일일_작업보다_먼저_돌고_로그는_15분마다_보낸다() -> None:
    timer = (DEPLOY / "systemd/jori-backup@.timer").read_text(encoding="utf-8")
    hour = int(re.search(r"^OnCalendar=\*-\*-\* (\d\d):", timer, re.M).group(1))  # type: ignore[union-attr]
    assert hour < min(DAILY_HOURS.values())
    assert "OnCalendar=*:0/15" in (DEPLOY / "systemd/jori-binlog-sync@.timer").read_text(encoding="utf-8")


def test_백업_환경_예시는_스크립트가_필수로_읽는_변수를_모두_갖는다() -> None:
    example = (DEPLOY / "env/jori.backup.env.example").read_text(encoding="utf-8")
    defined = set(re.findall(r"^(JORI_[A-Z_]+)=", example, re.M))
    needed: set[str] = set()
    for name in SCRIPTS[1:]:
        text = (DEPLOY / name).read_text(encoding="utf-8")
        needed |= set(re.findall(r"\$\{(JORI_[A-Z_]+)(?::\?|:=)", text))
    assert needed - {"JORI_CONFIG_DIR"} <= defined, needed - defined
    assert "JORI_BACKUP_KEYFILE=" in example and "CHANGE_ME" not in example.split("JORI_BACKUP_KEYFILE")[0]


def test_워커_유닛은_전용_DB_계정_설정을_있으면_덮어쓰는_선택_파일로_읽는다() -> None:
    lines = [
        line.split("=", 1)[1]
        for line in (DEPLOY / "systemd/jori-worker@.service").read_text(encoding="utf-8").splitlines()
        if line.startswith("EnvironmentFile=")
    ]
    assert lines == ["/etc/jori/%i.env", "-/etc/jori/%i.worker.env"]  # 앞의 -는 파일이 없어도 시작한다
