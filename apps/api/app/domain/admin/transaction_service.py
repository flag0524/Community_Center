# 관리자 결제·거래 대조: 목록·상세, PG 재조회, 수동 대사(AU.STLM_R·AU.STLM_W, TDD 5.4, FN-041·042, R12·R13)
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.adapters.pg.base import CURRENCY, ApproveOutcome, ApproveResult, PaymentGateway
from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit, permit_any, scope_for
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_MNGR,
    TB_RFND,
    TB_STLM,
    TB_STLM_EVENT,
)
from app.domain.admin.application_schemas import LinkedRefund
from app.domain.admin.application_types import ActionKind, NoticeHandling, ReconcileOutcome
from app.domain.admin.refund_service import kst_start, mask_name, scoped
from app.domain.admin.transaction_schemas import (
    PgNotice,
    ReconcileRequest,
    Transaction,
    TransactionAction,
    TransactionPage,
    TransactionSummary,
)
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.seats import lock_course
from app.domain.application.service import PAYMENT, REFUND_STAGE, flags
from app.domain.payment.service import (
    CODE_METHOD,
    METHOD_CODE,
    lock_application,
    lock_payment,
    record_event,
    settle_payment,
)
from app.domain.payment.types import PaymentMethod, PaymentStatus
from app.domain.refund.service import STATUS as REFUND_STATUS

PAYMENT_CODE = {value: code for code, value in PAYMENT.items()}
RECHECK_MAX = 3  # 워커의 자동 재조회 한도(TDD 5.4). 관리자 재조회는 한도를 세지 않는다
RECHECK_PREFIX = "RECHECK:"
MANUAL_PREFIX = "MANUAL:"
VIEW = (AU.STLM_R, AU.STLM_W)


def _base(bundle_sn: int) -> Select[Any]:
    return (
        select(
            TB_STLM,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.CORS_STTS_CD,
            TB_CORS.c.DONG_SN,
            TB_CORS.c.EDU_BGNG_YMD,
            TB_MBR.c.MBR_NM,
            TB_ATNLC_APLY.c.APLY_STTS_CD,
            TB_ATNLC_APLY.c.STLM_DDLN_DT,
            TB_ATNLC_APLY.c.STLM_PRNMNT_AMT,
            TB_ATNLC_APLY.c.CORS_SN,
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
        .join(TB_MBR, TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN)
        .where(TB_STLM.c.OPER_BNDL_SN == bundle_sn)
    )


def _conflict_payments(db: Session, bundle_sn: int) -> set[int]:
    """충돌 통보로 격리된 결제 번호. 작업이력 키가 문자열이라 숫자로 바꿔 모은다."""
    keys = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_STLM",
            TB_JOB_HSTRY.c.JOB_CD == "PAY_WEBHOOK",
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.DENY",
        )
    ).scalars()
    return {int(k) for k in keys if k is not None}


def _recheck_stats(
    db: Session, bundle_sn: int, stlm_sns: list[int]
) -> dict[int, tuple[int, datetime | None]]:
    if not stlm_sns:
        return {}
    rows = db.execute(
        select(TB_STLM_EVENT.c.STLM_SN, func.count(), func.max(TB_STLM_EVENT.c.RCPTN_DT))
        .where(
            TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM_EVENT.c.EVENT_TYPE_CD == "ET.RECON",
            TB_STLM_EVENT.c.EVENT_ID.like(f"{RECHECK_PREFIX}%"),
            TB_STLM_EVENT.c.STLM_SN.in_(stlm_sns),
        )
        .group_by(TB_STLM_EVENT.c.STLM_SN)
    ).all()
    return {int(r[0]): (int(r[1]), r[2]) for r in rows}


def _summary(row: Any, recheck: tuple[int, datetime | None], conflicts: set[int]) -> dict[str, Any]:
    return {
        "transaction_id": str(int(row.STLM_SN)),
        "order_no": str(row.STLM_NO),
        "application_no": str(int(row.ATNLC_APLY_SN)),
        "amount": int(row.STLM_AMT),
        "method": CODE_METHOD[str(row.STLM_MNS_CD)],
        "status": PAYMENT[str(row.STLM_STTS_CD)],
        "requested_at": utc(row.STLM_DMND_DT),
        "approved_at": None if row.STLM_APRV_DT is None else utc(row.STLM_APRV_DT),
        "recheck_count": recheck[0],
        "has_conflict": int(row.STLM_SN) in conflicts,
    }


def list_transactions(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    q: str | None,
    status: PaymentStatus | None,
    method: PaymentMethod | None,
    from_date: date | None,
    to_date: date | None,
    conflict_only: bool,
    page: int,
    size: int,
) -> TransactionPage:
    scope = permit_any(db, admin, VIEW, now)
    conflicts = _conflict_payments(db, admin.bundle_sn)
    query = scoped(_base(admin.bundle_sn), scope)
    if q:
        needle = q.strip()
        by_order = TB_STLM.c.STLM_NO.contains(needle, autoescape=True)
        query = query.where(
            or_(by_order, TB_STLM.c.ATNLC_APLY_SN == int(needle)) if needle.isdigit() else by_order
        )
    if status is not None:
        query = query.where(TB_STLM.c.STLM_STTS_CD == PAYMENT_CODE[status])
    if method is not None:
        query = query.where(TB_STLM.c.STLM_MNS_CD == METHOD_CODE[method])
    if from_date is not None:
        query = query.where(TB_STLM.c.STLM_DMND_DT >= kst_start(from_date))
    if to_date is not None:
        query = query.where(TB_STLM.c.STLM_DMND_DT < kst_start(to_date + timedelta(days=1)))
    if conflict_only:
        query = query.where(TB_STLM.c.STLM_SN.in_(conflicts or {0}))
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(
        query.order_by(
            case((TB_STLM.c.STLM_STTS_CD == "PS.PENDING", 0), else_=1),  # 결과 확인 중인 거래를 먼저
            TB_STLM.c.STLM_DMND_DT.desc(),
            TB_STLM.c.STLM_SN.desc(),
        )
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    stats = _recheck_stats(db, admin.bundle_sn, [int(r.STLM_SN) for r in rows])
    return TransactionPage(
        items=[
            TransactionSummary(**_summary(r, stats.get(int(r.STLM_SN), (0, None)), conflicts)) for r in rows
        ],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _visible(db: Session, admin: Admin, scope: Scope, transaction_id: str) -> Any:
    """범위 밖이거나 없는 거래는 같은 404다. 범위는 거래가 걸린 신청의 강좌 동이다."""
    row = db.execute(_base(admin.bundle_sn).where(TB_STLM.c.STLM_SN == int(transaction_id))).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _notices(db: Session, bundle_sn: int, stlm_sn: int) -> list[PgNotice]:
    """저장된 통보와 충돌로 격리한 통보. 중복 통보는 저장하지 않고 충돌 통보의 해시는 남기지 않는다."""
    stored = db.execute(
        select(TB_STLM_EVENT.c.RCPTN_DT, TB_STLM_EVENT.c.EVENT_HASH_VL)
        .where(
            TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM_EVENT.c.STLM_SN == stlm_sn,
            TB_STLM_EVENT.c.EVENT_TYPE_CD == "ET.WEBHOOK",
        )
        .order_by(TB_STLM_EVENT.c.RCPTN_DT)
    ).all()
    denied = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_STLM",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(stlm_sn),
            TB_JOB_HSTRY.c.JOB_CD == "PAY_WEBHOOK",
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.DENY",
        )
    ).all()
    notices = [
        PgNotice(at=utc(r.RCPTN_DT), hash_prefix=str(r.EVENT_HASH_VL)[:8], handling=NoticeHandling.DONE)
        for r in stored
    ] + [PgNotice(at=utc(r.REG_DT), hash_prefix="", handling=NoticeHandling.CONFLICT) for r in denied]
    return sorted(notices, key=lambda n: n.at)


def _actions(db: Session, bundle_sn: int, stlm_sn: int) -> list[TransactionAction]:
    rows = db.execute(
        select(
            TB_JOB_HSTRY.c.REG_DT,
            TB_JOB_HSTRY.c.JOB_CD,
            TB_JOB_HSTRY.c.ACTR_TYPE_CD,
            TB_JOB_HSTRY.c.CHG_CN,
            TB_MNGR.c.MNGR_NM,
        )
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_STLM",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(stlm_sn),
            TB_JOB_HSTRY.c.JOB_CD.in_(("PAY_RECHECK", "PAY_RECONCILE")),
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.SUCCESS",
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.JOB_HSTRY_SN)
    ).all()
    return [
        TransactionAction(
            at=utc(r.REG_DT),
            kind=ActionKind.RECHECK if r.JOB_CD == "PAY_RECHECK" else ActionKind.MANUAL_RECONCILE,
            actor=str(r.MNGR_NM) if r.MNGR_NM is not None else "SYSTEM",
            result=str(r.CHG_CN or ""),
        )
        for r in rows
    ]


def _detail(db: Session, admin: Admin, now: datetime, stlm_sn: int) -> Transaction:
    row = db.execute(_base(admin.bundle_sn).where(TB_STLM.c.STLM_SN == stlm_sn)).one()
    stats = _recheck_stats(db, admin.bundle_sn, [stlm_sn]).get(stlm_sn, (0, None))
    refund = db.execute(
        select(TB_RFND)
        .where(TB_RFND.c.OPER_BNDL_SN == admin.bundle_sn, TB_RFND.c.STLM_SN == stlm_sn)
        .order_by(TB_RFND.c.RFND_SN.desc())
    ).first()
    pay_status = PAYMENT[str(row.STLM_STTS_CD)]
    stage = REFUND_STAGE.get(str(refund.RFND_STTS_CD)) if refund is not None else None
    writer = can_write(db, admin, now, row)
    pending = row.STLM_STTS_CD == "PS.PENDING"
    return Transaction(
        **_summary(row, stats, _conflict_payments(db, admin.bundle_sn)),
        application_id=str(int(row.ATNLC_APLY_SN)),
        course_name=str(row.CORS_NM),
        applicant_name=mask_name(str(row.MBR_NM)),
        application_state=flags(row, pay_status, stage, now).display,
        merchant_id=str(row.FRCS_ID),
        payment_deadline_at=None if row.STLM_DDLN_DT is None else utc(row.STLM_DDLN_DT),
        recheck_max=RECHECK_MAX,
        last_recheck_at=None if stats[1] is None else utc(stats[1]),
        notices=_notices(db, admin.bundle_sn, stlm_sn),
        actions=_actions(db, admin.bundle_sn, stlm_sn),
        refund=(
            None
            if refund is None
            else LinkedRefund(
                refund_no=str(int(refund.RFND_SN)),
                amount=int(refund.RFND_AMT),
                status=REFUND_STATUS[str(refund.RFND_STTS_CD)],
            )
        ),
        can_recheck=pending and writer,
        can_reconcile=pending and writer,
        version=int(row.RCRD_VER),
    )


def can_write(db: Session, admin: Admin, now: datetime, row: Any) -> bool:
    """이 거래를 재조회·대사할 권한(AU.STLM_W)과 범위가 있는가."""
    return scope_for(db, admin, AU.STLM_W, now).covers(None if row.DONG_SN is None else int(row.DONG_SN))


def get_transaction(db: Session, admin: Admin, *, now: datetime, transaction_id: str) -> Transaction:
    _visible(db, admin, permit_any(db, admin, VIEW, now), transaction_id)
    return _detail(db, admin, now, int(transaction_id))


# --- 재조회·수동 대사 ------------------------------------------------------------------------


def next_event_id(db: Session, bundle_sn: int, stlm_sn: int, prefix: str) -> str:
    number = db.execute(
        select(func.count()).where(
            TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM_EVENT.c.STLM_SN == stlm_sn,
            TB_STLM_EVENT.c.EVENT_ID.like(f"{prefix}%"),
        )
    ).scalar_one()
    return f"{prefix}{int(number) + 1}"


def _lock_chain(db: Session, admin: Admin, scope: Scope, transaction_id: str) -> tuple[Any, Any, Any]:
    """범위를 확인하고 강좌 → 신청 → 결제 순으로 잠근다(C07). (강좌, 신청, 결제)."""
    row = _visible(db, admin, scope, transaction_id)
    course = lock_course(db, admin.bundle_sn, int(row.CORS_SN))
    application = lock_application(db, admin.bundle_sn, int(row.ATNLC_APLY_SN))
    return course, application, lock_payment(db, int(row.STLM_SN))


def recheck(
    db: Session,
    settings: Settings,
    admin: Admin,
    gateway: PaymentGateway,
    *,
    clock: Any,
    request_id: str,
    transaction_id: str,
) -> Transaction:
    """결과 확인 중인 거래의 결과를 PG에 다시 묻는다. 결과가 불명이면 그대로 두고 재조회 사건만 남긴다."""
    now = clock()
    scope = permit(db, admin, AU.STLM_W, now)
    row = _visible(db, admin, scope, transaction_id)
    if row.STLM_STTS_CD != "PS.PENDING":
        raise ApiError(ErrorCode.CONFLICT_STATE)
    order_no, stlm_sn = str(row.STLM_NO), int(row.STLM_SN)
    db.commit()  # PG를 부르는 동안 잠금을 쥐지 않는다
    try:
        approval = gateway.lookup(order_no=order_no)
    except Exception:  # 조회 실패는 결과 불명이다
        approval = ApproveResult(ApproveOutcome.UNKNOWN, failure_code="GATEWAY_ERROR")
    now = clock()
    course, application, payment = _lock_chain(db, admin, permit(db, admin, AU.STLM_W, now), transaction_id)
    if payment.STLM_STTS_CD == "PS.PENDING":  # 그 사이 통보·워커가 먼저 끝냈으면 그 결과를 따른다
        settled = settle_payment(
            db,
            settings,
            merchant_id=gateway.merchant_id,
            course=course,
            application=application,
            payment=payment,
            approval=approval,
            now=now,
            request_id=request_id,
        )
        record_event(
            db,
            admin.bundle_sn,
            stlm_sn,
            kind="ET.RECON",
            event_id=next_event_id(db, admin.bundle_sn, stlm_sn, RECHECK_PREFIX),
            status=settled.event_status,
            content=settled.content,
            now=now,
            fail_reason=settled.fail_reason,
        )
        _audit(db, admin, "PAY_RECHECK", stlm_sn, request_id, now, settled.audit)
    return _detail(db, admin, now, stlm_sn)


def manual_reconcile(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    transaction_id: str,
    body: ReconcileRequest,
) -> Transaction:
    """PG 관리자 화면에서 확인한 결과를 입력한다. 확인 근거는 필수이고 성공이면 승인번호도 필수다(FN-042)."""
    scope = permit(db, admin, AU.STLM_W, now)
    if body.outcome is ReconcileOutcome.PAID and not (body.approval_no and body.approval_no.strip()):
        raise ApiError(ErrorCode.RULE_REJECTED)
    course, application, payment = _lock_chain(db, admin, scope, transaction_id)
    if payment.STLM_STTS_CD != "PS.PENDING":
        raise ApiError(ErrorCode.CONFLICT_STATE)
    if int(payment.RCRD_VER) != body.version:
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    stlm_sn = int(payment.STLM_SN)
    if body.outcome is ReconcileOutcome.PAID:
        # 담당자가 PG 화면에서 확인한 사실이므로 우리 값과 같은 승인으로 반영한다(반영 규칙은 승인 확인·통보와 같다)
        approval = ApproveResult(
            ApproveOutcome.APPROVED,
            approval_no=(body.approval_no or "").strip(),
            approved_at=now,
            order_no=str(payment.STLM_NO),
            amount=int(payment.STLM_AMT),
            merchant_id=str(payment.FRCS_ID),
            currency=CURRENCY,
        )
    else:
        approval = ApproveResult(ApproveOutcome.REJECTED, failure_code="MANUAL_RECONCILE")
    settled = settle_payment(
        db,
        settings,
        merchant_id=str(payment.FRCS_ID),
        course=course,
        application=application,
        payment=payment,
        approval=approval,
        now=now,
        request_id=request_id,
    )
    content = {**settled.content, "manual": True, "evidence": body.evidence.strip()}
    record_event(
        db,
        admin.bundle_sn,
        stlm_sn,
        kind="ET.RECON",
        event_id=next_event_id(db, admin.bundle_sn, stlm_sn, MANUAL_PREFIX),
        status=settled.event_status,
        content=content,
        now=now,
        fail_reason=settled.fail_reason,
    )
    _audit(
        db,
        admin,
        "PAY_RECONCILE",
        stlm_sn,
        request_id,
        now,
        f"수동 대사({body.outcome.value}): {settled.audit}",
    )
    return _detail(db, admin, now, stlm_sn)


def _audit(
    db: Session, admin: Admin, job: str, stlm_sn: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_STLM",
        key=stlm_sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )
