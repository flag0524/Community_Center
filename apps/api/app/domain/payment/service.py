# 결제 요청·승인 확인·영수증. PG 호출은 트랜잭션 밖에서 하고 결과를 모르면 자리를 지킨다(ADR-006, TDD 5.4)
import hashlib
import json
import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.pg.base import CURRENCY, ApproveOutcome, ApproveResult, PaymentGateway
from app.audit import record_job
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_MBR, TB_STLM, TB_STLM_EVENT
from app.domain.application.seats import cancel_ready_payments, expire_application, lock_course
from app.domain.application.service import PAYMENT, get_mine
from app.domain.payment.schemas import (
    PaymentConfirmRequest,
    PaymentConfirmResult,
    PaymentRequestResult,
    Receipt,
)
from app.domain.payment.types import PaymentMethod, PaymentStatus

log = logging.getLogger("app.payment")
DUPLICATE_ENTRY = 1062
METHOD_CODE = {PaymentMethod.CARD: "PM.CARD", PaymentMethod.TRANSFER: "PM.TRANSFER"}
CODE_METHOD = {code: method for method, code in METHOD_CODE.items()}
IDEM_UNIQUE = "UQ_STLM_03"  # (운영묶음, 멱등키) 유일키 이름
PAYMENT_KEY_UNIQUE = "UQ_STLM_04"  # (대행사, 가맹점, 거래 아이디) 유일키 이름


def _new_order_no() -> str:
    """내부 일련번호와 분리한 주문번호. 추측할 수 없는 난수이고 20자 안이다."""
    return "JR" + secrets.token_hex(8).upper()


def _owned_application(db: Session, bundle_sn: int, member_sn: int, application_sn: int) -> Any:
    row = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN).where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn,
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
        )
    ).first()
    if row is None:  # 남의 신청은 없는 신청과 같다(RQ-SER-NF-001)
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def lock_application(db: Session, bundle_sn: int, application_sn: int) -> Any:
    return db.execute(
        select(TB_ATNLC_APLY)
        .where(TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn, TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
        .with_for_update()
    ).one()


def _has_status(db: Session, bundle_sn: int, application_sn: int, status: str) -> bool:
    return (
        db.execute(
            select(TB_STLM.c.STLM_SN).where(
                TB_STLM.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM.c.ATNLC_APLY_SN == application_sn,
                TB_STLM.c.STLM_STTS_CD == status,
            )
        ).first()
        is not None
    )


def record_event(
    db: Session,
    bundle_sn: int,
    stlm_sn: int,
    *,
    kind: str,
    event_id: str,
    status: str,
    content: dict[str, Any],
    now: datetime,
    fail_reason: str | None = None,
    refund_sn: int | None = None,
) -> None:
    """PG와 주고받은 사건을 남긴다. 정규화한 허용 항목만 담고 PG 전문은 복사하지 않는다(스키마 4.23)."""
    body = json.dumps(content, ensure_ascii=False, sort_keys=True)
    db.execute(
        insert(TB_STLM_EVENT).values(
            OPER_BNDL_SN=bundle_sn,
            STLM_SN=stlm_sn,
            RFND_SN=refund_sn,
            EVENT_TYPE_CD=kind,
            EVENT_ID=event_id,
            PRCS_STTS_CD=status,
            EVENT_HASH_VL=hashlib.sha256(body.encode()).hexdigest(),
            EVENT_CN=body,
            RCPTN_DT=now,
            PRCS_DT=None if status in ("EP.RECEIVED", "EP.PROCESS") else now,
            FAIL_RSN=fail_reason,
        )
    )


def _audit(
    db: Session,
    *,
    job: str,
    bundle_sn: int,
    member_sn: int,
    stlm_sn: int,
    request_id: str,
    now: datetime,
    change: str,
) -> None:
    record_job(
        db,
        actor="AK.MEMBER",
        job=job,
        table="TB_STLM",
        key=stlm_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=change,
    )


# --- 결제 요청 --------------------------------------------------------------------------------


def _request_result(
    gateway: PaymentGateway, payment: Any, deadline: datetime, now: datetime
) -> PaymentRequestResult:
    method = CODE_METHOD[str(payment.STLM_MNS_CD)]
    return PaymentRequestResult(
        server_now=utc(now),
        payment_id=str(int(payment.STLM_SN)),
        order_no=str(payment.STLM_NO),
        amount=int(payment.STLM_AMT),
        method=method,
        deadline=utc(deadline),
        gateway=gateway.provider_name,
        gateway_params=gateway.prepare(
            order_no=str(payment.STLM_NO), amount=int(payment.STLM_AMT), method=method.value
        ),
    )


def _ensure_payable(
    db: Session, settings: Settings, course: Any, application: Any, *, now: datetime, request_id: str
) -> None:
    """결제할 수 있는 신청인지 잠금 아래에서 확인한다. 기한이 지났으면 그 자리에서 만료시키고 알린다."""
    bundle_sn, application_sn = int(application.OPER_BNDL_SN), int(application.ATNLC_APLY_SN)
    if _has_status(db, bundle_sn, application_sn, "PS.PENDING"):
        raise ApiError(ErrorCode.PAY_RESULT_PENDING)  # 결과 확인 중에는 재결제를 막는다(ADR-006)
    if application.APLY_STTS_CD == "ES.EXPIRE":
        raise ApiError(ErrorCode.PAY_DEADLINE_EXPIRED)
    if application.APLY_STTS_CD != "ES.HOLD" or int(application.STLM_PRNMNT_AMT) == 0:
        raise ApiError(ErrorCode.PAY_NOT_PAYABLE)
    if application.STLM_DDLN_DT is None or now >= application.STLM_DDLN_DT:
        expire_application(db, settings, course, application, now=now, request_id=request_id)
        db.commit()  # 만료 처리는 오류 응답과 함께 사라지지 않게 먼저 확정한다
        raise ApiError(ErrorCode.PAY_DEADLINE_EXPIRED)


def request_payment(
    db: Session,
    settings: Settings,
    gateway: PaymentGateway,
    *,
    member_sn: int,
    bundle_sn: int,
    application_id: str,
    method: PaymentMethod,
    idem_key: str,
    request_id: str,
    now: datetime,
) -> PaymentRequestResult:
    application_sn = int(application_id)
    owned = _owned_application(db, bundle_sn, member_sn, application_sn)
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))  # 강좌 → 신청 순서(C07)
    application = lock_application(db, bundle_sn, application_sn)

    # 같은 키: 같은 신청·수단이면 이전 결과, 다르면 충돌. 기한은 신청의 값 그대로라 늘어나지 않는다(FN-036)
    prior = db.execute(
        select(TB_STLM).where(TB_STLM.c.OPER_BNDL_SN == bundle_sn, TB_STLM.c.IDEM_KEY == idem_key)
    ).first()
    if prior is not None:
        if int(prior.ATNLC_APLY_SN) != application_sn or prior.STLM_MNS_CD != METHOD_CODE[method]:
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _request_result(gateway, prior, application.STLM_DDLN_DT or now, now)

    _ensure_payable(db, settings, course, application, now=now, request_id=request_id)
    cancel_ready_payments(db, bundle_sn, application_sn, now)  # 이전에 발급한 결제창은 쓰지 못하게 한다
    values: dict[str, Any] = {
        "OPER_BNDL_SN": bundle_sn,
        "ATNLC_APLY_SN": application_sn,
        "STLM_NO": _new_order_no(),
        "PG_NM": gateway.provider_name,
        "FRCS_ID": gateway.merchant_id,
        "STLM_STTS_CD": "PS.READY",
        "STLM_MNS_CD": METHOD_CODE[method],
        "STLM_AMT": int(application.STLM_PRNMNT_AMT),  # 금액은 신청에 저장한 값이다. 요청 값은 쓰지 않는다
        "IDEM_KEY": idem_key,
        "STLM_DMND_DT": now,
        "STLM_EXPRY_DT": application.STLM_DDLN_DT,
        "REG_DT": now,
    }
    try:
        stlm_sn = int(db.execute(insert(TB_STLM).values(**values).returning(TB_STLM.c.STLM_SN)).scalar_one())
    except IntegrityError as error:
        # 같은 키를 다른 신청이 동시에 쓰면 잠금이 겹치지 않아 유일키가 마지막으로 막는다
        if (
            error.orig is not None
            and error.orig.args[0] == DUPLICATE_ENTRY
            and IDEM_UNIQUE in str(error.orig.args[1])
        ):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT) from None
        raise
    _audit(
        db,
        job="PAY_REQUEST",
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        stlm_sn=stlm_sn,
        request_id=request_id,
        now=now,
        change=f"결제 요청({METHOD_CODE[method]})",
    )
    created = db.execute(select(TB_STLM).where(TB_STLM.c.STLM_SN == stlm_sn)).one()
    return _request_result(gateway, created, application.STLM_DDLN_DT, now)


# --- 승인 확인 --------------------------------------------------------------------------------


def _confirm_result(
    db: Session,
    member_sn: int,
    bundle_sn: int,
    stlm_sn: int,
    application_sn: int,
    status: PaymentStatus,
    now: datetime,
) -> PaymentConfirmResult:
    state = get_mine(db, member_sn, bundle_sn, str(application_sn), now).display_state
    return PaymentConfirmResult(
        server_now=utc(now),
        payment_id=str(stlm_sn),
        status=status,
        application_id=str(application_sn),
        application_display_state=state,
    )


def _find_payment(db: Session, bundle_sn: int, member_sn: int, order_no: str) -> Any:
    row = db.execute(
        select(TB_STLM.c.STLM_SN, TB_STLM.c.ATNLC_APLY_SN)
        .join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN),
        )
        .where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM.c.STLM_NO == order_no,
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def lock_payment(db: Session, stlm_sn: int) -> Any:
    return db.execute(select(TB_STLM).where(TB_STLM.c.STLM_SN == stlm_sn).with_for_update()).one()


def confirm_payment(
    db: Session,
    settings: Settings,
    gateway: PaymentGateway,
    *,
    member_sn: int,
    bundle_sn: int,
    body: PaymentConfirmRequest,
    request_id: str,
    clock: Callable[[], datetime],
) -> PaymentConfirmResult:
    now = clock()
    found = _find_payment(db, bundle_sn, member_sn, body.order_no)
    stlm_sn, application_sn = int(found.STLM_SN), int(found.ATNLC_APLY_SN)

    # 1단계: 잠금 아래에서 검증하고 승인 요청 직전에 PS.PENDING을 커밋한다(결과를 모르는 동안 자리를 지킨다)
    owned = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
    ).one()
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))
    application = lock_application(db, bundle_sn, application_sn)
    payment = lock_payment(db, stlm_sn)
    if body.amount != int(payment.STLM_AMT):  # 브라우저가 보낸 금액은 대조에만 쓴다(R13)
        raise ApiError(ErrorCode.PAY_AMOUNT_MISMATCH)
    status = str(payment.STLM_STTS_CD)
    if status == "PS.PAID":  # 이미 끝난 결제를 다시 확인하면 같은 결과다
        return _confirm_result(db, member_sn, bundle_sn, stlm_sn, application_sn, PaymentStatus.PAID, now)
    if status == "PS.PENDING":
        raise ApiError(ErrorCode.PAY_RESULT_PENDING)
    if status != "PS.READY":
        raise ApiError(ErrorCode.PAY_NOT_PAYABLE)
    _ensure_payable(db, settings, course, application, now=now, request_id=request_id)
    try:
        db.execute(
            update(TB_STLM)
            .where(TB_STLM.c.STLM_SN == stlm_sn)
            .values(
                STLM_STTS_CD="PS.PENDING",
                PG_DLNG_ID=body.payment_key,
                MDFCN_DT=now,
                RCRD_VER=TB_STLM.c.RCRD_VER + 1,
            )
        )
    except IntegrityError as error:
        if (
            error.orig is not None
            and error.orig.args[0] == DUPLICATE_ENTRY
            and PAYMENT_KEY_UNIQUE in str(error.orig.args[1])
        ):
            raise ApiError(ErrorCode.PAY_NOT_PAYABLE) from None  # 이미 다른 결제에 쓴 거래 아이디다
        raise
    record_event(
        db,
        bundle_sn,
        stlm_sn,
        kind="ET.REQUEST",
        event_id=f"REQ:{body.order_no}",
        status="EP.PROCESS",
        content={"orderNo": body.order_no, "amount": body.amount},
        now=now,
    )
    db.commit()

    # 2단계: 트랜잭션과 잠금 밖에서 PG를 부른다. 예외나 시간 초과는 결과 불명으로 본다.
    try:
        approval = gateway.approve(order_no=body.order_no, payment_key=body.payment_key, amount=body.amount)
    except Exception as error:  # 어댑터가 예외를 던져도 결제 결과는 알 수 없는 것으로 다룬다
        log.warning("PG 승인 요청 실패 type=%s", type(error).__name__)
        approval = ApproveResult(ApproveOutcome.UNKNOWN, failure_code="GATEWAY_ERROR")

    # 3단계: 다시 잠그고 결과를 반영한다. PG가 응답하는 사이 시간이 흘렀으므로 시각을 새로 읽는다.
    return _apply_result(
        db,
        settings,
        member_sn=member_sn,
        bundle_sn=bundle_sn,
        stlm_sn=stlm_sn,
        application_sn=application_sn,
        approval=approval,
        merchant_id=gateway.merchant_id,
        request_id=request_id,
        now=clock(),
    )


@dataclass(frozen=True)
class Settled:
    """PG 결과를 반영한 뒤의 상태. 사건·감사 기록은 부른 쪽이 자기 경로에 맞게 남긴다."""

    status: PaymentStatus
    event_status: str  # EP.DONE(반영 완료) / EP.PROCESS(결과 불명) / EP.FAIL(대사 필요)
    audit: str
    content: dict[str, Any]
    fail_reason: str | None = None


def _mismatch(approval: ApproveResult, payment: Any, merchant_id: str) -> str | None:
    """승인 응답이 우리 값과 다른 항목. 금액·통화·가맹점·주문번호를 모두 대조한다(TRD 4.7, R13)."""
    if approval.order_no != str(payment.STLM_NO):
        return "주문번호"
    if approval.amount != int(payment.STLM_AMT):
        return "금액"
    if approval.merchant_id != merchant_id:
        return "가맹점"
    if approval.currency != CURRENCY:
        return "통화"
    return None


def settle_payment(
    db: Session,
    settings: Settings,
    *,
    merchant_id: str,
    course: Any,
    application: Any,
    payment: Any,
    approval: ApproveResult,
    now: datetime,
    request_id: str,
) -> Settled:
    """강좌·신청·결제를 잠근 상태에서 PG 결과를 반영한다. 승인 확인과 통보가 같은 규칙을 쓴다."""
    stlm_sn = int(payment.STLM_SN)
    application_sn = int(application.ATNLC_APLY_SN)
    status = str(payment.STLM_STTS_CD)
    current = PAYMENT.get(status, PaymentStatus.PENDING)
    content: dict[str, Any] = {"orderNo": str(payment.STLM_NO), "outcome": approval.outcome.value}
    if approval.amount is not None:
        content["amount"] = approval.amount
    if approval.transaction_id:
        content["txId"] = approval.transaction_id
    approved = approval.outcome is ApproveOutcome.APPROVED

    if status == "PS.PAID":  # 이미 반영됐다
        return Settled(current, "EP.DONE", "이미 결제완료", content)
    if status not in ("PS.READY", "PS.PENDING"):
        if approved:  # 우리 쪽은 닫힌 결제인데 PG는 승인했다. 돈이 나갔으므로 사람이 확인해야 한다(R12)
            note = "승인됐으나 결제가 이미 닫힘(보상환불 필요)"
            return Settled(current, "EP.FAIL", note, content, note)
        return Settled(current, "EP.DONE", "이미 종료된 결제", content)

    if approved:
        reason = _mismatch(approval, payment, merchant_id)
        if reason is not None:
            # 확정하지 않고 자리를 지킨 채 대사로 올린다(R13, TDD 412)
            return Settled(
                current,
                "EP.FAIL",
                f"승인 응답 불일치({reason}, 대사 필요)",
                content,
                f"승인 응답의 {reason} 불일치",
            )
        if application.APLY_STTS_CD != "ES.HOLD":
            note = "승인됐으나 신청이 유효하지 않음(보상환불 필요)"
            return Settled(current, "EP.FAIL", note, content, note)
        db.execute(
            update(TB_STLM)
            .where(TB_STLM.c.STLM_SN == stlm_sn)
            .values(
                STLM_STTS_CD="PS.PAID",
                STLM_APRV_NO=approval.approval_no,
                STLM_APRV_DT=approval.approved_at or now,
                # PG_DLNG_ID는 결제창이 준 paymentKey 그대로 둔다. 같은 거래를 두 결제에 연결하지 못하게 막는
                # 유일키이고 환불 때도 이 값을 쓴다. PG 응답의 거래 번호는 사건 기록에 남긴다.
                MDFCN_DT=now,
                RCRD_VER=TB_STLM.c.RCRD_VER + 1,
            )
        )
        # 결과를 기다리는 동안 자리를 지켰으므로 기한이 그 사이 지났어도 확정한다(ADR-006)
        db.execute(
            update(TB_ATNLC_APLY)
            .where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
            .values(APLY_STTS_CD="ES.CONFIRM", MDFCN_DT=now, RCRD_VER=TB_ATNLC_APLY.c.RCRD_VER + 1)
        )
        return Settled(PaymentStatus.PAID, "EP.DONE", "결제 승인", content)

    if approval.outcome is ApproveOutcome.REJECTED:
        db.execute(
            update(TB_STLM)
            .where(TB_STLM.c.STLM_SN == stlm_sn)
            .values(
                STLM_STTS_CD="PS.FAIL",
                FAIL_CD=approval.failure_code,
                FAIL_RSN="결제 승인 거절",
                MDFCN_DT=now,
                RCRD_VER=TB_STLM.c.RCRD_VER + 1,
            )
        )
        # 기한이 남았으면 다시 결제할 수 있게 자리를 지키고, 지났으면 만료시켜 자리를 돌려준다(TDD 5.4)
        if application.APLY_STTS_CD == "ES.HOLD" and (
            application.STLM_DDLN_DT is None or now >= application.STLM_DDLN_DT
        ):
            expire_application(db, settings, course, application, now=now, request_id=request_id)
        return Settled(PaymentStatus.FAILED, "EP.DONE", "결제 승인 거절", content)

    # 결과 불명: 상태를 바꾸지 않고 자리를 지킨다. 재조회는 워커가 한다(B5)
    return Settled(current, "EP.PROCESS", "승인 결과 불명(확인 중)", content, approval.failure_code)


def _apply_result(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    stlm_sn: int,
    application_sn: int,
    approval: ApproveResult,
    merchant_id: str,
    request_id: str,
    now: datetime,
) -> PaymentConfirmResult:
    owned = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
    ).one()
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))
    application = lock_application(db, bundle_sn, application_sn)
    payment = lock_payment(db, stlm_sn)
    if payment.STLM_STTS_CD != "PS.PENDING":  # 그 사이 다른 경로(통보·대사)가 먼저 끝냈다. 그 결과를 따른다
        status = PAYMENT.get(str(payment.STLM_STTS_CD), PaymentStatus.PENDING)
        return _confirm_result(db, member_sn, bundle_sn, stlm_sn, application_sn, status, now)

    settled = settle_payment(
        db,
        settings,
        merchant_id=merchant_id,
        course=course,
        application=application,
        payment=payment,
        approval=approval,
        now=now,
        request_id=request_id,
    )
    event_id = f"RES:{approval.transaction_id}" if approval.transaction_id else f"RES:{now.isoformat()}"
    record_event(
        db,
        bundle_sn,
        stlm_sn,
        kind="ET.RESPONSE",
        event_id=event_id,
        status=settled.event_status,
        content=settled.content,
        now=now,
        fail_reason=settled.fail_reason,
    )
    _audit(
        db,
        job="PAY_CONFIRM",
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        stlm_sn=stlm_sn,
        request_id=request_id,
        now=now,
        change=settled.audit,
    )
    return _confirm_result(db, member_sn, bundle_sn, stlm_sn, application_sn, settled.status, now)


# --- PG 통보(웹훅) ----------------------------------------------------------------------------


class WebhookResult(StrEnum):
    PROCESSED = "processed"  # 새 통보를 거래 조회로 확인해 반영했다
    DUPLICATE = "duplicate"  # 이미 받은 통보다. 업무를 다시 바꾸지 않는다
    CONFLICT = "conflict"  # 같은 사건 번호에 다른 내용이다. 업무에 반영하지 않고 보안 사건으로 남긴다
    UNIDENTIFIED = "unidentified"  # 서명은 맞지만 우리 주문이 아니다. 격리한다
    RETRY = "retry"  # 거래 조회에 실패해 재시도 대상으로 남겼다


security_log = logging.getLogger("app.security")


def receive_webhook(
    db: Session,
    settings: Settings,
    gateway: PaymentGateway,
    *,
    bundle_sn: int,
    headers: Mapping[str, str],
    body: bytes,
    request_id: str,
    clock: Callable[[], datetime],
) -> WebhookResult:
    """서명을 확인하고 사건을 멱등으로 저장한 뒤, 통보 내용이 아니라 거래 조회 결과로 반영한다(TDD 5.4.2).

    서명이 틀리면 WebhookRejected가 올라가고 아무것도 저장하지 않는다.
    """
    event = gateway.parse_webhook(headers=headers, body=body)
    now = clock()
    payment = db.execute(
        select(TB_STLM.c.STLM_SN, TB_STLM.c.ATNLC_APLY_SN).where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn, TB_STLM.c.STLM_NO == event.order_no
        )
    ).first()
    if payment is None:
        security_log.warning("식별할 수 없는 PG 통보 격리 request_id=%s", request_id)
        return WebhookResult.UNIDENTIFIED
    stlm_sn, application_sn = int(payment.STLM_SN), int(payment.ATNLC_APLY_SN)

    content = {"eventId": event.event_id, "orderNo": event.order_no}
    try:
        db.execute(
            insert(TB_STLM_EVENT).values(
                OPER_BNDL_SN=bundle_sn,
                STLM_SN=stlm_sn,
                EVENT_TYPE_CD="ET.WEBHOOK",
                EVENT_ID=event.event_id,
                PRCS_STTS_CD="EP.RECEIVED",
                EVENT_HASH_VL=event.digest,
                EVENT_CN=json.dumps(content, ensure_ascii=False, sort_keys=True),
                RCPTN_DT=now,
            )
        )
    except IntegrityError as error:
        if error.orig is None or error.orig.args[0] != DUPLICATE_ENTRY:
            raise
        db.rollback()  # 중복 키로 실패한 요청의 트랜잭션을 끝내고 이미 받은 사건을 읽는다
        known = db.execute(
            select(TB_STLM_EVENT.c.EVENT_HASH_VL).where(
                TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM_EVENT.c.STLM_SN == stlm_sn,
                TB_STLM_EVENT.c.EVENT_ID == event.event_id,
            )
        ).scalar_one()
        if known == event.digest:
            return WebhookResult.DUPLICATE
        security_log.warning("PG 통보 충돌 request_id=%s", request_id)
        record_job(
            db,
            actor="AK.SYSTEM",
            job="PAY_WEBHOOK",
            table="TB_STLM",
            key=stlm_sn,
            request_id=request_id,
            now=now,
            bundle_sn=bundle_sn,
            result="JR.DENY",
            change="같은 사건 번호에 다른 내용의 통보(업무 반영 안 함)",
        )
        db.commit()
        return WebhookResult.CONFLICT
    db.commit()  # 받은 사건을 먼저 확정한다. 여기서부터는 PG를 부르므로 잠금을 쥐지 않는다

    try:
        approval = gateway.lookup(order_no=event.order_no)
    except Exception as error:  # 조회 실패는 결과 불명이다. 통보 내용만으로 반영하지 않는다
        log.warning("PG 거래 조회 실패 type=%s", type(error).__name__)
        approval = ApproveResult(ApproveOutcome.UNKNOWN, failure_code="GATEWAY_ERROR")

    now = clock()
    owned = db.execute(
        select(TB_ATNLC_APLY.c.CORS_SN).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn)
    ).one()
    course = lock_course(db, bundle_sn, int(owned.CORS_SN))
    application = lock_application(db, bundle_sn, application_sn)
    payment_row = lock_payment(db, stlm_sn)
    settled = settle_payment(
        db,
        settings,
        merchant_id=gateway.merchant_id,
        course=course,
        application=application,
        payment=payment_row,
        approval=approval,
        now=now,
        request_id=request_id,
    )
    retry = approval.outcome is ApproveOutcome.UNKNOWN
    db.execute(
        update(TB_STLM_EVENT)
        .where(
            TB_STLM_EVENT.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM_EVENT.c.STLM_SN == stlm_sn,
            TB_STLM_EVENT.c.EVENT_ID == event.event_id,
        )
        .values(
            PRCS_STTS_CD="EP.FAIL" if retry else settled.event_status,  # 조회 실패는 워커가 다시 시도한다
            PRCS_DT=now,
            RTRY_NMTM=1 if retry else 0,
            FAIL_RSN=settled.fail_reason,
        )
    )
    record_job(
        db,
        actor="AK.SYSTEM",
        job="PAY_WEBHOOK",
        table="TB_STLM",
        key=stlm_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        change=settled.audit,
    )
    return WebhookResult.RETRY if retry else WebhookResult.PROCESSED


# --- 영수증 -----------------------------------------------------------------------------------


def get_receipt(db: Session, *, member_sn: int, bundle_sn: int, payment_id: str) -> Receipt:
    row = db.execute(
        select(
            TB_STLM.c.STLM_SN,
            TB_STLM.c.ATNLC_APLY_SN,
            TB_STLM.c.STLM_MNS_CD,
            TB_STLM.c.STLM_AMT,
            TB_STLM.c.STLM_APRV_NO,
            TB_STLM.c.STLM_APRV_DT,
            TB_CORS.c.CORS_NM,
            TB_MBR.c.MBR_NM,
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
        .join(TB_MBR, TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN)
        .where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM.c.STLM_SN == int(payment_id),
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
            TB_STLM.c.STLM_STTS_CD == "PS.PAID",  # 결제가 끝난 건만 영수증이 있다
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return Receipt(
        payment_id=str(int(row.STLM_SN)),
        application_id=str(int(row.ATNLC_APLY_SN)),
        course_name=str(row.CORS_NM),
        method=CODE_METHOD[str(row.STLM_MNS_CD)],
        amount=int(row.STLM_AMT),
        approval_no=str(row.STLM_APRV_NO),
        approved_at=utc(row.STLM_APRV_DT),
        payer_name=str(row.MBR_NM),
    )
