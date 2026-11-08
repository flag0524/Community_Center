# 스키마 설계안에서 첫 마이그레이션의 적용·되돌리기 SQL 파일을 만드는 명령
import sys
from pathlib import Path

from app.tools.schema_checks import problems as check_problems
from app.tools.schema_ddl import down_statements, identifier_problems, render, up_statements
from app.tools.schema_doc import parse_schema_doc, validate
from app.tools.schema_tables import render_tables

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
TABLES = Path(__file__).resolve().parents[1] / "db" / "tables.py"
HEADER = (
    "-- app.tools.generate_ddl이 스키마 설계안에서 만든 파일이다. 직접 고치지 않는다.\n"
    "-- 배포한 뒤에는 이 파일을 고치지 않고 새 버전을 더한다.\n\n"
)


def generate() -> dict[str, str]:
    """파일 이름과 내용을 돌려준다. 문서가 일관적이지 않으면 만들지 않고 예외를 던진다."""
    schema = parse_schema_doc()
    problems = validate(schema) + identifier_problems(schema) + check_problems(schema)
    if problems:
        raise ValueError("스키마 설계안에 문제가 있어 만들지 않는다:\n" + "\n".join(problems))
    return {
        "0001_initial_schema.up.sql": HEADER + render(up_statements(schema)),
        "0001_initial_schema.down.sql": HEADER + render(down_statements(schema)),
        "tables.py": render_tables(schema),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("사용법 python -m app.tools.generate_ddl", file=sys.stderr)
        return 2
    MIGRATIONS.mkdir(parents=True, exist_ok=True)
    TABLES.parent.mkdir(parents=True, exist_ok=True)
    for name, content in generate().items():
        target = TABLES if name == "tables.py" else MIGRATIONS / name
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"썼습니다 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
