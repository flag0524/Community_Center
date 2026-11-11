# 회원 환불: 반환 기준액 미리보기, 접수, 내역. 접수하면 신청을 취소하고 자리를 돌려준다(TDD 5.6·5.7, FN-043·045, R14·R15)
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.crypto import encrypt
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_RFND, TB_STLM
from app.domain.application.seats import cancel_ready_payments, lock_course, promote_waiters, set_status
from app.domain.application.service import REFUND_STAGE
from app.domain.payment.service import lock_application, lock_payment
from app.domain.refund.calc import Reference, reference_amount
from app.domain.refund.schemas import Refund, RefundBasis, RefundPage, RefundPreview
from app.domain.refund.types import RefundStatus

DUPLICATE_ENTRY = 1062
IDEM_UNIQUE = "UQ_RFND_02"  # (운영묶음, 멱등키) 유일키 이름
DEFAULT_REASON = "본인 환불 요청"
REFUND_CANCEL_REASON = "환불 접수"
STATUS = {
    "RS.REQUEST": RefundStatus.REQUESTED,
    "RS.HOLD": RefundStatus.ON_HOLD,
    "RS.REJECT": RefundStatus.REJECTED,
    "RS.APPROVE": RefundStatus.APPROVED,
    "RS.PENDING": RefundStatus.PENDING,
    "RS.DONE": RefundStatus.DONE,
    "RS.FAIL": RefundStatus.FAILED,
}
# 아직 끝나지 않은 환불. 이 중 하나가 있으면 같은 결제에 새로 접수할 수 없다
IN_PROGRESS = ("RS.REQUEST", "RS.HOLD", "RS.APPROVE", "RS.PENDING", "RS.FAIL")
# 환불로 잡혀 있는(또는 이미 돌려준) 금액. 반려된 것만 뺀다
RESERVED = ("RS.REQUEST", "RS.HOLD", "RS.APPROVE", "RS.PENDING", "RS.FAIL", "RS.DONE")


def paid_payment(db: Session, bundle_sn: int, application_sn: int) -> Any:
    return db.execute(
        select(TB_STLM.c.STLM_SN, TB_STLM.c.STLM_AMT).where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM.c.ATNLC_APLY_SN == application_sn,
            TB_STLM.c.STLM_STTS_CD == "PS.PAID",
        )
    ).first()


def reserved_amount(db: Session, bundle_sn: int, stlm_sn: int) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(TB_RFND.c.RFND_AMT), 0)).where(
            TB_RFND.c.OPER_BNDL_SN == bundle_sn,
            TB_RFND.c.STLM_SN == stlm_sn,
            TB_RFND.c.RFND_STTS_CD.in_(RESERVED),
        )
    ).scalar_one()
    return int(total)


def in_progress(db: Session, bundle_sn: int, stlm_sn: int) -> bool:
    return (
        db.execute(
            select(TB_RFND.c.RFND_SN).where(
                TB_RFND.c.OPER_BNDL_SN == bundle_sn,
                TB_RFND.c.STLM_SN == stlm_sn,
                TB_RFND.c.RFND_STTS_CD.in_(IN_PROGRESS),
            )
        ).first()
        is not None
    )


def _application(db: Session, bundle_sn: int, member_sn: int, application_sn: int) -> Any:
    row = db.execute(
        select(
            TB_ATNLC_APLY.c.ATNLC_APLY_SN,
            TB_ATNLC_APLY.c.CORS_SN,
            TB_ATNLC_APLY.c.APLY_STTS_CD,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.EDU_BGNG_YMD,
            TB_CORS.c.EDU_END_YMD,
        )
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn,
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
        )
    ).first()
    if row is None:  # 남의 신청은 없는 신청과 같다(R15, RQ-SER-NF-001)
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _basis(ref: Reference) -> RefundBasis:
    return RefundBasis(
        rule=ref.rule,
        reference_date=ref.reference_date,
        education_months=ref.education_months,
        elapsed_months=ref.elapsed_months,
        monthly_fee=ref.monthly_fee,
    )


def preview(
    db: Session, *, member_sn: int, bundle_sn: int, application_id: str, now: datetime
) -> RefundPreview:
    application_sn = int(application_id)
    application = _application(db, bundle_sn, member_sn, application_sn)
    payment = paid_payment(db, bundle_sn, application_sn)
    if payment is None:  # 결제가 끝나지 않았거나 결제가 없는(0원) 신청은 환불이 없다
        raise ApiError(ErrorCode.RFND_NOT_ALLOWED)
    paid = int(payment.STLM_AMT)
    reserved = reserved_amount(db, bundle_sn, int(payment.STLM_SN))
    # 수강확정이거나, 이미 환불을 접수해 진행 상태를 보려는 신청만 볼 수 있다
    if application.APLY_STTS_CD != "ES.CONFIRM" and reserved == 0:
        raise ApiError(ErrorCode.RFND_NOT_ALLOWED)
    ref = reference_amount(paid, str(application.EDU_BGNG_YMD), str(application.EDU_END_YMD), kst_today(now))
    return RefundPreview(
        server_now=utc(now),
        application_id=str(application_sn),
        paid_amount=paid,
        refundable_amount=ref.amount,
        reserved_amount=reserved,
        basis=_basis(ref),
    )


def _to_refund(row: Any) -> Refund:
    status = STATUS[str(row.RFND_STTS_CD)]
    reason = (
        row.HLDOF_RSN
        if row.RFND_STTS_CD == "RS.HOLD"
        else row.RJCT_RSN
        if row.RFND_STTS_CD == "RS.REJECT"
        else None
    )
    return Refund(
        refund_id=str(int(row.RFND_SN)),
        application_id=str(int(row.ATNLC_APLY_SN)),
        course_name=str(row.CORS_NM),
        amount=int(row.RFND_AMT),
        status=status,
        stage=REFUND_STAGE[str(row.RFND_STTS_CD)],
        reason=None if reason is None else str(reason),
        requested_at=utc(row.RFND_DMND_DT),
        completed_at=utc(row.RFND_DT) if row.RFND_STTS_CD == "RS.DONE" and row.RFND_DT is not None else None,
    )


def _refund_query() -> Any:
    return (
        select(
            TB_RFND.c.RFND_SN,
            TB_RFND.c.RFND_AMT,
            TB_RFND.c.RFND_STTS_CD,
            TB_RFND.c.RFND_DMND_DT,
            TB_RFND.c.RFND_DT,
            TB_RFND.c.HLDOF_RSN,
            TB_RFND.c.RJCT_RSN,
            TB_RFND.c.IDEM_KEY,
            TB_STLM.c.ATNLC_APLY_SN,
            TB_CORS.c.CORS_NM,
        )
        .join(
            TB_STLM,
            (TB_STLM.c.OPER_BNDL_SN == TB_RFND.c.OPER_BNDL_SN) & (TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN),
        )
        .join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN),
        )
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
    )


def close_application(db: Session, bundle_sn: int, application_sn: int, now: datetime) -> None:
    """환불을 접수한 신청을 취소한다. 회원·담당자 접수가 같이 쓴다. 자리 반환과 승격은 호출한 쪽이 이어서 한다."""
    cancel_ready_payments(db, bundle_sn, application_sn, now)
    set_status(db, application_sn, status="ES.CANCEL", now=now, reason=REFUND_CANCEL_REASON)


def create_refund(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    application_id: str,
    reason: str | None,
    account: tuple[str, str, str] | None = None,
    idem_key: str,
    request_id: str,
    now: datetime,
) -> Refund:
    """account는 (은행코드, 예금주, 계좌번호)다. 있으면 수동 계좌환불이고 암호화해 저장하며 로그에는 남기지 않는다."""
    application_sn = int(application_id)
    owned = _application(db, bundle_sn, member_sn, application_sn)
    # 잠금 순서는 강좌 → 신청 → 결제 → 환불이다(C07). 한도 판정은 결제 행을 잠근 뒤에 한다(R14).
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))
    application = lock_application(db, bundle_sn, application_sn)
    payment = paid_payment(db, bundle_sn, application_sn)

    # 같은 멱등키: 같은 신청이면 이전 결과, 다르면 충돌(FN-033). 잠금을 얻은 뒤 보므로 동시 재전송도 걸린다.
    prior = db.execute(
        _refund_query().where(TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.IDEM_KEY == idem_key)
    ).first()
    if prior is not None:
        if int(prior.ATNLC_APLY_SN) != application_sn:
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _to_refund(prior)

    if payment is None or application.APLY_STTS_CD != "ES.CONFIRM":
        raise ApiError(ErrorCode.RFND_NOT_ALLOWED)
    stlm_sn = int(payment.STLM_SN)
    lock_payment(db, stlm_sn)
    if in_progress(db, bundle_sn, stlm_sn):  # 진행 중인 환불이 있으면 새로 접수하지 않는다
        raise ApiError(ErrorCode.RFND_NOT_ALLOWED)
    ref = reference_amount(
        int(payment.STLM_AMT), str(owned.EDU_BGNG_YMD), str(owned.EDU_END_YMD), kst_today(now)
    )
    if ref.amount <= 0:
        raise ApiError(ErrorCode.RFND_NOT_ALLOWED)
    amount = ref.amount - reserved_amount(db, bundle_sn, stlm_sn)  # 금액은 서버가 정한다. 요청에는 없다(DV25)
    if amount <= 0:
        raise ApiError(ErrorCode.RFND_LIMIT_EXCEEDED)

    try:
        refund_sn = int(
            db.execute(
                insert(TB_RFND)
                .values(
                    OPER_BNDL_SN=bundle_sn,
                    STLM_SN=stlm_sn,
                    RFND_AMT=amount,
                    RFND_STTS_CD="RS.REQUEST",
                    RFND_RSN=(reason or "").strip() or DEFAULT_REASON,
                    RFND_DMND_DT=now,
                    DMND_MBR_SN=member_sn,
                    RFND_BANK_CD=None if account is None else account[0],
                    RFND_DPSTR_ENCPT_VL=None if account is None else encrypt(settings.secret_key, account[1]),
                    RFND_ACTNO_ENCPT_VL=None if account is None else encrypt(settings.secret_key, account[2]),
                    IDEM_KEY=idem_key,
                    REG_DT=now,
                )
                .returning(TB_RFND.c.RFND_SN)
            ).scalar_one()
        )
    except IntegrityError as error:
        # 같은 키를 다른 신청이 동시에 쓰면 잠금이 겹치지 않아 유일키가 마지막으로 막는다
        if (
            error.orig is not None
            and error.orig.args[0] == DUPLICATE_ENTRY
            and IDEM_UNIQUE in str(error.orig.args[1])
        ):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT) from None
        raise

    # 환불을 접수하면 신청을 취소하고 자리를 돌려준다(TDD 5.7). 반려돼도 신청은 되살리지 않는다.
    close_application(db, bundle_sn, application_sn, now)
    record_job(
        db,
        actor="AK.MEMBER",
        job="RFND_REQUEST",
        table="TB_RFND",
        key=refund_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"환불 접수(기준액 {ref.amount}원, {ref.rule.value}), 신청 취소",
    )
    promote_waiters(db, settings, course, now=now, request_id=request_id)
    created = db.execute(_refund_query().where(TB_RFND.c.RFND_SN == refund_sn)).one()
    return _to_refund(created)


def list_mine(
    db: Session, *, member_sn: int, bundle_sn: int, now: datetime, page: int, size: int
) -> RefundPage:
    where = (TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.DMND_MBR_SN == member_sn)
    total = int(db.execute(select(func.count()).select_from(TB_RFND).where(*where)).scalar_one())
    rows = db.execute(
        _refund_query()
        .where(*where)
        .order_by(TB_RFND.c.RFND_DMND_DT.desc(), TB_RFND.c.RFND_SN.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return RefundPage(
        items=[_to_refund(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )
