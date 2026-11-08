# 스키마 설계안 v0.5의 45개 테이블·키·외래키·검사·공통코드를 만드는 첫 마이그레이션(SQL은 생성기가 만든 파일)
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_HERE = Path(__file__).resolve().parent


def _run(name: str) -> None:
    """생성기가 만든 파일은 문장마다 ';' 뒤에 빈 줄을 둔다. 문장 안에는 빈 줄이 없다."""
    text = (_HERE / name).read_text(encoding="utf-8")
    for statement in text.split(";\n\n"):
        lines = [line for line in statement.split("\n") if not line.startswith("--")]
        body = "\n".join(lines).strip()
        if body:
            op.execute(body)


def upgrade() -> None:
    _run("0001_initial_schema.up.sql")


def downgrade() -> None:
    _run("0001_initial_schema.down.sql")
