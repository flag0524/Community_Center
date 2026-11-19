# 콘텐츠 유형(CT)에 홈 비주얼 코드를 더한다. 기존 행은 건드리지 않고 이미 있으면 다시 넣지 않는다
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

CODE = "CT.VISUAL"


def upgrade() -> None:
    op.execute(
        "INSERT INTO TB_COM_CD (COM_CD, CD_GROUP_ID, CD_NM, SORT_SEQ) "
        f"SELECT '{CODE}', 'CT', '홈비주얼', 13 FROM DUAL "
        f"WHERE NOT EXISTS (SELECT 1 FROM TB_COM_CD WHERE COM_CD = '{CODE}')"
    )


def downgrade() -> None:
    # 이 코드를 쓰는 콘텐츠가 있으면 FK(RESTRICT)가 지우기를 막는다. 데이터를 잃지 않으려는 의도다
    op.execute(f"DELETE FROM TB_COM_CD WHERE COM_CD = '{CODE}'")
