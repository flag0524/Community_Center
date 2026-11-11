# 워커 작업: 결제기한 만료, 결제 결과 재조회, 환불 결과 조회. 대상을 DB 상태로 찾고 항목마다 커밋한다(TDD 7, ADR-048)
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.adapters.pg.base import ApproveOutcome, ApproveResult, CancelOutcome, CancelResult, PaymentGateway
from app.audit import record_job
from app.auth.tokens import new_token
from app.core.config import Settings
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_RFND, TB_STLM, TB_STLM_EVENT
from app.domain.admin.refund_service import pg_key, settle_cancel
from app.domain.admin.transaction_service import RECHECK_MAX, RECHECK_PREFIX, next_event_id
from app.domain.application.seats import expire_application, lock_course
from app.domain.payment.service import lock_application, lock_payment, record_event, settle_payment

log = logging.getLogger("app.worker")

BATCH = 50  # 한 번에 집는 대상 수. 남은 것은 다음 주기가 이어서 처리한다
RECHECK_INTERVAL = timedelta(seconds=60)  # 결제 재조회 간격(TDD 5.4: 1분 간격 최대 3회)
SETTLE_GRACE = timedelta(
    seconds=30
)  # 결제·환불 요청 직후에는 요청 처리가 아직 PG 응답을 기다리는 중일 수 있어 건드리지 않는다

Clock = Callable[[], datetime]


def _request_id() -> str:
    return f"worker-{new_token()[:16]}"


# --- 결제기한 만료 ------------------------------------------------------------------------------


def expire_payments(db: Session, settings: Settings, bundle_sn: int, clock: Clock, limit: int = BATCH) -> int:
    """기한이 지난 결제대기 신청을 만료시키고 자리를 돌려 대기자를 승격한다(TDD 7.1, FN-036).

    결제 결과를 확인 중인 신청은 자리를 지켜야 하므로 건너뛴다(ADR-006). 강좌 행이 다른 처리에 잠겨 있으면
    기다리지 않고 건너뛰어 다음 주기에 다시 본다(SKIP LOCKED). 만료한 신청 수를 돌려준다.
    """
    now = clock()
    pending_payment = exists().where(
        TB_STLM.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
        TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        TB_STLM.c.STLM_STTS_CD == "PS.PENDING",
    )
    due = db.execute(
        select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_ATNLC_APLY.c.CORS_SN)
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.HOLD",
            TB_ATNLC_APLY.c.STLM_DDLN_DT <= now,
            ~pending_payment,
        )
        .order_by(TB_ATNLC_APLY.c.STLM_DDLN_DT, TB_ATNLC_APLY.c.ATNLC_APLY_SN)
        .limit(limit)
    ).all()
    db.rollback()  # 후보를 읽은 트랜잭션을 닫는다. 이후 항목마다 새 트랜잭션에서 잠그고 다시 본다
    expired = 0
    for candidate in due:
        now = clock()
        course = db.execute(
            select(TB_CORS)
            .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn, TB_CORS.c.CORS_SN == candidate.CORS_SN)
            .with_for_update(skip_locked=True)
        ).first()
        if course is None:  # 다른 처리가 강좌를 잡고 있다
            db.rollback()
            continue
        application = lock_application(db, bundle_sn, int(candidate.ATNLC_APLY_SN))
        stlm_pending = db.execute(
            select(TB_STLM.c.STLM_SN).where(
                TB_STLM.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM.c.ATNLC_APLY_SN == application.ATNLC_APLY_SN,
                TB_STLM.c.STLM_STTS_CD == "PS.PENDING",
            )
        ).first()
        still_due = (
            application.APLY_STTS_CD == "ES.HOLD"
            and application.STLM_DDLN_DT is not None
            and application.STLM_DDLN_DT <= now
            and stlm_pending is None
        )
        if not still_due:  # 잠그는 사이 결제·취소가 먼저 끝났다
            db.rollback()
            continue
        expire_application(db, settings, course, application, now=now, request_id=_request_id())
        db.commit()
        expired += 1
    return expired


# --- 결제 결과 재조회 ---------------------------------------------------------------------------


def _due_payments(db: Session, bundle_sn: int, now: datetime) -> list[Any]:
    """재조회할 차례인 결과 확인 중 결제. 재조회 사건이 한도 미만이고 마지막 재조회가 1분 전인 것이다."""
    pending = db.execute(
        select(TB_STLM.c.STLM_SN, TB_STLM.c.STLM_DMND_DT, TB_STLM.c.MDFCN_DT, TB_STLM.c.ATNLC_APLY_SN)
        .where(TB_STLM.c.OPER_BNDL_SN == bundle_sn, TB_STLM.c.STLM_STTS_CD == "PS.PENDING")
        .order_by(TB_STLM.c.STLM_SN)
        .limit(BATCH * 4)
    ).all()
    due = []
    for payment in pending:
        since = payment.MDFCN_DT or payment.STLM_DMND_DT
        if now - since < SETTLE_GRACE:
            continue
        events = db.execute(
            select(TB_STLM_EVENT.c.RCPTN_DT).where(
                TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM_EVENT.c.STLM_SN == payment.STLM_SN,
                TB_STLM_EVENT.c.EVENT_TYPE_CD == "ET.RECON",
                TB_STLM_EVENT.c.EVENT_ID.like(f"{RECHECK_PREFIX}%"),
            )
        ).all()
        if len(events) >= RECHECK_MAX:  # 자동 재조회는 여기까지다. 이후는 담당자가 대사한다(TDD 5.4)
            continue
        if events and now - max(e.RCPTN_DT for e in events) < RECHECK_INTERVAL:
            continue
        due.append(payment)
        if len(due) >= BATCH:
            break
    return due


def recheck_payments(
    db: Session, settings: Settings, gateway: PaymentGateway, bundle_sn: int, clock: Clock
) -> int:
    """결과 확인 중인 결제를 PG에 다시 묻고 승인 확인과 같은 규칙으로 반영한다(TDD 7.2, FN-042). 재조회한 수를 돌려준다."""
    due = _due_payments(db, bundle_sn, clock())
    db.rollback()
    checked = 0
    for payment in due:
        stlm_sn = int(payment.STLM_SN)
        order_no = str(db.execute(select(TB_STLM.c.STLM_NO).where(TB_STLM.c.STLM_SN == stlm_sn)).scalar_one())
        db.rollback()  # PG를 부르는 동안 트랜잭션을 쥐지 않는다
        try:
            approval = gateway.lookup(order_no=order_no)
        except Exception:  # 조회 실패는 결과 불명이다
            approval = ApproveResult(ApproveOutcome.UNKNOWN, failure_code="GATEWAY_ERROR")
        now = clock()
        owned = db.execute(
            select(TB_ATNLC_APLY.c.CORS_SN).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == payment.ATNLC_APLY_SN)
        ).one()
        course = lock_course(db, bundle_sn, int(owned.CORS_SN))
        application = lock_application(db, bundle_sn, int(payment.ATNLC_APLY_SN))
        locked = lock_payment(db, stlm_sn)
        if locked.STLM_STTS_CD != "PS.PENDING":  # 그 사이 통보·담당자가 먼저 끝냈다
            db.rollback()
            continue
        request_id = _request_id()
        settled = settle_payment(
            db,
            settings,
            merchant_id=gateway.merchant_id,
            course=course,
            application=application,
            payment=locked,
            approval=approval,
            now=now,
            request_id=request_id,
        )
        record_event(
            db,
            bundle_sn,
            stlm_sn,
            kind="ET.RECON",
            event_id=next_event_id(db, bundle_sn, stlm_sn, RECHECK_PREFIX),
            status=settled.event_status,
            content=settled.content,
            now=now,
            fail_reason=settled.fail_reason,
        )
        record_job(
            db,
            actor="AK.SYSTEM",
            job="PAY_RECHECK",
            table="TB_STLM",
            key=stlm_sn,
            request_id=request_id,
            now=now,
            bundle_sn=bundle_sn,
            change=settled.audit,
        )
        db.commit()
        checked += 1
    return checked


# --- 환불 결과 조회 -----------------------------------------------------------------------------


def recheck_refunds(db: Session, gateway: PaymentGateway, bundle_sn: int, clock: Clock) -> int:
    """PG에 취소를 요청한 뒤 결과를 모르는 환불(RS.PENDING)을 같은 멱등키로 조회해 확정한다(TDD 7.2, FN-046).

    수동 계좌환불은 PG를 부르지 않으므로 대상이 아니다. 조회한 수를 돌려준다.
    """
    now = clock()
    due = db.execute(
        select(TB_RFND.c.RFND_SN)
        .where(
            TB_RFND.c.OPER_BNDL_SN == bundle_sn,
            TB_RFND.c.RFND_STTS_CD == "RS.PENDING",
            TB_RFND.c.RFND_ACTNO_ENCPT_VL.is_(None),
            TB_RFND.c.IMPL_DMND_DT <= now - SETTLE_GRACE,
        )
        .order_by(TB_RFND.c.RFND_SN)
        .limit(BATCH)
    ).all()
    db.rollback()
    checked = 0
    for item in due:
        refund_sn = int(item.RFND_SN)
        key = pg_key(bundle_sn, refund_sn)
        try:
            result = gateway.lookup_cancel(idempotency_key=key)
        except Exception:
            result = CancelResult(CancelOutcome.UNKNOWN, failure_code="CANCEL_LOOKUP_ERROR")
        now = clock()
        stlm = db.execute(select(TB_RFND.c.STLM_SN).where(TB_RFND.c.RFND_SN == refund_sn)).scalar_one()
        lock_payment(db, int(stlm))  # 결제 → 환불 순서(C07)
        refund = db.execute(
            select(TB_RFND)
            .where(TB_RFND.c.OPER_BNDL_SN == bundle_sn, TB_RFND.c.RFND_SN == refund_sn)
            .with_for_update()
        ).one()
        if refund.RFND_STTS_CD != "RS.PENDING":  # 그 사이 다른 경로가 끝냈다
            db.rollback()
            continue
        settle_cancel(
            db, None, refund, result, amount=int(refund.RFND_AMT), request_id=_request_id(), now=now
        )
        db.commit()
        checked += 1
    return checked
