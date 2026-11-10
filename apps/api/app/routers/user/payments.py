# 결제 요청, 승인 확인, 영수증 라우터. PG 웹훅은 별도 경로(/api/pg/webhook)로 추가한다.
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Security
from sqlalchemy.orm import Session

from app.adapters.pg.base import PaymentGateway
from app.auth.deps import (
    Clock,
    Member,
    get_clock,
    get_payment_gateway,
    request_id_of,
    require_member,
    require_member_write,
)
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.payment import service
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

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]
Gateway = Annotated[PaymentGateway, Depends(get_payment_gateway)]

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
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Config,
    gateway: Gateway,
    clock: Now,
) -> PaymentRequestResult:
    return service.request_payment(
        db,
        settings,
        gateway,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        application_id=application_id,
        method=body.method,
        idem_key=idempotency_key,
        request_id=request_id_of(request),
        now=clock(),
    )


@router.post("/payments/confirm", responses=PAY_ERRORS, dependencies=[Depends(csrf_header)])
def confirm_payment(
    body: PaymentConfirmRequest,
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Config,
    gateway: Gateway,
    clock: Now,
) -> PaymentConfirmResult:
    return service.confirm_payment(
        db,
        settings,
        gateway,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        body=body,
        request_id=request_id_of(request),
        clock=clock,
    )


@router.get("/me/payments/{payment_id}/receipt")
def get_receipt(
    payment_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="결제 일련번호(문자열)")],
    db: Db,
    me: Me,
) -> Receipt:
    return service.get_receipt(db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, payment_id=payment_id)
