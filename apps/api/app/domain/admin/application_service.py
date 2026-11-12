# 관리자 수강신청·대기 조회(AU.APLY_R). 범위는 신청자 거주지가 아니라 강좌의 운영 동이다(스키마 6.1, ADR-043)
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_EDU_CYCL,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_RFND,
    TB_SMS_DMND,
    TB_SMS_TRGT,
    TB_STLM,
)
from app.domain.admin.application_schemas import (
    AdminApplication,
    AdminApplicationPage,
    AdminApplicationSummary,
    HistoryEntry,
    LinkedPayment,
    LinkedRefund,
    Promotion,
    Waiter,
    WaitlistCourse,
    WaitlistDetail,
    WaitlistPage,
)
from app.domain.admin.application_types import SmsResult
from app.domain.admin.csv_export import audit_export, build_csv, chunks, fetch_all
from app.domain.admin.refund_service import kst_start, mask_name, scoped
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.service import PAYMENT, REFUND_STAGE, STATUS, flags, rank_in_waitlist
from app.domain.application.types import ApplicationStatus
from app.domain.payment.service import CODE_METHOD
from app.domain.payment.types import PaymentStatus
from app.domain.refund.service import STATUS as REFUND_STATUS

PAYMENT_CODE = {value: code for code, value in PAYMENT.items()}
STATUS_CODE = {value: code for code, value in STATUS.items()}
SMS_RESULT = {
    "SS.WAIT": SmsResult.PENDING,
    "SS.SENDING": SmsResult.PENDING,
    "SS.UNKNOWN": SmsResult.PENDING,
    "SS.SENT": SmsResult.SENT,
    "SS.FAIL": SmsResult.FAILED,
    "SS.SKIP": SmsResult.FAILED,
}
APPLICATION_JOBS = ("APLY_CREATE", "APLY_PROMOTE", "APLY_EXPIRE", "APLY_CANCEL")
STATUS_IN_NOTE = re.compile(r"(ES\.[A-Z]+)")


def _latest_payment() -> Any:
    """신청의 가장 최근 결제 번호(상관 서브쿼리)."""
    return (
        select(func.max(TB_STLM.c.STLM_SN))
        .where(
            TB_STLM.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
            TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        )
        .correlate(TB_ATNLC_APLY)  # JOIN의 ON 안에서는 자동 상관이 되지 않아 명시한다
        .scalar_subquery()
    )


PAY = TB_STLM.alias("pay")  # 신청의 가장 최근 결제. 결제 상태로 거를 때도 쓴다


def _base(bundle_sn: int) -> Select[Any]:
    source = (
        TB_ATNLC_APLY.join(
            TB_CORS,
            and_(
                TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
                TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN,
            ),
        )
        .join(TB_MBR, TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN)
        .outerjoin(
            PAY,
            and_(PAY.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN, PAY.c.STLM_SN == _latest_payment()),
        )
    )
    return (
        select(
            TB_ATNLC_APLY,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.CORS_STTS_CD,
            TB_CORS.c.DONG_SN,
            TB_CORS.c.EDU_BGNG_YMD,
            TB_CORS.c.EDU_CYCL_SN,
            TB_MBR.c.MBR_NM,
            PAY.c.STLM_SN.label("PAY_SN"),
        )
        .select_from(source)
        .where(TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn)
    )


def _payments_and_refunds(
    db: Session, bundle_sn: int, rows: list[Any]
) -> tuple[dict[int, Any], dict[int, Any]]:
    pay_sns = [int(r.PAY_SN) for r in rows if r.PAY_SN is not None]
    if not pay_sns:
        return {}, {}
    payments: dict[int, Any] = {}
    refunds: dict[int, Any] = {}
    for part in chunks(pay_sns):  # 내보내기는 수만 건이라 IN 목록을 나눠 읽는다
        for p in db.execute(
            select(TB_STLM).where(TB_STLM.c.OPER_BNDL_SN == bundle_sn, TB_STLM.c.STLM_SN.in_(part))
        ).all():
            payments[int(p.STLM_SN)] = p
        for r in db.execute(
            select(TB_RFND)
            .where(TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.STLM_SN.in_(part))
            .order_by(TB_RFND.c.RFND_SN)
        ).all():
            refunds[int(r.STLM_SN)] = r  # 같은 결제의 환불이 여럿이면 마지막이 남는다
    return payments, refunds


def _summary(row: Any, payment: Any, refund: Any, now: datetime) -> dict[str, Any]:
    pay_status = PAYMENT.get(str(payment.STLM_STTS_CD)) if payment is not None else None
    stage = REFUND_STAGE.get(str(refund.RFND_STTS_CD)) if refund is not None else None
    return {
        "application_id": str(int(row.ATNLC_APLY_SN)),
        "application_no": str(int(row.ATNLC_APLY_SN)),
        "course_name": str(row.CORS_NM),
        "applicant_name": mask_name(str(row.MBR_NM)),
        "status": STATUS[str(row.APLY_STTS_CD)],
        "display_state": flags(row, pay_status, stage, now).display,
        "payment_status": pay_status,
        "refund_status": None if refund is None else REFUND_STATUS[str(refund.RFND_STTS_CD)],
        "applied_at": utc(row.APLY_DT),
    }


def _filtered(
    db: Session,
    admin: Admin,
    now: datetime,
    *,
    q: str | None,
    cycle_id: str | None,
    course_id: str | None,
    status: ApplicationStatus | None,
    payment_status: PaymentStatus | None,
    from_date: date | None,
    to_date: date | None,
) -> Any:
    """목록과 내보내기가 함께 쓰는 조회. 권한·범위·조건이 한 곳에서 정해진다."""
    scope = permit(db, admin, AU.APLY_R, now)
    query = scoped(_base(admin.bundle_sn), scope)
    if q:
        needle = q.strip()
        match = TB_MBR.c.MBR_NM.contains(needle, autoescape=True)
        query = query.where(
            or_(TB_ATNLC_APLY.c.ATNLC_APLY_SN == int(needle), match) if needle.isdigit() else match
        )
    if cycle_id:
        query = query.where(TB_CORS.c.EDU_CYCL_SN == int(cycle_id))
    if course_id:
        query = query.where(TB_CORS.c.CORS_SN == int(course_id))
    if status is not None:
        query = query.where(TB_ATNLC_APLY.c.APLY_STTS_CD == STATUS_CODE[status])
    if payment_status is not None:
        query = query.where(PAY.c.STLM_STTS_CD == PAYMENT_CODE[payment_status])
    if from_date is not None:
        query = query.where(TB_ATNLC_APLY.c.APLY_DT >= kst_start(from_date))
    if to_date is not None:
        query = query.where(TB_ATNLC_APLY.c.APLY_DT < kst_start(to_date + timedelta(days=1)))
    return query.order_by(TB_ATNLC_APLY.c.APLY_DT.desc(), TB_ATNLC_APLY.c.ATNLC_APLY_SN.desc())


def _summaries(db: Session, admin: Admin, rows: list[Any], now: datetime) -> list[AdminApplicationSummary]:
    payments, refunds = _payments_and_refunds(db, admin.bundle_sn, rows)
    return [
        AdminApplicationSummary(
            **_summary(
                r,
                payments.get(int(r.PAY_SN)) if r.PAY_SN is not None else None,
                refunds.get(int(r.PAY_SN)) if r.PAY_SN is not None else None,
                now,
            )
        )
        for r in rows
    ]


def list_applications(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    page: int,
    size: int,
    **filters: Any,
) -> AdminApplicationPage:
    query = _filtered(db, admin, now, **filters)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = list(db.execute(query.limit(size).offset((page - 1) * size)).all())
    items = _summaries(db, admin, rows, now)
    return AdminApplicationPage(
        items=items, page=page, size=size, total=total, criteria=PageCriteria(basis_at=utc(now))
    )


def export_csv(db: Session, admin: Admin, *, now: datetime, request_id: str, **filters: Any) -> bytes:
    """목록과 같은 조건·권한·가려진 값으로 만든다. 페이지 제한만 없고 5만 행을 넘으면 거절한다."""
    rows = fetch_all(db, _filtered(db, admin, now, **filters))
    items = _summaries(db, admin, rows, now)
    audit_export(db, admin, "TB_ATNLC_APLY", len(items), request_id, now, filters)
    return build_csv(
        ["신청번호", "강좌", "신청자", "신청 상태", "표시 상태", "결제 상태", "환불 상태", "신청일시"],
        [
            [
                i.application_no,
                i.course_name,
                i.applicant_name,
                i.status.value,
                i.display_state.value,
                None if i.payment_status is None else i.payment_status.value,
                None if i.refund_status is None else i.refund_status.value,
                i.applied_at,
            ]
            for i in items
        ],
    )


def _visible(db: Session, admin: Admin, scope: Scope, application_id: str) -> Any:
    """범위 밖이거나 없는 신청은 같은 404다."""
    row = db.execute(
        _base(admin.bundle_sn).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == int(application_id))
    ).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _history(db: Session, bundle_sn: int, application_sn: int) -> list[HistoryEntry]:
    """신청 원장의 상태 변화 이력. 작업이력에 남은 신청 관련 작업만 보이고 이전·이후 상태는 작업 메모에서 읽는다."""
    rows = db.execute(
        select(
            TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.JOB_CD, TB_JOB_HSTRY.c.ACTR_TYPE_CD, TB_JOB_HSTRY.c.CHG_CN
        )
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_ATNLC_APLY",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(application_sn),
            TB_JOB_HSTRY.c.JOB_CD.in_(APPLICATION_JOBS),
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.SUCCESS",
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.JOB_HSTRY_SN)
    ).all()
    entries = []
    for r in rows:
        note = str(r.CHG_CN or "")
        found = STATUS_IN_NOTE.search(note)
        job = str(r.JOB_CD)
        before: str | None
        if job == "APLY_EXPIRE":
            before, after = "ES.HOLD", "ES.EXPIRE"
        elif job == "APLY_CANCEL":
            before, after = (found.group(1) if found else None), "ES.CANCEL"
        elif job == "APLY_PROMOTE":
            before, after = "ES.WAIT", (found.group(1) if found else "ES.HOLD")
        else:  # APLY_CREATE
            before, after = None, (found.group(1) if found else "ES.WAIT")
        entries.append(
            HistoryEntry(
                at=utc(r.REG_DT),
                from_status=STATUS[before] if before else None,
                to_status=STATUS[after],
                actor="회원" if r.ACTR_TYPE_CD == "AK.MEMBER" else "SYSTEM",
                note=note or None,
            )
        )
    return entries


def get_application(db: Session, admin: Admin, *, now: datetime, application_id: str) -> AdminApplication:
    scope = permit(db, admin, AU.APLY_R, now)
    row = _visible(db, admin, scope, application_id)
    payments, refunds = _payments_and_refunds(db, admin.bundle_sn, [row])
    payment = payments.get(int(row.PAY_SN)) if row.PAY_SN is not None else None
    refund = refunds.get(int(row.PAY_SN)) if row.PAY_SN is not None else None
    cycle = db.execute(
        select(TB_EDU_CYCL.c.EDU_CYCL_NM).where(TB_EDU_CYCL.c.EDU_CYCL_SN == row.EDU_CYCL_SN)
    ).scalar_one()
    sn = int(row.ATNLC_APLY_SN)
    return AdminApplication(
        **_summary(row, payment, refund, now),
        course_id=str(int(row.CORS_SN)),
        cycle_name=str(cycle),
        waiting_order=rank_in_waitlist(db, admin.bundle_sn, row) if row.APLY_STTS_CD == "ES.WAIT" else None,
        seat_allotted_at=None if row.SEAT_ALTMNT_DT is None else utc(row.SEAT_ALTMNT_DT),
        payment_deadline_at=None if row.STLM_DDLN_DT is None else utc(row.STLM_DDLN_DT),
        history=_history(db, admin.bundle_sn, sn),
        payment=(
            None
            if payment is None
            else LinkedPayment(
                order_no=str(payment.STLM_NO),
                method=CODE_METHOD[str(payment.STLM_MNS_CD)],
                amount=int(payment.STLM_AMT),
                status=PAYMENT[str(payment.STLM_STTS_CD)],
                approved_at=None if payment.STLM_APRV_DT is None else utc(payment.STLM_APRV_DT),
            )
        ),
        refund=(
            None
            if refund is None
            else LinkedRefund(
                refund_no=str(int(refund.RFND_SN)),
                amount=int(refund.RFND_AMT),
                status=REFUND_STATUS[str(refund.RFND_STTS_CD)],
            )
        ),
        replays=[],  # 멱등 재요청은 응답만 되돌려 주고 따로 저장하지 않는다(새 테이블 없음)
    )


# --- 대기·자리 배정 -------------------------------------------------------------------------


def _course_stats(bundle_sn: int) -> Select[Any]:
    occupied = func.coalesce(
        func.sum(case((TB_ATNLC_APLY.c.APLY_STTS_CD.in_(("ES.HOLD", "ES.CONFIRM")), 1), else_=0)), 0
    )
    waiting = func.coalesce(func.sum(case((TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT", 1), else_=0)), 0)
    return (
        select(
            TB_CORS.c.CORS_SN,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.RCRT_NOPE,
            TB_CORS.c.DONG_SN,
            occupied.label("OCCUPIED"),
            waiting.label("WAITING"),
        )
        .select_from(TB_CORS)
        .outerjoin(
            TB_ATNLC_APLY,
            and_(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_ATNLC_APLY.c.CORS_SN == TB_CORS.c.CORS_SN,
            ),
        )
        .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn)
        .group_by(TB_CORS.c.CORS_SN, TB_CORS.c.CORS_NM, TB_CORS.c.RCRT_NOPE, TB_CORS.c.DONG_SN)
    )


def _promotions(db: Session, bundle_sn: int, course_sn: int) -> list[Any]:
    """강좌의 승격 작업(최신 순). 작업이력 키가 문자열이라 신청 번호를 먼저 구해 IN으로 찾는다(정렬 규칙 충돌 방지)."""
    applications = {
        str(int(a.ATNLC_APLY_SN)): a.STLM_DDLN_DT
        for a in db.execute(
            select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_ATNLC_APLY.c.STLM_DDLN_DT).where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.CORS_SN == course_sn
            )
        ).all()
    }
    if not applications:
        return []
    jobs = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.TRGT_KEY_VL)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_ATNLC_APLY",
            TB_JOB_HSTRY.c.JOB_CD == "APLY_PROMOTE",
            TB_JOB_HSTRY.c.TRGT_KEY_VL.in_(list(applications)),
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT.desc(), TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
    ).all()
    return [(j.REG_DT, int(j.TRGT_KEY_VL), applications[str(j.TRGT_KEY_VL)]) for j in jobs]


def _last_promoted(db: Session, bundle_sn: int, course_sn: int) -> datetime | None:
    promotions = _promotions(db, bundle_sn, course_sn)
    return utc(promotions[0][0]) if promotions else None


def _course(db: Session, bundle_sn: int, row: Any) -> dict[str, Any]:
    waiting = int(row.WAITING)
    return {
        "course_id": str(int(row.CORS_SN)),
        "course_name": str(row.CORS_NM),
        "capacity": int(row.RCRT_NOPE),
        "occupied": int(row.OCCUPIED),
        "wait_count": waiting,
        "next_wait_order": 1 if waiting else None,
        "last_promoted_at": _last_promoted(db, bundle_sn, int(row.CORS_SN)),
    }


def list_waitlist(
    db: Session, admin: Admin, *, now: datetime, cycle_id: str | None, page: int, size: int
) -> WaitlistPage:
    """대기 신청이 있는 강좌만 보인다."""
    scope = permit(db, admin, AU.APLY_R, now)
    stats = _course_stats(admin.bundle_sn)
    if cycle_id:
        stats = stats.where(TB_CORS.c.EDU_CYCL_SN == int(cycle_id))
    if not scope.whole:
        stats = stats.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    stats = stats.having(func.sum(case((TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT", 1), else_=0)) > 0)
    total = int(db.execute(select(func.count()).select_from(stats.subquery())).scalar_one())
    rows = db.execute(stats.order_by(TB_CORS.c.CORS_SN).limit(size).offset((page - 1) * size)).all()
    return WaitlistPage(
        items=[WaitlistCourse(**_course(db, admin.bundle_sn, r)) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get_waitlist(db: Session, admin: Admin, *, now: datetime, course_id: str) -> WaitlistDetail:
    scope = permit(db, admin, AU.APLY_R, now)
    row = db.execute(_course_stats(admin.bundle_sn).where(TB_CORS.c.CORS_SN == int(course_id))).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    bundle_sn, course_sn = admin.bundle_sn, int(row.CORS_SN)
    waiters = db.execute(
        select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_ATNLC_APLY.c.APLY_DT, TB_MBR.c.MBR_NM)
        .join(TB_MBR, TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN)
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.CORS_SN == course_sn,
            TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT",
        )
        .order_by(TB_ATNLC_APLY.c.WTNG_SEQ, TB_ATNLC_APLY.c.ATNLC_APLY_SN)
    ).all()
    promoted = _promotions(db, bundle_sn, course_sn)
    return WaitlistDetail(
        **_course(db, bundle_sn, row),
        waiters=[
            Waiter(
                order=index,
                application_no=str(int(w.ATNLC_APLY_SN)),
                applicant_name=mask_name(str(w.MBR_NM)),
                applied_at=utc(w.APLY_DT),
            )
            for index, w in enumerate(waiters, start=1)
        ],
        promotions=[
            Promotion(
                promoted_at=utc(at),
                application_no=str(sn),
                deadline_at=utc(deadline if deadline is not None else at),
                sms_result=_sms_result(db, bundle_sn, sn),
            )
            for at, sn, deadline in promoted
        ],
    )


def _sms_result(db: Session, bundle_sn: int, application_sn: int) -> SmsResult:
    """승격 안내 문자의 발송 결과. 아웃박스에 쌓지 않았으면(수신번호 없음) 보내지 못한 것이다."""
    status = db.execute(
        select(TB_SMS_TRGT.c.TRGT_STTS_CD)
        .join(TB_SMS_DMND, TB_SMS_DMND.c.SMS_DMND_SN == TB_SMS_TRGT.c.SMS_DMND_SN)
        .where(
            TB_SMS_DMND.c.OPER_BNDL_SN == bundle_sn,
            TB_SMS_DMND.c.SRC_EVENT_ID.like(f"PROMO:{application_sn}:%"),
        )
        .order_by(TB_SMS_DMND.c.SMS_DMND_SN.desc())
    ).scalar()
    return SMS_RESULT.get(str(status), SmsResult.FAILED) if status is not None else SmsResult.FAILED
