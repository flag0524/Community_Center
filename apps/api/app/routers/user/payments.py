# 결제 요청, 승인 확인, 영수증 라우터. PG 웹훅은 별도 경로(/api/pg/webhook)로 P5에서 추가한다.
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.payment.schemas import (
    PaymentConfirmRequest,
    PaymentConfirmResult,
    PaymentRequestCreate,
    PaymentRequestResult,
    Receipt,
)
from app.routers.deps import (
    MEMBER_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

router = APIRouter(tags=["payments"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])

PAY_ERRORS = error_responses(
    ErrorCode.PAY_NOT_PAYABLE,
    ErrorCode.PAY_DEADLINE_EXPIRED,
    ErrorCode.PAY_RESULT_PENDING,
    ErrorCode.PAY_AMOUNT_MISMATCH,
    ErrorCode.IDEMPOTENCY_CONFLICT,
)


@router.post(
    "/me/applications/{application_id}/payments",
    status_code=201,
    responses=PAY_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def request_payment(
    application_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="신청 일련번호(문자열)")],
    body: PaymentRequestCreate,
    idempotency_key: IdempotencyKey,
) -> PaymentRequestResult:
    not_implemented()


@router.post("/payments/confirm", responses=PAY_ERRORS, dependencies=[Depends(csrf_header)])
def confirm_payment(body: PaymentConfirmRequest) -> PaymentConfirmResult:
    not_implemented()


@router.get("/me/payments/{payment_id}/receipt")
def get_receipt(
    payment_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="결제 일련번호(문자열)")],
) -> Receipt:
    not_implemented()
