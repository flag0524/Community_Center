# 본인 신청 취소. 자리를 쥐고 있던 신청이면 같은 잠금 아래에서 대기자를 승격한다(TDD 5.7, FN-037)
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_ATNLC_APLY, TB_STLM
from app.domain.application.schemas import Application
from app.domain.application.seats import lock_course, promote_waiters, set_status
from app.domain.application.service import SEAT_STATUSES, get_mine
from app.domain.application.types import ApplicationDisplayState

SELF_CANCEL_REASON = "본인 취소"


def cancel_application(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    application_id: str,
    request_id: str,
    now: datetime,
) -> Application:
    application_sn = int(application_id)
    owned = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN).where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn,
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
        )
    ).first()
    if owned is None:  # 남의 신청은 없는 신청과 같다(RQ-SER-NF-001)
        raise ApiError(ErrorCode.NOT_FOUND)
    # 잠금 순서는 강좌 → 신청이다(C07). 잠금을 얻은 뒤의 상태로 다시 판정한다.
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))
    row = db.execute(
        select(TB_ATNLC_APLY.c.APLY_STTS_CD)
        .where(TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
        .with_for_update()
    ).one()
    if row.APLY_STTS_CD == "ES.CANCEL":
        return get_mine(db, member_sn, bundle_sn, application_id, now)  # 이미 취소됐다. 같은 결과를 돌려준다
    current = get_mine(db, member_sn, bundle_sn, application_id, now)
    if not current.can_cancel:
        if current.display_state is ApplicationDisplayState.PAYMENT_UNKNOWN:
            raise ApiError(ErrorCode.PAY_RESULT_PENDING)
        raise ApiError(ErrorCode.APLY_CANCEL_NOT_ALLOWED)

    held_seat = row.APLY_STTS_CD in SEAT_STATUSES
    # 아직 승인 전인 결제창 발급분은 함께 취소한다. 승인 결과를 기다리는 결제가 있으면 위에서 이미 막았다.
    db.execute(
        update(TB_STLM)
        .where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM.c.ATNLC_APLY_SN == application_sn,
            TB_STLM.c.STLM_STTS_CD == "PS.READY",
        )
        .values(STLM_STTS_CD="PS.CANCEL", MDFCN_DT=now, RCRD_VER=TB_STLM.c.RCRD_VER + 1)
    )
    set_status(db, application_sn, status="ES.CANCEL", now=now, reason=SELF_CANCEL_REASON)
    record_job(
        db,
        actor="AK.MEMBER",
        job="APLY_CANCEL",
        table="TB_ATNLC_APLY",
        key=application_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"본인 취소(이전 상태 {row.APLY_STTS_CD})",
    )
    if held_seat:  # 대기 신청이 빠지는 것은 자리를 돌려주지 않는다
        promote_waiters(db, settings, course, now=now, request_id=request_id)
    return get_mine(db, member_sn, bundle_sn, application_id, now)
