# 환불 미리보기, 환불 접수, 환불 내역 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.deps import Clock, Member, get_clock, request_id_of, require_member, require_member_write
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.refund import service
from app.domain.refund.schemas import Refund, RefundCreate, RefundPage, RefundPreview
from app.routers.deps import (
    MEMBER_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

router = APIRouter(tags=["refunds"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get(
    "/me/applications/{application_id}/refund-preview",
    responses=error_responses(ErrorCode.RFND_NOT_ALLOWED),
)
def get_refund_preview(
    application_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="신청 일련번호(문자열)")],
    db: Db,
    me: Me,
    clock: Now,
) -> RefundPreview:
    """서버가 산정한 반환 기준액과 근거를 보여 준다. TDD 10.2에 없던 엔드포인트라 spec에 반영한다."""
    return service.preview(
        db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, application_id=application_id, now=clock()
    )


@router.post(
    "/me/refunds",
    status_code=201,
    responses=error_responses(
        ErrorCode.RFND_NOT_ALLOWED, ErrorCode.RFND_LIMIT_EXCEEDED, ErrorCode.IDEMPOTENCY_CONFLICT
    ),
    dependencies=[Depends(csrf_header)],
)
def create_refund(
    body: RefundCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Now,
) -> Refund:
    return service.create_refund(
        db,
        settings,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        application_id=body.application_id,
        reason=body.reason,
        account=(
            (body.bank_code, body.account_holder, body.account_number)
            if body.bank_code is not None
            and body.account_holder is not None
            and body.account_number is not None
            else None
        ),
        idem_key=idempotency_key,
        request_id=request_id_of(request),
        now=clock(),
    )


@router.get("/me/refunds")
def list_my_refunds(
    db: Db,
    me: Me,
    clock: Now,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> RefundPage:
    return service.list_mine(
        db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, now=clock(), page=page, size=size
    )
