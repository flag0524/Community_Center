# 관리자 환불 검토 라우터. 접수·승인·반려·보류는 AU.RFND_A, 집행·이체 확인은 AU.RFND_X다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.adapters.pg.base import PaymentGateway
from app.auth.admin_access import Admin, require_admin, require_admin_write
from app.auth.deps import Clock, get_clock, get_payment_gateway, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import refund_service as service
from app.domain.admin.application_types import RefundRequester
from app.domain.admin.csv_export import csv_response
from app.domain.admin.refund_schemas import (
    AdminRefund,
    AdminRefundCreate,
    AdminRefundPage,
    RefundApproveRequest,
    RefundHoldRequest,
    RefundRejectRequest,
    RefundVersionRequest,
)
from app.domain.refund.types import RefundStatus
from app.routers.deps import (
    CSV_RESPONSE,
    MEMBER_ERRORS,
    IdempotencyKey,
    admin_session,
    csrf_header,
    error_responses,
)

router = APIRouter(tags=["admin-refund"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
MeWrite = Annotated[Admin, Depends(require_admin_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]
STATE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT_STATE,
    ErrorCode.VERSION_CONFLICT,
    ErrorCode.RULE_REJECTED,
    ErrorCode.RFND_LIMIT_EXCEEDED,
)
CREATE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.RULE_REJECTED,
    ErrorCode.RFND_LIMIT_EXCEEDED,
    ErrorCode.IDEMPOTENCY_CONFLICT,
)


@router.get("/refunds")
def list_admin_refunds(
    db: Db,
    admin: Me,
    clock: Now,
    status: RefundStatus | None = None,
    requester: RefundRequester | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminRefundPage:
    """검토가 급한 건(접수·보류, 오래된 순)을 먼저 보인다. 담당 범위의 강좌에 걸린 환불만 보인다."""
    return service.list_refunds(
        db,
        admin,
        now=clock(),
        status=status,
        requester=requester,
        from_date=from_date,
        to_date=to_date,
        page=page,
        size=size,
    )


@router.post("/refunds", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_refund(
    body: AdminRefundCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    """방문·유선 대리 접수. 승인 시점이 아니라 접수 때도 한도를 사전 검사한다."""
    return service.create_by_admin(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        body=body,
        idem_key=idempotency_key,
    )


@router.get(
    "/refunds/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_refunds_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    status: RefundStatus | None = None,
    requester: RefundRequester | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    """목록과 같은 조건·권한으로 만든다. 환불 계좌 같은 민감 값은 담지 않는다."""
    content = service.export_csv(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        status=status,
        requester=requester,
        from_date=from_date,
        to_date=to_date,
    )
    return csv_response("refunds.csv", content)


@router.get("/refunds/{refund_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_refund(refund_id: Serial, db: Db, admin: Me, settings: Config, clock: Now) -> AdminRefund:
    return service.get_refund(db, settings, admin, now=clock(), refund_id=refund_id)


@router.put("/refunds/{refund_id}/hold", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def hold_refund(
    refund_id: Serial,
    body: RefundHoldRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    """접수 건을 보류한다. 사유가 필수다."""
    return service.hold(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        refund_id=refund_id,
        reason=body.reason,
        version=body.version,
    )


@router.post("/refunds/{refund_id}/release-hold", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def release_refund_hold(
    refund_id: Serial,
    body: RefundVersionRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    return service.release_hold(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        refund_id=refund_id,
        version=body.version,
    )


@router.put("/refunds/{refund_id}/approve", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def approve_refund(
    refund_id: Serial,
    body: RefundApproveRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    """승인액과 기존 예약액이 승인 시점의 반환 기준액을 넘으면 거절한다. 결제 행을 잠그고 검사한다."""
    return service.approve(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        refund_id=refund_id,
        amount=body.amount,
        version=body.version,
    )


@router.put("/refunds/{refund_id}/reject", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def reject_refund(
    refund_id: Serial,
    body: RefundRejectRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    return service.reject(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        refund_id=refund_id,
        reason=body.reason,
        version=body.version,
    )


@router.post("/refunds/{refund_id}/execute", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def execute_refund(
    refund_id: Serial,
    body: RefundVersionRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    clock: Now,
) -> AdminRefund:
    """승인 건의 집행을 요청하거나 실패 건을 재처리한다. 승인한 담당자는 집행할 수 없다(PRD Q22 임시 기준)."""
    return service.execute(
        db,
        settings,
        admin,
        gateway,
        clock=clock,
        request_id=request_id_of(request),
        refund_id=refund_id,
        version=body.version,
    )


@router.post("/refunds/{refund_id}/confirm-done", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def confirm_refund_done(
    refund_id: Serial,
    body: RefundVersionRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminRefund:
    """수동 계좌환불은 담당자가 이체한 뒤 완료를 확인해야 환불완료가 된다."""
    return service.confirm_done(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        refund_id=refund_id,
        version=body.version,
    )
