# 수강신청 생성. 강좌 행 잠금 아래에서 정원·대기를 세고 자리를 배정한다(TDD 5.2, ADR-028, FN-033~039)
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_ATNLC_APLY, TB_MBR, TB_RDCT_HSTRY
from app.domain.application.pricing import REDUCTION_REASON, quote
from app.domain.application.schemas import Application
from app.domain.application.seats import count_by_status, lock_course, next_wait_seq
from app.domain.application.service import (
    PAYMENT_WINDOW_SECONDS,
    SEAT_STATUSES,
    first_blocker,
    get_mine,
    has_active_application,
)
from app.domain.course.service import VISIBLE_STATUSES

DUPLICATE_ENTRY = 1062
IDEM_UNIQUE = "UQ_ATNLC_APLY_02"  # (운영묶음, 멱등키) 유일키 이름


def _lock_member(db: Session, member_sn: int) -> Any:
    return db.execute(
        select(
            TB_MBR.c.MBR_SN,
            TB_MBR.c.OPER_BNDL_SN,
            TB_MBR.c.MBR_STTS_CD,
            TB_MBR.c.HAB_RGN_CD,
            TB_MBR.c.HAB_IDNTY_STTS_CD,
        )
        .where(TB_MBR.c.MBR_SN == member_sn)
        .with_for_update()
    ).one()


def create_application(
    db: Session,
    *,
    member_sn: int,
    bundle_sn: int,
    course_id: str,
    idem_key: str,
    request_id: str,
    now: datetime,
) -> Application:
    course_sn = int(course_id)
    course = lock_course(db, bundle_sn, course_sn)
    if course is None or course.CORS_STTS_CD not in VISIBLE_STATUSES:
        raise ApiError(ErrorCode.NOT_FOUND)
    member = _lock_member(db, member_sn)

    # 같은 멱등키: 같은 회원·강좌면 이전 결과, 다르면 충돌(FN-033). 잠금을 얻은 뒤 보므로 동시 재전송도 걸린다.
    prior = db.execute(
        select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_ATNLC_APLY.c.MBR_SN, TB_ATNLC_APLY.c.CORS_SN).where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.IDEM_KEY == idem_key
        )
    ).first()
    if prior is not None:
        if (int(prior.MBR_SN), int(prior.CORS_SN)) != (member_sn, course_sn):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return get_mine(db, member_sn, bundle_sn, str(int(prior.ATNLC_APLY_SN)), now)

    occupied = count_by_status(db, bundle_sn, course_sn, SEAT_STATUSES)
    waiting = count_by_status(db, bundle_sn, course_sn, ("ES.WAIT",))
    blocker = first_blocker(
        member=member,
        course=course,
        already_applied=has_active_application(db, bundle_sn, member_sn, course_sn),
        occupied=occupied,
        waiting=waiting,
        now=now,
    )
    if blocker is not None:
        raise ApiError(blocker)

    price = quote(db, member, course, now)
    values: dict[str, Any] = {
        "OPER_BNDL_SN": bundle_sn,
        "MBR_SN": member_sn,
        "CORS_SN": course_sn,
        "APLY_DT": now,
        "REG_DT": now,
        "TTCHG_AMT": price.fee,
        "RDCT_AMT": price.reduction,
        "STLM_PRNMNT_AMT": price.payable,
        "IDEM_KEY": idem_key,
    }
    if price.approval is not None and price.reduction > 0:
        values["RDCT_RSN"] = REDUCTION_REASON[price.approval.type_code]
        values["RDCT_MNGR_SN"] = price.approval.reviewer_sn
    # 대기자가 있으면 빈자리가 있어도 새 신청이 가로채지 못한다. 자리가 있고 대기자가 없을 때만 바로 배정한다.
    if waiting == 0 and occupied < int(course.RCRT_NOPE):
        values["SEAT_ALTMNT_DT"] = now
        if price.payable == 0:
            values["APLY_STTS_CD"] = "ES.CONFIRM"
        else:
            values["APLY_STTS_CD"] = "ES.HOLD"
            values["STLM_DDLN_DT"] = now + timedelta(seconds=PAYMENT_WINDOW_SECONDS)
    else:
        values["APLY_STTS_CD"] = "ES.WAIT"
        values["WTNG_SEQ"] = next_wait_seq(db, bundle_sn, course_sn)

    try:
        application_sn = int(
            db.execute(
                insert(TB_ATNLC_APLY).values(**values).returning(TB_ATNLC_APLY.c.ATNLC_APLY_SN)
            ).scalar_one()
        )
    except IntegrityError as error:
        raise _business_error(error) from None

    if price.approval is not None and price.reduction > 0:
        # 감면 이력은 INSERT만 한다. 이 행이 있어야 같은 기수에 감면을 다시 쓰지 못한다(RDCT-BFHD-02)
        db.execute(
            insert(TB_RDCT_HSTRY).values(
                OPER_BNDL_SN=bundle_sn,
                ATNLC_APLY_SN=application_sn,
                DCSN_RSLT_CD="DR.APPROVE",
                RDCT_AMT=price.reduction,
                DCSN_RSN=REDUCTION_REASON[price.approval.type_code],
                DCSN_MNGR_SN=price.approval.reviewer_sn,
                DCSN_DT=now,
                REG_DT=now,
                RDCT_BFHD_SRNG_SN=price.approval.sn,
            )
        )
    record_job(
        db,
        actor="AK.MEMBER",
        job="APLY_CREATE",
        table="TB_ATNLC_APLY",
        key=application_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"신청 생성({values['APLY_STTS_CD']})",
    )
    return get_mine(db, member_sn, bundle_sn, str(application_sn), now)


def _business_error(error: IntegrityError) -> Exception:
    """유일키가 막은 중복을 업무 오류로 바꾼다. 잠금 아래에서는 일어나지 않아야 하는 마지막 방어선이다."""
    if error.orig is None or error.orig.args[0] != DUPLICATE_ENTRY:
        return error
    # 같은 멱등키가 다른 강좌의 요청과 동시에 들어오면 강좌 잠금이 서로 달라 여기서 막힌다
    if IDEM_UNIQUE in str(error.orig.args[1]):
        return ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return ApiError(ErrorCode.APLY_ALREADY_APPLIED)
