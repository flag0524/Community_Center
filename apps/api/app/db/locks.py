# 인증 발급·소비·파기가 공유하는 부모 행 잠금. 인증 행보다 먼저 획득한다.
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tables import TB_OPER_BNDL


def lock_bundle(db: Session, bundle_sn: int) -> None:
    db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN).where(TB_OPER_BNDL.c.OPER_BNDL_SN == bundle_sn).with_for_update()
    ).scalar_one()
