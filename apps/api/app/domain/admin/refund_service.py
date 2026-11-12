# 관리자 환불 검토·집행: 조회, 대리 접수, 보류·승인·반려, PG 취소 집행, 수동 이체 확인(TDD 5.6, FN-043~046, R14·R15)
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.pg.base import CancelOutcome, CancelResult, PaymentGateway
from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit, permit_any, scope_for
from app.auth.crypto import DecryptError, decrypt
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import KST, kst_today, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_FILE,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_MNGR,
    TB_RFND,
    TB_STLM,
    TB_STLM_EVENT,
)
from app.db.versioned import update_versioned
from app.domain.admin.application_types import ExecutionMethod, RefundRequester
from app.domain.admin.csv_export import audit_export, build_csv, fetch_all
from app.domain.admin.refund_schemas import (
    AdminRefund,
    AdminRefundCreate,
    AdminRefundPage,
    AdminRefundSummary,
    ManualAccount,
    RefundHistoryEntry,
)
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.seats import lock_course, promote_waiters
from app.domain.payment.service import CODE_METHOD, lock_application, lock_payment, record_event
from app.domain.refund.calc import reference_amount
from app.domain.refund.service import (
    DEFAULT_REASON,
    DUPLICATE_ENTRY,
    IDEM_UNIQUE,
    STATUS,
    close_application,
    in_progress,
    paid_payment,
    reserved_amount,
)
from app.domain.refund.types import RefundStatus

VIEW = (AU.RFND_A, AU.RFND_X)
STATUS_CODE = {value: code for code, value in STATUS.items()}
REVIEWABLE = ("RS.REQUEST", "RS.HOLD")  # 검토 중이라 심사 목표 기한을 센다
OVERDUE_AFTER_BUSINESS_DAYS = 3  # 심사 목표 3영업일(공휴일 자료 전이라 주말만 뺀다)
# 한도를 차지하는 다른 환불. 반려된 것과 아직 검토 중인 것은 뺀다(R14). 실패는 재처리될 수 있어 차지한다
HELD_BY_OTHERS = ("RS.APPROVE", "RS.PENDING", "RS.DONE", "RS.FAIL")
JOB_STATUS = {
    "RFND_REQUEST": RefundStatus.REQUESTED,
    "RFND_HOLD": RefundStatus.ON_HOLD,
    "RFND_RELEASE": RefundStatus.REQUESTED,
    "RFND_APPROVE": RefundStatus.APPROVED,
    "RFND_REJECT": RefundStatus.REJECTED,
    "RFND_EXECUTE": RefundStatus.PENDING,
    "RFND_DONE": RefundStatus.DONE,
    "RFND_FAIL": RefundStatus.FAILED,
}


def mask_name(name: str) -> str:
    if len(name) <= 1:
        return "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def business_days_between(received: date, today: date) -> int:
    """접수일 다음 날부터 오늘까지의 평일 수."""
    days, cursor = 0, received
    while cursor < today:
        cursor += timedelta(days=1)
        days += 1 if cursor.weekday() < 5 else 0
    return days


def kst_start(day: date) -> datetime:
    """한국 날짜의 시작을 DB의 UTC 시각으로."""
    return datetime.combine(day, time.min, tzinfo=KST).astimezone(UTC).replace(tzinfo=None)


def _base(bundle_sn: int) -> Select[Any]:
    requester = TB_MNGR.alias("requester")
    approver = TB_MNGR.alias("approver")
    implementer = TB_MNGR.alias("implementer")
    return (
        select(
            TB_RFND,
            TB_STLM.c.ATNLC_APLY_SN,
            TB_STLM.c.STLM_NO,
            TB_STLM.c.STLM_AMT,
            TB_STLM.c.STLM_MNS_CD,
            TB_STLM.c.STLM_APRV_DT,
            TB_CORS.c.CORS_SN,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.DONG_SN,
            TB_CORS.c.EDU_BGNG_YMD,
            TB_CORS.c.EDU_END_YMD,
            TB_MBR.c.MBR_NM.label("MEMBER_NM"),
            requester.c.MNGR_NM.label("REQUESTER_NM"),
            approver.c.MNGR_NM.label("APPROVER_NM"),
            implementer.c.MNGR_NM.label("IMPLEMENTER_NM"),
        )
        .join(
            TB_STLM,
            and_(TB_STLM.c.OPER_BNDL_SN == TB_RFND.c.OPER_BNDL_SN, TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN),
        )
        .join(
            TB_ATNLC_APLY,
            and_(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN,
                TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN,
            ),
        )
        .join(
            TB_CORS,
            and_(
                TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
                TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN,
            ),
        )
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_RFND.c.DMND_MBR_SN)
        .outerjoin(requester, requester.c.MNGR_SN == TB_RFND.c.DMND_MNGR_SN)
        .outerjoin(approver, approver.c.MNGR_SN == TB_RFND.c.APRV_MNGR_SN)
        .outerjoin(implementer, implementer.c.MNGR_SN == TB_RFND.c.IMPL_MNGR_SN)
        .where(TB_RFND.c.OPER_BNDL_SN == bundle_sn)
    )


def _requester(row: Any) -> RefundRequester:
    return RefundRequester.ADMIN if row.DMND_MNGR_SN is not None else RefundRequester.MEMBER


def _summary(row: Any, now: datetime) -> dict[str, Any]:
    received = kst_today(row.RFND_DMND_DT)
    elapsed = business_days_between(received, kst_today(now))
    return {
        "refund_id": str(int(row.RFND_SN)),
        "refund_no": str(int(row.RFND_SN)),
        "application_no": str(int(row.ATNLC_APLY_SN)),
        "course_name": str(row.CORS_NM),
        "requested_amount": int(row.RFND_AMT),
        "status": STATUS[str(row.RFND_STTS_CD)],
        "received_on": received,
        "elapsed_business_days": elapsed,
        "overdue": row.RFND_STTS_CD in REVIEWABLE and elapsed > OVERDUE_AFTER_BUSINESS_DAYS,
        "requester": _requester(row),
    }


def scoped(query: Select[Any], scope: Scope) -> Select[Any]:
    """범위는 요청 값이 아니라 환불이 걸린 강좌의 운영 동으로 판정한다(스키마 6.1)."""
    if scope.whole:
        return query
    return query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))


def _filters(
    query: Select[Any],
    status: RefundStatus | None,
    requester: RefundRequester | None,
    from_date: date | None,
    to_date: date | None,
) -> Select[Any]:
    if status is not None:
        query = query.where(TB_RFND.c.RFND_STTS_CD == STATUS_CODE[status])
    if requester is RefundRequester.MEMBER:
        query = query.where(TB_RFND.c.DMND_MBR_SN.is_not(None))
    if requester is RefundRequester.ADMIN:
        query = query.where(TB_RFND.c.DMND_MNGR_SN.is_not(None))
    if from_date is not None:
        query = query.where(TB_RFND.c.RFND_DMND_DT >= kst_start(from_date))
    if to_date is not None:
        query = query.where(TB_RFND.c.RFND_DMND_DT < kst_start(to_date + timedelta(days=1)))
    return query


def _filtered(
    db: Session,
    admin: Admin,
    now: datetime,
    *,
    status: RefundStatus | None,
    requester: RefundRequester | None,
    from_date: date | None,
    to_date: date | None,
) -> Any:
    """목록과 내보내기가 함께 쓰는 조회. 목록(ADM-PAY-004)은 승인 권한만, 상세는 승인·집행(화면설계서 5절)이다."""
    scope = permit(db, admin, AU.RFND_A, now)
    query = _filters(scoped(_base(admin.bundle_sn), scope), status, requester, from_date, to_date)
    urgent = case((TB_RFND.c.RFND_STTS_CD.in_(REVIEWABLE), 0), else_=1)
    return query.order_by(
        urgent,
        case((urgent == 0, TB_RFND.c.RFND_DMND_DT), else_=None).asc(),  # 검토 중은 오래된 순
        TB_RFND.c.RFND_DMND_DT.desc(),
        TB_RFND.c.RFND_SN.desc(),
    )


def export_csv(db: Session, admin: Admin, *, now: datetime, request_id: str, **filters: Any) -> bytes:
    """목록과 같은 조건·권한으로 만든다. 환불 계좌 같은 민감 값은 담지 않는다."""
    rows = fetch_all(db, _filtered(db, admin, now, **filters))
    items = [AdminRefundSummary(**_summary(r, now)) for r in rows]
    audit_export(db, admin, "TB_RFND", len(items), request_id, now, filters)
    return build_csv(
        ["환불번호", "신청번호", "강좌", "요청액", "상태", "접수일", "경과 영업일", "지연", "요청자"],
        [
            [
                i.refund_no,
                i.application_no,
                i.course_name,
                i.requested_amount,
                i.status.value,
                i.received_on,
                i.elapsed_business_days,
                i.overdue,
                i.requester.value,
            ]
            for i in items
        ],
    )


def list_refunds(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    page: int,
    size: int,
    **filters: Any,
) -> AdminRefundPage:
    query = _filtered(db, admin, now, **filters)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AdminRefundPage(
        items=[AdminRefundSummary(**_summary(r, now)) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _history(db: Session, bundle_sn: int, refund_sn: int) -> list[RefundHistoryEntry]:
    rows = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.JOB_CD, TB_JOB_HSTRY.c.ACTR_TYPE_CD, TB_MNGR.c.MNGR_NM)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_RFND",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(refund_sn),
            TB_JOB_HSTRY.c.JOB_CD.in_(tuple(JOB_STATUS)),
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.SUCCESS",
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.JOB_HSTRY_SN)
    ).all()
    actor = {"AK.MEMBER": "회원", "AK.SYSTEM": "SYSTEM"}
    return [
        RefundHistoryEntry(
            at=utc(r.REG_DT),
            status=JOB_STATUS[str(r.JOB_CD)],
            actor=str(r.MNGR_NM) if r.MNGR_NM is not None else actor.get(str(r.ACTR_TYPE_CD), "담당자"),
            note=None,
        )
        for r in rows
    ]


def _manual_account(settings: Settings, row: Any) -> ManualAccount | None:
    """은행·계좌·예금주가 함께 있을 때만 수동 계좌환불이다(R15). 화면에는 가려서만 준다."""
    if row.RFND_BANK_CD is None or row.RFND_ACTNO_ENCPT_VL is None or row.RFND_DPSTR_ENCPT_VL is None:
        return None
    try:
        account = decrypt(settings.secret_key, str(row.RFND_ACTNO_ENCPT_VL))
        holder = decrypt(settings.secret_key, str(row.RFND_DPSTR_ENCPT_VL))
    except DecryptError:
        return ManualAccount(bank_name=str(row.RFND_BANK_CD), holder_masked="*", account_masked="****")
    tail = account[-4:] if len(account) > 4 else ""
    return ManualAccount(
        bank_name=str(row.RFND_BANK_CD),
        holder_masked=mask_name(holder),
        account_masked="*" * max(len(account) - len(tail), 4) + tail,
    )


def _failure_reason(db: Session, refund_sn: int) -> str | None:
    return db.execute(
        select(TB_STLM_EVENT.c.FAIL_RSN)
        .where(TB_STLM_EVENT.c.RFND_SN == refund_sn, TB_STLM_EVENT.c.PRCS_STTS_CD == "EP.FAIL")
        .order_by(TB_STLM_EVENT.c.STLM_EVENT_SN.desc())
    ).scalar()


def _detail(db: Session, settings: Settings, admin: Admin, now: datetime, refund_sn: int) -> AdminRefund:
    row = db.execute(_base(admin.bundle_sn).where(TB_RFND.c.RFND_SN == refund_sn)).one()
    stlm_sn = int(row.STLM_SN)
    paid = int(row.STLM_AMT)
    held = _held_by_others(db, admin.bundle_sn, stlm_sn, refund_sn)
    ref = reference_amount(paid, str(row.EDU_BGNG_YMD), str(row.EDU_END_YMD), kst_today(now))
    review, execute = scope_for(db, admin, AU.RFND_A, now), scope_for(db, admin, AU.RFND_X, now)
    status = str(row.RFND_STTS_CD)
    method = (
        ExecutionMethod.MANUAL_TRANSFER if _manual_account(settings, row) else ExecutionMethod.CANCEL_PAYMENT
    )
    own_approval = row.APRV_MNGR_SN is not None and int(row.APRV_MNGR_SN) == admin.admin_sn
    executable = execute.covers(row.DONG_SN) and status in ("RS.APPROVE", "RS.FAIL")
    confirmable = (
        execute.covers(row.DONG_SN) and status == "RS.PENDING" and method is ExecutionMethod.MANUAL_TRANSFER
    )
    approved = status in ("RS.APPROVE", "RS.PENDING", "RS.DONE", "RS.FAIL")
    result = {
        "RS.DONE": "환불 완료",
        "RS.PENDING": "처리 중",
        "RS.FAIL": _failure_reason(db, refund_sn) or "집행 실패",
    }.get(status)
    evidence = db.execute(
        select(func.count()).select_from(TB_FILE).where(TB_FILE.c.RFND_SN == refund_sn)
    ).scalar_one()
    requested_by = (
        str(row.REQUESTER_NM) if row.DMND_MNGR_SN is not None else mask_name(str(row.MEMBER_NM or ""))
    )
    return AdminRefund(
        **_summary(row, now),
        payment_order_no=str(row.STLM_NO),
        paid_amount=paid,
        payment_method=CODE_METHOD[str(row.STLM_MNS_CD)],
        paid_at=utc(row.STLM_APRV_DT),
        reserved_amount=held,
        remaining_amount=max(0, paid - held),
        baseline_amount=ref.amount,
        baseline_rule=ref.rule,
        education_start=date(
            int(str(row.EDU_BGNG_YMD)[:4]), int(str(row.EDU_BGNG_YMD)[4:6]), int(str(row.EDU_BGNG_YMD)[6:8])
        ),
        reason=str(row.RFND_RSN),
        detail=None,
        evidence_count=int(evidence),
        requester_name=requested_by,
        approved_amount=int(row.RFND_AMT) if approved else None,
        decision_reason=(
            str(row.RJCT_RSN)
            if row.RJCT_RSN is not None
            else None
            if row.HLDOF_RSN is None
            else str(row.HLDOF_RSN)
        ),
        decided_by=None if row.APPROVER_NM is None else str(row.APPROVER_NM),
        execution_method=method,
        manual_account=_manual_account(settings, row),
        executed_by=None if row.IMPLEMENTER_NM is None else str(row.IMPLEMENTER_NM),
        execution_result=result,
        history=_history(db, admin.bundle_sn, refund_sn),
        version=int(row.RCRD_VER),
        can_review=review.covers(row.DONG_SN) and status in REVIEWABLE,
        can_execute=executable and not own_approval,
        can_confirm_transfer=confirmable and not own_approval,
        execute_note="승인한 담당자는 집행할 수 없습니다." if executable and own_approval else None,
    )


def get_refund(
    db: Session, settings: Settings, admin: Admin, *, now: datetime, refund_id: str
) -> AdminRefund:
    scope = permit_any(db, admin, VIEW, now)
    _visible(db, admin, scope, int(refund_id))
    return _detail(db, settings, admin, now, int(refund_id))


def _visible(db: Session, admin: Admin, scope: Scope, refund_sn: int) -> Any:
    """범위 밖이거나 없는 환불은 같은 404다. 범위는 요청이 아니라 환불이 걸린 강좌의 동으로 판정한다."""
    row = db.execute(_base(admin.bundle_sn).where(TB_RFND.c.RFND_SN == refund_sn)).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _held_by_others(db: Session, bundle_sn: int, stlm_sn: int, refund_sn: int) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(TB_RFND.c.RFND_AMT), 0)).where(
            TB_RFND.c.OPER_BNDL_SN == bundle_sn,
            TB_RFND.c.STLM_SN == stlm_sn,
            TB_RFND.c.RFND_SN != refund_sn,
            TB_RFND.c.RFND_STTS_CD.in_(HELD_BY_OTHERS),
        )
    ).scalar_one()
    return int(total)


def _lock_refund(db: Session, bundle_sn: int, refund_sn: int) -> Any:
    return db.execute(
        select(TB_RFND)
        .where(TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.RFND_SN == refund_sn)
        .with_for_update()
    ).one()


def _locked(db: Session, admin: Admin, scope: Scope, refund_sn: int) -> tuple[Any, Any]:
    """범위를 확인하고 결제 → 환불 순으로 잠근다(C07). 잠근 뒤의 행을 돌려준다."""
    target = _visible(db, admin, scope, refund_sn)
    payment = lock_payment(db, int(target.STLM_SN))
    return _lock_refund(db, admin.bundle_sn, refund_sn), payment


def _audit(
    db: Session, admin: Admin, job: str, refund_sn: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_RFND",
        key=refund_sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def _move(
    db: Session,
    admin: Admin,
    refund: Any,
    *,
    allowed: tuple[str, ...],
    to: str,
    version: int,
    values: dict[str, Any],
) -> None:
    if refund.RFND_STTS_CD not in allowed:
        raise ApiError(ErrorCode.CONFLICT_STATE)
    update_versioned(
        db,
        TB_RFND,
        {"OPER_BNDL_SN": admin.bundle_sn, "RFND_SN": int(refund.RFND_SN)},
        version,
        {"RFND_STTS_CD": to, **values},
    )


def hold(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    refund_id: str,
    reason: str,
    version: int,
) -> AdminRefund:
    sn = int(refund_id)
    refund, _ = _locked(db, admin, permit(db, admin, AU.RFND_A, now), sn)
    _move(
        db,
        admin,
        refund,
        allowed=("RS.REQUEST",),
        to="RS.HOLD",
        version=version,
        values={"HLDOF_RSN": reason},
    )
    _audit(db, admin, "RFND_HOLD", sn, request_id, now, "검토 보류")
    return _detail(db, settings, admin, now, sn)


def release_hold(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    refund_id: str,
    version: int,
) -> AdminRefund:
    sn = int(refund_id)
    refund, _ = _locked(db, admin, permit(db, admin, AU.RFND_A, now), sn)
    _move(
        db, admin, refund, allowed=("RS.HOLD",), to="RS.REQUEST", version=version, values={"HLDOF_RSN": None}
    )
    _audit(db, admin, "RFND_RELEASE", sn, request_id, now, "보류 해제")
    return _detail(db, settings, admin, now, sn)


def reject(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    refund_id: str,
    reason: str,
    version: int,
) -> AdminRefund:
    sn = int(refund_id)
    refund, _ = _locked(db, admin, permit(db, admin, AU.RFND_A, now), sn)
    _move(
        db,
        admin,
        refund,
        allowed=("RS.REQUEST",),
        to="RS.REJECT",
        version=version,
        values={"RJCT_RSN": reason, "APRV_MNGR_SN": admin.admin_sn, "APRV_DT": now},
    )
    _audit(db, admin, "RFND_REJECT", sn, request_id, now, "반려(신청은 되살리지 않음)")
    return _detail(db, settings, admin, now, sn)


def approve(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    refund_id: str,
    amount: int,
    version: int,
) -> AdminRefund:
    """승인액은 요청액 이하이고, 다른 환불이 차지한 금액과 합쳐 승인 시점의 반환 기준액을 넘지 못한다(사용자 확정)."""
    sn = int(refund_id)
    refund, payment = _locked(db, admin, permit(db, admin, AU.RFND_A, now), sn)
    if refund.RFND_STTS_CD != "RS.REQUEST":
        raise ApiError(ErrorCode.CONFLICT_STATE)
    if payment.STLM_STTS_CD != "PS.PAID" or amount > int(refund.RFND_AMT):
        raise ApiError(ErrorCode.RULE_REJECTED)
    target = db.execute(_base(admin.bundle_sn).where(TB_RFND.c.RFND_SN == sn)).one()
    ref = reference_amount(
        int(payment.STLM_AMT), str(target.EDU_BGNG_YMD), str(target.EDU_END_YMD), kst_today(now)
    )
    held = _held_by_others(db, admin.bundle_sn, int(payment.STLM_SN), sn)
    if held + amount > ref.amount:
        raise ApiError(ErrorCode.RFND_LIMIT_EXCEEDED)
    _move(
        db,
        admin,
        refund,
        allowed=("RS.REQUEST",),
        to="RS.APPROVE",
        version=version,
        values={"RFND_AMT": amount, "APRV_MNGR_SN": admin.admin_sn, "APRV_DT": now},
    )
    _audit(
        db,
        admin,
        "RFND_APPROVE",
        sn,
        request_id,
        now,
        f"승인 {amount}원(요청 {int(refund.RFND_AMT)}원, 기준액 {ref.amount}원 {ref.rule.value}, 기존 예약 {held}원)",
    )
    return _detail(db, settings, admin, now, sn)


def create_by_admin(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    body: AdminRefundCreate,
    idem_key: str,
) -> AdminRefund:
    """방문·유선 대리 접수. 회원 접수와 같이 신청을 취소하고 자리를 돌려준다(사용자 확정). 금액은 담당자가 정한다."""
    scope = permit(db, admin, AU.RFND_A, now)
    if not body.application_no.isdigit():
        raise ApiError(ErrorCode.NOT_FOUND)
    application_sn = int(body.application_no)
    found = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN, TB_CORS.c.DONG_SN)
        .join(
            TB_CORS,
            and_(
                TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
                TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN,
            ),
        )
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == admin.bundle_sn, TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn
        )
    ).first()
    if found is None or not scope.covers(None if found.DONG_SN is None else int(found.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    course = lock_course(db, admin.bundle_sn, int(found.CORS_SN))
    application = lock_application(db, admin.bundle_sn, application_sn)
    prior = db.execute(
        select(TB_RFND.c.RFND_SN, TB_STLM.c.ATNLC_APLY_SN)
        .join(TB_STLM, TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN)
        .where(TB_RFND.c.OPER_BNDL_SN == admin.bundle_sn, TB_RFND.c.IDEM_KEY == idem_key)
    ).first()
    if prior is not None:
        if int(prior.ATNLC_APLY_SN) != application_sn:
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _detail(db, settings, admin, now, int(prior.RFND_SN))
    payment = paid_payment(db, admin.bundle_sn, application_sn)
    if payment is None or application.APLY_STTS_CD != "ES.CONFIRM":
        raise ApiError(ErrorCode.RULE_REJECTED)
    stlm_sn = int(payment.STLM_SN)
    lock_payment(db, stlm_sn)
    if in_progress(db, admin.bundle_sn, stlm_sn):
        raise ApiError(ErrorCode.RULE_REJECTED)
    if reserved_amount(db, admin.bundle_sn, stlm_sn) + body.requested_amount > int(payment.STLM_AMT):
        raise ApiError(ErrorCode.RFND_LIMIT_EXCEEDED)  # 접수 때도 원결제액을 넘지 못한다(R14)
    try:
        refund_sn = int(
            db.execute(
                insert(TB_RFND)
                .values(
                    OPER_BNDL_SN=admin.bundle_sn,
                    STLM_SN=stlm_sn,
                    RFND_AMT=body.requested_amount,
                    RFND_STTS_CD="RS.REQUEST",
                    RFND_RSN=body.reason.strip() or DEFAULT_REASON,
                    RFND_DMND_DT=now,
                    DMND_MNGR_SN=admin.admin_sn,
                    IDEM_KEY=idem_key,
                    REG_DT=now,
                )
                .returning(TB_RFND.c.RFND_SN)
            ).scalar_one()
        )
    except IntegrityError as error:
        if (
            error.orig is not None
            and error.orig.args[0] == DUPLICATE_ENTRY
            and IDEM_UNIQUE in str(error.orig.args[1])
        ):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT) from None
        raise
    close_application(db, admin.bundle_sn, application_sn, now)
    _audit(db, admin, "RFND_REQUEST", refund_sn, request_id, now, "대리 접수, 신청 취소")
    promote_waiters(db, settings, course, now=now, request_id=request_id)
    return _detail(db, settings, admin, now, refund_sn)


# --- 집행 -------------------------------------------------------------------------------------


def pg_key(bundle_sn: int, refund_sn: int) -> str:
    """PG 취소의 멱등키. 재처리도 같은 키라 이중 취소가 되지 않는다(TDD 5.6, R14)."""
    return f"RFND-{bundle_sn}-{refund_sn}"


def _cancel_event(
    db: Session,
    bundle_sn: int,
    refund: Any,
    *,
    status: str,
    content: dict[str, Any],
    now: datetime,
    fail_reason: str | None = None,
) -> None:
    number = (
        db.execute(
            select(func.count()).select_from(TB_STLM_EVENT).where(TB_STLM_EVENT.c.RFND_SN == refund.RFND_SN)
        ).scalar_one()
        + 1
    )
    record_event(
        db,
        bundle_sn,
        int(refund.STLM_SN),
        kind="ET.RESPONSE",
        event_id=f"{pg_key(bundle_sn, int(refund.RFND_SN))}:{number}",
        status=status,
        content=content,
        now=now,
        fail_reason=fail_reason,
        refund_sn=int(refund.RFND_SN),
    )


def settle_cancel(
    db: Session,
    admin: Admin | None,
    refund: Any,
    result: CancelResult,
    *,
    amount: int,
    request_id: str,
    now: datetime,
) -> str:
    """잠근 RS.PENDING 환불에 PG 취소 결과를 반영한다(집행 직후와 이후 재조회가 함께 쓴다). 새 상태 코드를 돌려준다.

    결과를 모르면 그대로 두고, 취소 금액이 어긋나면 돈이 나갔을 수 있어 완료도 실패도 아닌 채로 확인 필요 사건만 남긴다.
    """
    bundle_sn, sn = int(refund.OPER_BNDL_SN), int(refund.RFND_SN)
    content = {"outcome": result.outcome.value, "amount": result.amount, "cancelId": result.cancel_id}
    if result.outcome is CancelOutcome.DONE and result.amount != amount:
        _cancel_event(
            db,
            bundle_sn,
            refund,
            status="EP.FAIL",
            content=content,
            now=now,
            fail_reason=f"취소 금액 불일치(요청 {amount}원) 확인 필요",
        )
        return "RS.PENDING"
    if result.outcome is CancelOutcome.DONE:
        values = {"RFND_STTS_CD": "RS.DONE", "RFND_DT": now, "PG_RFND_ID": result.cancel_id}
        job, new = "RFND_DONE", "RS.DONE"
        _cancel_event(db, bundle_sn, refund, status="EP.DONE", content=content, now=now)
    elif result.outcome is CancelOutcome.REJECTED:
        values = {"RFND_STTS_CD": "RS.FAIL"}
        job, new = "RFND_FAIL", "RS.FAIL"
        _cancel_event(
            db,
            bundle_sn,
            refund,
            status="EP.FAIL",
            content=content,
            now=now,
            fail_reason=result.failure_code or "PG 취소 거절",
        )
    else:
        return "RS.PENDING"
    update_versioned(db, TB_RFND, {"OPER_BNDL_SN": bundle_sn, "RFND_SN": sn}, int(refund.RCRD_VER), values)
    record_job(
        db,
        actor="AK.ADMIN" if admin else "AK.SYSTEM",
        job=job,
        table="TB_RFND",
        key=sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        admin_sn=admin.admin_sn if admin else None,
        change="PG 취소 완료" if new == "RS.DONE" else "PG 취소 실패",
    )
    return new


def _call_cancel(gateway: PaymentGateway, *, order_no: str, amount: int, key: str) -> CancelResult:
    """응답이 없거나 오류면 같은 멱등키로 조회해 실제 취소 여부를 확인한다. 그래도 모르면 UNKNOWN이다."""
    try:
        result = gateway.cancel(order_no=order_no, amount=amount, idempotency_key=key)
    except Exception:  # 외부 호출 실패는 모두 결과 불명으로 본다
        result = CancelResult(CancelOutcome.UNKNOWN, failure_code="CANCEL_CALL_ERROR")
    if result.outcome is CancelOutcome.UNKNOWN:
        try:
            result = gateway.lookup_cancel(idempotency_key=key)
        except Exception:
            result = CancelResult(CancelOutcome.UNKNOWN, failure_code="CANCEL_LOOKUP_ERROR")
    return result


def execute(
    db: Session,
    settings: Settings,
    admin: Admin,
    gateway: PaymentGateway,
    *,
    clock: Callable[[], datetime],
    request_id: str,
    refund_id: str,
    version: int,
) -> AdminRefund:
    """승인된 환불의 집행을 요청하거나 실패 건을 재처리한다. 승인한 담당자는 집행할 수 없다(PRD Q22 임시)."""
    sn, now = int(refund_id), clock()
    refund, payment = _locked(db, admin, permit(db, admin, AU.RFND_X, now), sn)
    if refund.RFND_STTS_CD not in ("RS.APPROVE", "RS.FAIL"):
        raise ApiError(ErrorCode.CONFLICT_STATE)
    if refund.APRV_MNGR_SN is not None and int(refund.APRV_MNGR_SN) == admin.admin_sn:
        raise ApiError(ErrorCode.RULE_REJECTED)
    amount = int(refund.RFND_AMT)
    # 재처리(RS.FAIL → RS.PENDING)도 한도를 다시 검사한다(TDD 5.6)
    if payment.STLM_STTS_CD != "PS.PAID" or _held_by_others(
        db, admin.bundle_sn, int(payment.STLM_SN), sn
    ) + amount > int(payment.STLM_AMT):
        raise ApiError(ErrorCode.RFND_LIMIT_EXCEEDED)
    manual = _manual_account(settings, refund) is not None
    _move(
        db,
        admin,
        refund,
        allowed=("RS.APPROVE", "RS.FAIL"),
        to="RS.PENDING",
        version=version,
        values={"IMPL_MNGR_SN": admin.admin_sn, "IMPL_DMND_DT": now},
    )
    _audit(
        db,
        admin,
        "RFND_EXECUTE",
        sn,
        request_id,
        now,
        "수동 이체 집행 요청" if manual else "PG 취소 집행 요청",
    )
    if manual:
        return _detail(db, settings, admin, now, sn)
    order_no, key = str(payment.STLM_NO), pg_key(admin.bundle_sn, sn)
    db.commit()  # PG를 부르기 전에 처리 중 상태를 남긴다. 호출 중 죽어도 같은 키로 이어서 확인한다(ADR-006)
    result = _call_cancel(gateway, order_no=order_no, amount=amount, key=key)  # 트랜잭션 밖
    now = clock()
    _locked(db, admin, permit(db, admin, AU.RFND_X, now), sn)
    current = _lock_refund(db, admin.bundle_sn, sn)
    if current.RFND_STTS_CD == "RS.PENDING":
        settle_cancel(db, admin, current, result, amount=amount, request_id=request_id, now=now)
    return _detail(db, settings, admin, now, sn)


def confirm_done(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    refund_id: str,
    version: int,
) -> AdminRefund:
    """수동 계좌환불은 담당자가 이체한 뒤 완료를 확인해야 환불완료가 된다."""
    sn = int(refund_id)
    refund, _ = _locked(db, admin, permit(db, admin, AU.RFND_X, now), sn)
    if refund.RFND_STTS_CD != "RS.PENDING" or _manual_account(settings, refund) is None:
        raise ApiError(ErrorCode.CONFLICT_STATE)
    if refund.APRV_MNGR_SN is not None and int(refund.APRV_MNGR_SN) == admin.admin_sn:
        raise ApiError(ErrorCode.RULE_REJECTED)
    _move(db, admin, refund, allowed=("RS.PENDING",), to="RS.DONE", version=version, values={"RFND_DT": now})
    _audit(db, admin, "RFND_DONE", sn, request_id, now, "수동 이체 완료 확인")
    return _detail(db, settings, admin, now, sn)
