# 수강신청 조회(신청 화면 미리보기, 내 신청 목록·상세). 가능 여부와 화면 상태는 서버가 판정한다(FN-014, 025, 037)
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import DEFAULT_MESSAGES, ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_ymd, utc
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_MBR, TB_RFND, TB_STLM
from app.domain.application.pricing import is_resident, quote
from app.domain.application.schemas import (
    Application,
    ApplicationPage,
    ApplicationSummary,
    ApplyPreview,
    Eligibility,
)
from app.domain.application.types import ApplicationDisplayState as Display
from app.domain.application.types import ApplicationStatus
from app.domain.course.service import course_query, reception_state, summaries, visible_course
from app.domain.course.types import ReceptionState
from app.domain.payment.types import PaymentStatus
from app.domain.refund.types import RefundStage

PAYMENT_WINDOW_SECONDS = 600  # 자리 배정 시각부터 결제할 수 있는 시간(SEAT-01)
ACTIVE = ("ES.WAIT", "ES.HOLD", "ES.CONFIRM")  # 같은 강좌에 하나만 둘 수 있는 신청 상태
SEAT_STATUSES = ("ES.HOLD", "ES.CONFIRM")  # 정원을 차지하는 신청 상태(ADR-028)

STATUS = {
    "ES.WAIT": ApplicationStatus.WAITING,
    "ES.HOLD": ApplicationStatus.HOLD,
    "ES.CONFIRM": ApplicationStatus.CONFIRMED,
    "ES.CANCEL": ApplicationStatus.CANCELLED,
    "ES.EXPIRE": ApplicationStatus.EXPIRED,
    "ES.COMPLETE": ApplicationStatus.COMPLETED,
}
PAYMENT = {
    "PS.READY": PaymentStatus.READY,
    "PS.PENDING": PaymentStatus.PENDING,
    "PS.PAID": PaymentStatus.PAID,
    "PS.FAIL": PaymentStatus.FAILED,
    "PS.CANCEL": PaymentStatus.CANCELLED,
}
REFUND_STAGE = {
    "RS.REQUEST": RefundStage.RECEIVED,
    "RS.HOLD": RefundStage.ON_HOLD,
    "RS.APPROVE": RefundStage.PROCESSING,
    "RS.PENDING": RefundStage.PROCESSING,
    "RS.FAIL": RefundStage.PROCESSING,
    "RS.DONE": RefundStage.DONE,
    "RS.REJECT": RefundStage.REJECTED,
}


def load_member(db: Session, member_sn: int) -> Any:
    return db.execute(
        select(
            TB_MBR.c.MBR_SN,
            TB_MBR.c.OPER_BNDL_SN,
            TB_MBR.c.MBR_STTS_CD,
            TB_MBR.c.HAB_RGN_CD,
            TB_MBR.c.HAB_IDNTY_STTS_CD,
        ).where(TB_MBR.c.MBR_SN == member_sn)
    ).one()


def has_active_application(db: Session, bundle_sn: int, member_sn: int, course_sn: int) -> bool:
    return bool(
        db.execute(
            select(
                select(TB_ATNLC_APLY.c.ATNLC_APLY_SN)
                .where(
                    TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
                    TB_ATNLC_APLY.c.MBR_SN == member_sn,
                    TB_ATNLC_APLY.c.CORS_SN == course_sn,
                    TB_ATNLC_APLY.c.APLY_STTS_CD.in_(ACTIVE),
                )
                .exists()
            )
        ).scalar_one()
    )


def first_blocker(
    *,
    member: Any,
    course: Any,
    already_applied: bool,
    occupied: int,
    waiting: int,
    now: datetime,
) -> ErrorCode | None:
    """신청할 수 없는 첫 이유. 신청 생성이 같은 판정을 잠금 아래에서 다시 한다(TDD 5.2의 순서)."""
    if (
        reception_state(str(course.CORS_STTS_CD), course.RCPT_BGNG_DT, course.RCPT_END_DT, now)
        is not ReceptionState.OPEN
    ):
        return ErrorCode.APLY_RCPT_CLOSED
    if member.MBR_STTS_CD != "MS.ACTIVE":
        return ErrorCode.APLY_MEMBER_INACTIVE
    resident = is_resident(member)
    if not resident and (course.OTSD_RGN_RCPT_BGNG_DT is None or now < course.OTSD_RGN_RCPT_BGNG_DT):
        return ErrorCode.APLY_PRIORITY_PERIOD
    if already_applied:
        return ErrorCode.APLY_ALREADY_APPLIED
    seat_free = waiting == 0 and occupied < int(course.RCRT_NOPE)
    # 관외 신청자는 잔여 정원이 없으면 대기도 받지 않는다. 문서가 정하지 않아 보수적으로 둔다(PRD Q5, ADR-037)
    can_wait = resident and waiting < int(course.WTNG_NOPE)
    if not seat_free and not can_wait:
        return ErrorCode.APLY_FULL
    return None


def preview(db: Session, member_sn: int, bundle_sn: int, course_id: str, now: datetime) -> ApplyPreview:
    row = visible_course(db, bundle_sn, course_id)
    member = load_member(db, member_sn)
    applied = has_active_application(db, bundle_sn, member_sn, int(row.CORS_SN))
    blocker = first_blocker(
        member=member,
        course=row,
        already_applied=applied,
        occupied=int(row.OCCUPIED),
        waiting=int(row.WAITING),
        now=now,
    )
    price = quote(db, member, row, now)
    priority_open = row.OTSD_RGN_RCPT_BGNG_DT is None or now < row.OTSD_RGN_RCPT_BGNG_DT
    return ApplyPreview(
        server_now=utc(now),
        course=summaries(db, bundle_sn, [row], now)[0],
        fee=price.fee,
        reduction_amount=price.reduction,
        payable_amount=price.payable,
        payment_window_seconds=PAYMENT_WINDOW_SECONDS,
        eligibility=Eligibility(
            can_apply=blocker is None,
            reason_code=blocker,
            reason_message=None if blocker is None else DEFAULT_MESSAGES[blocker],
        ),
        resident_priority_active=priority_open,
        already_applied=applied,
    )


# --- 내 신청 -------------------------------------------------------------------------


@dataclass(frozen=True)
class Flags:
    display: Display
    can_cancel: bool
    can_pay: bool
    can_request_refund: bool


def flags(row: Any, payment: PaymentStatus | None, refund: RefundStage | None, now: datetime) -> Flags:
    """신청 상태와 결제·환불 상태를 합쳐 화면 상태와 가능한 행동을 정한다(TDD 5.1)."""
    status = str(row.APLY_STTS_CD)
    unknown = (
        payment is PaymentStatus.PENDING
    )  # 승인 결과 확인 중에는 취소·재결제·환불을 모두 막는다(ADR-006)
    deadline_open = row.STLM_DDLN_DT is not None and now < row.STLM_DDLN_DT
    free = int(row.STLM_PRNMNT_AMT) == 0
    before_start = str(row.EDU_BGNG_YMD) > kst_ymd(now)
    if status == "ES.WAIT":
        return Flags(Display.WAITING, True, False, False)
    if status == "ES.HOLD":
        if unknown:
            return Flags(Display.PAYMENT_UNKNOWN, False, False, False)
        shown = (
            Display.PAYMENT_FAILED
            if payment is PaymentStatus.FAILED and deadline_open
            else Display.PAYMENT_DUE
        )
        return Flags(shown, True, deadline_open, False)
    if status == "ES.CONFIRM":
        refundable = payment is PaymentStatus.PAID and refund in (None, RefundStage.REJECTED)
        # 결제 없는 확정은 환불이 없어 취소가 유일한 길이다. 개강 전까지만 허용한다(PRD Q18, ADR-037)
        return Flags(
            Display.CONFIRMED_FREE if free else Display.CONFIRMED, free and before_start, False, refundable
        )
    if status == "ES.EXPIRE":
        return Flags(Display.EXPIRED, False, False, False)
    if status == "ES.COMPLETE":
        return Flags(Display.COMPLETED, False, False, False)
    closed = str(row.CORS_STTS_CD) == "CS.CANCEL"
    return Flags(Display.COURSE_CLOSED if closed else Display.CANCELLED, False, False, False)


def _my_query(bundle_sn: int, member_sn: int) -> Select[Any]:
    latest_payment = (
        select(func.max(TB_STLM.c.STLM_SN))
        .where(
            TB_STLM.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
            TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        )
        .scalar_subquery()
    )
    return (
        select(
            TB_ATNLC_APLY,
            TB_CORS.c.CORS_STTS_CD,
            TB_CORS.c.EDU_BGNG_YMD,
            latest_payment.label("PAY_SN"),
        )
        .join(
            TB_CORS,
            and_(
                TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
                TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN,
            ),
        )
        .where(TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.MBR_SN == member_sn)
    )


def _summaries(db: Session, bundle_sn: int, rows: list[Any], now: datetime) -> list[ApplicationSummary]:
    if not rows:
        return []
    courses = {
        int(c.CORS_SN): c
        for c in db.execute(
            course_query().where(
                TB_CORS.c.OPER_BNDL_SN == bundle_sn, TB_CORS.c.CORS_SN.in_([int(r.CORS_SN) for r in rows])
            )
        ).all()
    }
    course_summaries = dict(zip(courses, summaries(db, bundle_sn, list(courses.values()), now), strict=True))
    pay_sns = [int(r.PAY_SN) for r in rows if r.PAY_SN is not None]
    payments = (
        {
            int(p.STLM_SN): str(p.STLM_STTS_CD)
            for p in db.execute(
                select(TB_STLM.c.STLM_SN, TB_STLM.c.STLM_STTS_CD).where(
                    TB_STLM.c.OPER_BNDL_SN == bundle_sn, TB_STLM.c.STLM_SN.in_(pay_sns)
                )
            ).all()
        }
        if pay_sns
        else {}
    )
    refunds: dict[int, str] = {}
    if pay_sns:
        for r in db.execute(
            select(TB_RFND.c.STLM_SN, TB_RFND.c.RFND_STTS_CD)
            .where(TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.STLM_SN.in_(pay_sns))
            .order_by(TB_RFND.c.RFND_SN)
        ).all():
            refunds[int(r.STLM_SN)] = str(r.RFND_STTS_CD)  # 같은 결제의 환불이 여럿이면 마지막이 남는다
    waiting_rank = {
        int(r.ATNLC_APLY_SN): rank_in_waitlist(db, bundle_sn, r) for r in rows if r.APLY_STTS_CD == "ES.WAIT"
    }
    result = []
    for row in rows:
        pay_code = payments.get(int(row.PAY_SN)) if row.PAY_SN is not None else None
        payment = PAYMENT.get(pay_code) if pay_code else None
        refund_code = refunds.get(int(row.PAY_SN)) if row.PAY_SN is not None else None
        refund = REFUND_STAGE.get(refund_code) if refund_code else None
        state = flags(row, payment, refund, now)
        result.append(
            ApplicationSummary(
                application_id=str(int(row.ATNLC_APLY_SN)),
                course=course_summaries[int(row.CORS_SN)],
                status=STATUS[str(row.APLY_STTS_CD)],
                display_state=state.display,
                waiting_rank=waiting_rank.get(int(row.ATNLC_APLY_SN)),
                payment_status=payment,
                payment_id=None if row.PAY_SN is None else str(int(row.PAY_SN)),
                refund_stage=refund,
                fee=int(row.TTCHG_AMT),
                reduction_amount=int(row.RDCT_AMT),
                payable_amount=int(row.STLM_PRNMNT_AMT),
                applied_at=utc(row.APLY_DT),
                seat_assigned_at=None if row.SEAT_ALTMNT_DT is None else utc(row.SEAT_ALTMNT_DT),
                payment_deadline=None if row.STLM_DDLN_DT is None else utc(row.STLM_DDLN_DT),
                can_cancel=state.can_cancel,
                can_pay=state.can_pay,
                can_request_refund=state.can_request_refund,
            )
        )
    return result


def rank_in_waitlist(db: Session, bundle_sn: int, row: Any) -> int:
    """대기 순번. 같은 강좌의 대기 신청 중 (대기순서, 신청번호)가 내 앞인 수 + 1이다."""
    ahead = db.execute(
        select(func.count()).where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.CORS_SN == row.CORS_SN,
            TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT",
            (TB_ATNLC_APLY.c.WTNG_SEQ < row.WTNG_SEQ)
            | and_(
                TB_ATNLC_APLY.c.WTNG_SEQ == row.WTNG_SEQ, TB_ATNLC_APLY.c.ATNLC_APLY_SN < row.ATNLC_APLY_SN
            ),
        )
    ).scalar_one()
    return int(ahead) + 1


def list_mine(
    db: Session, member_sn: int, bundle_sn: int, now: datetime, *, page: int, size: int
) -> ApplicationPage:
    base = _my_query(bundle_sn, member_sn)
    total = int(
        db.execute(
            select(func.count()).where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.MBR_SN == member_sn
            )
        ).scalar_one()
    )
    rows = db.execute(
        base.order_by(TB_ATNLC_APLY.c.APLY_DT.desc(), TB_ATNLC_APLY.c.ATNLC_APLY_SN.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return ApplicationPage(
        items=_summaries(db, bundle_sn, list(rows), now),
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get_mine(db: Session, member_sn: int, bundle_sn: int, application_id: str, now: datetime) -> Application:
    """내 신청이 아니면 없는 신청과 같이 404다(존재 여부 노출 방지, RQ-SER-NF-001)."""
    row = db.execute(
        _my_query(bundle_sn, member_sn).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == int(application_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    summary = _summaries(db, bundle_sn, [row], now)[0]
    return Application(**summary.model_dump(), server_now=utc(now))
