# 환불 미리보기, 환불 접수, 환불 내역 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.refund.schemas import Refund, RefundCreate, RefundPage, RefundPreview
from app.routers.deps import (
    MEMBER_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

router = APIRouter(tags=["refunds"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])


@router.get(
    "/me/applications/{application_id}/refund-preview",
    responses=error_responses(ErrorCode.RFND_NOT_ALLOWED),
)
def get_refund_preview(
    application_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="신청 일련번호(문자열)")],
) -> RefundPreview:
    """서버가 산정한 반환 기준액과 근거를 보여 준다. TDD 10.2에 없던 엔드포인트라 spec에 반영한다."""
    not_implemented()


@router.post(
    "/me/refunds",
    status_code=201,
    responses=error_responses(
        ErrorCode.RFND_NOT_ALLOWED, ErrorCode.RFND_LIMIT_EXCEEDED, ErrorCode.IDEMPOTENCY_CONFLICT
    ),
    dependencies=[Depends(csrf_header)],
)
def create_refund(body: RefundCreate, idempotency_key: IdempotencyKey) -> Refund:
    not_implemented()


@router.get("/me/refunds")
def list_my_refunds(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> RefundPage:
    not_implemented()
