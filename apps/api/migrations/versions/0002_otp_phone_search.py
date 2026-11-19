# 기존 인증 요청을 보존하며 전화번호별 OTP 제한의 HMAC 검색키와 인덱스를 추가한다
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "TB_CERT_DMND",
        sa.Column("TELNO_SRCH_HASH_VL", sa.CHAR(64), nullable=True, comment="전화번호검색해시값"),
    )
    op.create_index("IX_CERT_DMND_03", "TB_CERT_DMND", ["OPER_BNDL_SN", "TELNO_SRCH_HASH_VL", "REG_DT"])


def downgrade() -> None:
    op.drop_index("IX_CERT_DMND_03", table_name="TB_CERT_DMND")
    op.drop_column("TB_CERT_DMND", "TELNO_SRCH_HASH_VL")
