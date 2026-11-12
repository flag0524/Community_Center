# 워커 작업: 결제기한 만료, 결제 결과 재조회, 환불 결과 조회. 대상을 DB 상태로 찾고 항목마다 커밋한다(TDD 7, ADR-048)
import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, insert, or_, select, update
from sqlalchemy.orm import Session

from app.adapters.pg.base import ApproveOutcome, ApproveResult, CancelOutcome, CancelResult, PaymentGateway
from app.adapters.scan.base import FileScanner, ScanUnavailable
from app.adapters.sms.base import DeliveryState, SendOutcome, SmsLookup, SmsSender
from app.audit import record_job
from app.auth.crypto import decrypt
from app.auth.tokens import new_token
from app.core.config import Settings
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_FILE,
    TB_RFND,
    TB_SMS_DMND,
    TB_SMS_SNDNG_HSTRY,
    TB_SMS_TRGT,
    TB_STLM,
    TB_STLM_EVENT,
)
from app.domain.admin.refund_service import pg_key, settle_cancel
from app.domain.admin.transaction_service import RECHECK_MAX, RECHECK_PREFIX, next_event_id
from app.domain.application.seats import expire_application, lock_course
from app.domain.payment.service import lock_application, lock_payment, record_event, settle_payment
from app.files.storage import StorageError, read_blob

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


# --- 문자 발송 ----------------------------------------------------------------------------------

SEND_STATUS = {
    SendOutcome.ACCEPTED: "SS.SENDING",
    SendOutcome.REJECTED: "SS.FAIL",
    SendOutcome.UNKNOWN: "SS.UNKNOWN",
}
# OTP 문자는 인증번호 원문을 아는 API가 직접 보낸다. 워커는 건드리지 않는다(TDD 8.1)
NOT_OTP = or_(TB_SMS_DMND.c.SRC_EVENT_ID.is_(None), ~TB_SMS_DMND.c.SRC_EVENT_ID.like("CERT:%"))


def _attempt_key(trgt_sn: int, seq: int) -> str:
    return f"sms-{trgt_sn}-{seq}"


def dispatch_sms(db: Session, settings: Settings, sender: SmsSender, bundle_sn: int, clock: Clock) -> int:
    """아웃박스에 쌓인 문자(수신대상 SS.WAIT)를 보낸다(TDD 7.3, FN-028). 시도한 수를 돌려준다.

    보내기 전에 시도 행과 결과 확인 중(SS.UNKNOWN)을 먼저 커밋한다. 발송 직후 죽어도 같은 문자를 새로 보내지 않고
    조회로 확인한다. 확인된 실패와 결과 불명은 자동으로 다시 보내지 않는다(SMS-04).
    """
    due = db.execute(
        select(TB_SMS_TRGT.c.SMS_TRGT_SN)
        .join(TB_SMS_DMND, TB_SMS_DMND.c.SMS_DMND_SN == TB_SMS_TRGT.c.SMS_DMND_SN)
        .where(TB_SMS_TRGT.c.OPER_BNDL_SN == bundle_sn, TB_SMS_TRGT.c.TRGT_STTS_CD == "SS.WAIT", NOT_OTP)
        .order_by(TB_SMS_TRGT.c.SMS_TRGT_SN)
        .limit(BATCH)
    ).all()
    db.rollback()
    sent = 0
    for item in due:
        trgt_sn = int(item.SMS_TRGT_SN)
        now = clock()
        target = db.execute(
            select(TB_SMS_TRGT).where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn).with_for_update(skip_locked=True)
        ).first()
        if target is None or target.TRGT_STTS_CD != "SS.WAIT":  # 다른 처리가 잡았거나 이미 보냈다
            db.rollback()
            continue
        request = db.execute(
            select(TB_SMS_DMND.c.SMS_CN, TB_SMS_DMND.c.DSPTCH_TELNO).where(
                TB_SMS_DMND.c.SMS_DMND_SN == target.SMS_DMND_SN
            )
        ).one()
        key = _attempt_key(trgt_sn, 1)
        db.execute(
            insert(TB_SMS_SNDNG_HSTRY).values(
                OPER_BNDL_SN=bundle_sn,
                SMS_TRGT_SN=trgt_sn,
                SNDNG_SEQ=1,
                SPLR_NM=sender.provider_name,
                SPLR_ACNT_ID=sender.provider_name,
                IDEM_KEY=key,
                PRCS_STTS_CD="SS.UNKNOWN",
                SNDNG_DMND_DT=now,
                RCRD_VER=1,
            )
        )
        db.execute(
            update(TB_SMS_TRGT)
            .where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn)
            .values(TRGT_STTS_CD="SS.UNKNOWN", MDFCN_DT=now, RCRD_VER=TB_SMS_TRGT.c.RCRD_VER + 1)
        )
        phone = decrypt(settings.secret_key, str(target.RCPTN_TELNO_ENCPT_VL))
        text, from_number = str(request.SMS_CN), str(request.DSPTCH_TELNO)
        db.commit()  # 시도를 먼저 확정한다. 공급자 호출은 잠금·트랜잭션 밖이다
        try:
            result = sender.send(to=phone, text=text, sender=from_number, idempotency_key=key)
            outcome, message_id, failure = result.outcome, result.message_id, result.failure_code
        except Exception:  # 통신 오류는 결과 불명이다. 새로 보내지 않고 조회한다
            outcome, message_id, failure = SendOutcome.UNKNOWN, None, "SEND_ERROR"
        status = SEND_STATUS[outcome]
        now = clock()
        db.execute(
            update(TB_SMS_SNDNG_HSTRY)
            .where(TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == trgt_sn, TB_SMS_SNDNG_HSTRY.c.SNDNG_SEQ == 1)
            .values(
                PRCS_STTS_CD=status,
                SPLR_MSG_ID=message_id,
                FAIL_CD=failure,
                RSLT_IDNTY_DT=now if outcome is SendOutcome.REJECTED else None,
                RCRD_VER=TB_SMS_SNDNG_HSTRY.c.RCRD_VER + 1,
            )
        )
        db.execute(
            update(TB_SMS_TRGT)
            .where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn)
            .values(TRGT_STTS_CD=status, MDFCN_DT=now, RCRD_VER=TB_SMS_TRGT.c.RCRD_VER + 1)
        )
        db.commit()
        sent += 1
    return sent


def recheck_sms(db: Session, sender: SmsSender, bundle_sn: int, clock: Clock) -> int:
    """공급자가 접수한 문자(SS.SENDING)의 최종 전달과 결과를 모르는 문자(SS.UNKNOWN)의 실제 발송 여부를 조회한다.

    전달 확인이면 SS.SENT, 실패 확인이면 SS.FAIL로 바꾼다. 아직 모르면 그대로 두고 새로 보내지 않는다. 조회한 수를 돌려준다.
    """
    now = clock()
    latest = (
        select(func.max(TB_SMS_SNDNG_HSTRY.c.SNDNG_SEQ))
        .where(TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == TB_SMS_TRGT.c.SMS_TRGT_SN)
        .correlate(TB_SMS_TRGT)
        .scalar_subquery()
    )
    due = db.execute(
        select(TB_SMS_TRGT.c.SMS_TRGT_SN, TB_SMS_SNDNG_HSTRY.c.IDEM_KEY, TB_SMS_SNDNG_HSTRY.c.SPLR_MSG_ID)
        .join(TB_SMS_DMND, TB_SMS_DMND.c.SMS_DMND_SN == TB_SMS_TRGT.c.SMS_DMND_SN)
        .join(
            TB_SMS_SNDNG_HSTRY,
            (TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == TB_SMS_TRGT.c.SMS_TRGT_SN)
            & (TB_SMS_SNDNG_HSTRY.c.SNDNG_SEQ == latest),
        )
        .where(
            TB_SMS_TRGT.c.OPER_BNDL_SN == bundle_sn,
            TB_SMS_TRGT.c.TRGT_STTS_CD.in_(("SS.SENDING", "SS.UNKNOWN")),
            TB_SMS_SNDNG_HSTRY.c.SNDNG_DMND_DT <= now - SETTLE_GRACE,
            NOT_OTP,
        )
        .order_by(TB_SMS_TRGT.c.SMS_TRGT_SN)
        .limit(BATCH)
    ).all()
    db.rollback()
    checked = 0
    for item in due:
        trgt_sn = int(item.SMS_TRGT_SN)
        try:
            found = sender.lookup(idempotency_key=str(item.IDEM_KEY), message_id=item.SPLR_MSG_ID)
        except Exception:  # 조회 실패는 아직 모르는 것이다
            found = SmsLookup(DeliveryState.UNKNOWN, "LOOKUP_ERROR")
        checked += 1
        if found.state not in (DeliveryState.DELIVERED, DeliveryState.FAILED):
            continue
        now = clock()
        target = db.execute(
            select(TB_SMS_TRGT.c.TRGT_STTS_CD)
            .where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn)
            .with_for_update(skip_locked=True)
        ).first()
        if target is None or target.TRGT_STTS_CD not in ("SS.SENDING", "SS.UNKNOWN"):
            db.rollback()
            continue
        delivered = found.state is DeliveryState.DELIVERED
        status = "SS.SENT" if delivered else "SS.FAIL"
        db.execute(
            update(TB_SMS_SNDNG_HSTRY)
            .where(
                TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == trgt_sn, TB_SMS_SNDNG_HSTRY.c.IDEM_KEY == item.IDEM_KEY
            )
            .values(
                PRCS_STTS_CD=status,
                RSLT_IDNTY_DT=now,
                FAIL_CD=None if delivered else found.failure_code,
                RCRD_VER=TB_SMS_SNDNG_HSTRY.c.RCRD_VER + 1,
            )
        )
        db.execute(
            update(TB_SMS_TRGT)
            .where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn)
            .values(TRGT_STTS_CD=status, MDFCN_DT=now, RCRD_VER=TB_SMS_TRGT.c.RCRD_VER + 1)
        )
        db.commit()
    return checked


# --- 파일 검사 ----------------------------------------------------------------------------------


def scan_files(db: Session, settings: Settings, scanner: FileScanner, bundle_sn: int, clock: Clock) -> int:
    """검사 대기(FS.PENDING) 파일을 검사해 통과(FS.SAFE)나 차단(FS.BLOCK)으로 정한다(TDD 7.4, NF-SER-002). 정한 수를 돌려준다.

    저장된 내용의 해시가 올릴 때의 값과 다르면 바뀐 파일이라 차단한다. 검사기에 닿지 못하거나 파일을 읽지 못하면
    통과로 보지 않고 검사 대기로 두어 다음 주기에 다시 한다. 차단 사유(탐지 이름)는 로그·이력에 남기지 않는다.
    """
    due = db.execute(
        select(TB_FILE.c.FILE_SN)
        .where(TB_FILE.c.OPER_BNDL_SN == bundle_sn, TB_FILE.c.FILE_STTS_CD == "FS.PENDING")
        .order_by(TB_FILE.c.REG_DT, TB_FILE.c.FILE_SN)
        .limit(BATCH)
    ).all()
    db.rollback()
    decided = 0
    for item in due:
        file_sn = int(item.FILE_SN)
        info = db.execute(
            select(TB_FILE.c.STRG_KEY, TB_FILE.c.FILE_HASH_VL).where(TB_FILE.c.FILE_SN == file_sn)
        ).one()
        db.rollback()
        try:
            data = read_blob(settings.file_root, str(info.STRG_KEY))
        except StorageError:
            log.warning("검사할 파일을 읽지 못했다 file=%s", file_sn)
            continue
        if hashlib.sha256(data).hexdigest() != str(info.FILE_HASH_VL):
            safe = False  # 올린 뒤 내용이 바뀌었다
        else:
            try:
                safe = scanner.scan(data).clean
            except ScanUnavailable:
                log.warning("파일 검사기에 닿지 못했다")
                continue
        now = clock()
        target = db.execute(
            select(TB_FILE.c.FILE_STTS_CD)
            .where(TB_FILE.c.FILE_SN == file_sn)
            .with_for_update(skip_locked=True)
        ).first()
        if target is None or target.FILE_STTS_CD != "FS.PENDING":  # 그 사이 삭제 등 다른 처리가 먼저 끝냈다
            db.rollback()
            continue
        db.execute(
            update(TB_FILE)
            .where(TB_FILE.c.FILE_SN == file_sn)
            .values(FILE_STTS_CD="FS.SAFE" if safe else "FS.BLOCK", MDFCN_DT=now)
        )
        record_job(
            db,
            actor="AK.SYSTEM",
            job="FILE_SCAN",
            table="TB_FILE",
            key=file_sn,
            request_id=_request_id(),
            now=now,
            bundle_sn=bundle_sn,
            change="검사 통과" if safe else "차단",
        )
        db.commit()
        decided += 1
    return decided
