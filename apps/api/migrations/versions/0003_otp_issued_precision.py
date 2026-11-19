# 발급 시각의 소수초를 보존해 60초 이전 재발급을 막는다. 기존 행은 그대로 둔다.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "TB_CERT_DMND",
        "REG_DT",
        existing_type=mysql.DATETIME(),
        type_=mysql.DATETIME(fsp=6),
        existing_nullable=False,
        existing_comment="등록일시",
        existing_server_default=sa.text("CURRENT_TIMESTAMP"),
        server_default=sa.text("CURRENT_TIMESTAMP(6)"),
    )


def downgrade() -> None:
    op.alter_column(
        "TB_CERT_DMND",
        "REG_DT",
        existing_type=mysql.DATETIME(fsp=6),
        type_=mysql.DATETIME(),
        existing_nullable=False,
        existing_comment="등록일시",
        existing_server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
