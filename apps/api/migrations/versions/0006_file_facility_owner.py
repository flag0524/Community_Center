# 첨부파일의 소유 업무에 시설·강의실을 더하고 소유자·일련번호 검사를 다시 만든다(스키마 v0.9, ADR-129)
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OWNERS = (
    "PST_SN",
    "CORS_SN",
    "INSTR_SN",
    "SITE_CONTS_SN",
    "ATNLC_APLY_SN",
    "RFND_SN",
    "INSTR_APLY_SN",
    "MBR_STATS_SRC_SN",
    "RDCT_BFHD_SRNG_SN",
    "CORS_DGSTFN_SRC_SN",
)
# 0001의 CK_R27_SN_FILE이 검사하던 열(순서 그대로)
SERIALS = ("FILE_SN", "OPER_BNDL_SN", *OWNERS)


def _checks(owners: tuple[str, ...], serials: tuple[str, ...]) -> None:
    owner = " + ".join(f"({name} IS NOT NULL)" for name in owners)
    positive = " AND ".join(f"({name} IS NULL OR {name} > 0)" for name in serials)
    op.execute(
        "ALTER TABLE TB_FILE DROP CONSTRAINT CK_R18_OWNER, DROP CONSTRAINT CK_R27_SN_FILE, "
        f"ADD CONSTRAINT CK_R18_OWNER CHECK ({owner} = 1), "
        f"ADD CONSTRAINT CK_R27_SN_FILE CHECK ({positive})"
    )


def upgrade() -> None:
    op.add_column("TB_FILE", sa.Column("FCLT_SN", sa.Numeric(22, 0), nullable=True, comment="시설일련번호"))
    op.create_index("IX_FILE_FCLT", "TB_FILE", ["OPER_BNDL_SN", "FCLT_SN"])
    op.create_foreign_key(
        "FK_FILE_14",
        "TB_FILE",
        "TB_FCLT",
        ["OPER_BNDL_SN", "FCLT_SN"],
        ["OPER_BNDL_SN", "FCLT_SN"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )
    _checks((*OWNERS, "FCLT_SN"), (*SERIALS, "FCLT_SN"))


def downgrade() -> None:
    # 시설 사진 행이 남아 있으면 소유자 하나 검사가 되돌리기를 막는다. 데이터를 잃지 않으려는 의도다
    _checks(OWNERS, SERIALS)
    op.drop_constraint("FK_FILE_14", "TB_FILE", type_="foreignkey")
    op.drop_index("IX_FILE_FCLT", table_name="TB_FILE")
    op.drop_column("TB_FILE", "FCLT_SN")
