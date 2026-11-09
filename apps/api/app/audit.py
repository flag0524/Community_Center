# 업무 감사이력 기록(TB_JOB_HSTRY). INSERT만 하고 비밀값·개인정보 원문은 넣지 않는다(ADR-025, C10)
from datetime import datetime
from typing import Literal

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.tables import TB_JOB_HSTRY

Actor = Literal["AK.MEMBER", "AK.ADMIN", "AK.SYSTEM", "AK.ANON"]


def record_job(
    db: Session,
    *,
    actor: Actor,
    job: str,
    table: str,
    key: int | str | None,
    request_id: str,
    now: datetime,
    bundle_sn: int | None = None,
    member_sn: int | None = None,
    admin_sn: int | None = None,
    result: Literal["JR.SUCCESS", "JR.FAIL", "JR.DENY"] = "JR.SUCCESS",
    change: str | None = None,
) -> None:
    """회원이면 묶음·회원이, 관리자면 관리자가 필수다(R21). change에는 값이 아니라 바뀐 항목만 적는다."""
    db.execute(
        insert(TB_JOB_HSTRY).values(
            OPER_BNDL_SN=bundle_sn,
            ACTR_TYPE_CD=actor,
            MNGR_SN=admin_sn,
            MBR_SN=member_sn,
            JOB_CD=job,
            TRGT_TBL_NM=table,
            TRGT_KEY_VL=None if key is None else str(key),
            JOB_RSLT_CD=result,
            DMND_ID=request_id,
            CHG_CN=change,
            REG_DT=now,
        )
    )
