# 설계안의 테이블·시퀀스 목록으로 DB 계정·권한 SQL을 만든다. 초안이다(ADR-102)
import sys
from pathlib import Path

from app.tools.schema_ddl import sequence_name
from app.tools.schema_doc import SchemaDoc, parse_schema_doc

OUTPUT = Path(__file__).resolve().parents[4] / "deploy" / "mariadb" / "accounts.sql"
DATABASE = "jori"
HOST = "127.0.0.1"
AUDIT_TABLE = "TB_JOB_HSTRY"  # 작업 이력은 쌓기만 하고 고치거나 지우지 않는다(TDD 11장)
DML = "SELECT, INSERT, UPDATE, DELETE"
APPEND_ONLY = "SELECT, INSERT"
USERS = {  # 계정 이름: 비밀번호 자리표시. 실제 비밀번호는 서버에서 바꿔 넣고 저장소에 두지 않는다
    f"app_{DATABASE}": "{{APP_PASSWORD}}",
    f"worker_{DATABASE}": "{{WORKER_PASSWORD}}",
    f"backup_{DATABASE}": "{{BACKUP_PASSWORD}}",
    f"migrate_{DATABASE}": "{{MIGRATE_PASSWORD}}",
}


def _grant(privileges: str, obj: str, user: str) -> str:
    return f"GRANT {privileges} ON `{DATABASE}`.`{obj}` TO '{user}'@'{HOST}';"


def render(schema: SchemaDoc) -> str:
    sequences = sorted(name for name in (sequence_name(table) for table in schema.tables) if name)
    tables = sorted(table.name for table in schema.tables)
    lines = [
        "-- 초안(미검증): 서버에서 확인하기 전에는 운영 DB에 적용하지 않는다.",
        "-- 이 파일은 app.tools.generate_grants가 만든다. 직접 고치지 않는다.",
        "-- 비밀번호 자리표시({{...}})는 서버에서 바꿔 넣고 이 파일에 실제 값을 남기지 않는다.",
        f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        "",
    ]
    lines += [
        f"CREATE USER IF NOT EXISTS '{user}'@'{HOST}' IDENTIFIED BY '{secret}';"
        for user, secret in USERS.items()
    ]
    lines += ["", "-- 배포 때만 쓰는 마이그레이션 계정(구조 변경 권한). API·워커는 구조를 바꾸지 못한다"]
    lines.append(f"GRANT ALL PRIVILEGES ON `{DATABASE}`.* TO 'migrate_{DATABASE}'@'{HOST}';")
    for user in (f"app_{DATABASE}", f"worker_{DATABASE}"):
        lines += [
            "",
            f"-- {user}: 업무 테이블 읽기·쓰기, 작업 이력은 쌓기만, 시퀀스는 번호 발급, 버전은 읽기",
        ]
        lines += [_grant(APPEND_ONLY if name == AUDIT_TABLE else DML, name, user) for name in tables]
        lines += [
            _grant(APPEND_ONLY, name, user) for name in sequences
        ]  # NEXTVAL은 시퀀스에 INSERT가 필요하다
        lines.append(_grant("SELECT", "alembic_version", user))
    backup = f"backup_{DATABASE}"
    lines += [
        "",
        f"-- {backup}: mariabackup이 요구하는 전역 권한만(데이터는 읽지 않는다)",
        f"GRANT RELOAD, PROCESS, LOCK TABLES, BINLOG MONITOR ON *.* TO '{backup}'@'{HOST}';",
        "",
        "FLUSH PRIVILEGES;",
        "",
    ]
    return "\n".join(lines)


def generate() -> str:
    return render(parse_schema_doc())


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("사용법 python -m app.tools.generate_grants", file=sys.stderr)
        return 2
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generate(), encoding="utf-8", newline="\n")
    print(f"썼습니다 {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
