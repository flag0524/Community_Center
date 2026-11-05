# 관리자 환불 검토 라우터. 접수·승인·반려·보류는 AU.RFND_A, 집행·이체 확인은 AU.RFND_X다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.application_types import RefundRequester
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
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-refund"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
STATE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT_STATE,
    ErrorCode.VERSION_CONFLICT,
    ErrorCode.RULE_REJECTED,
    ErrorCode.RFND_LIMIT_EXCEEDED,
)
CREATE_ERRORS = error_responses(
    ErrorCode.RULE_REJECTED, ErrorCode.RFND_LIMIT_EXCEEDED, ErrorCode.IDEMPOTENCY_CONFLICT
)


@router.get("/refunds")
def list_admin_refunds(
    status: RefundStatus | None = None,
    requester: RefundRequester | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminRefundPage:
    """검토가 급한 건(접수·보류, 오래된 순)을 먼저 보인다."""
    not_implemented()


@router.post("/refunds", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_refund(body: AdminRefundCreate, idempotency_key: IdempotencyKey) -> AdminRefund:
    """방문·유선 대리 접수. 승인 시점이 아니라 접수 때도 한도를 사전 검사한다."""
    not_implemented()


@router.get("/refunds/{refund_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_refund(refund_id: Serial) -> AdminRefund:
    not_implemented()


@router.put("/refunds/{refund_id}/hold", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def hold_refund(refund_id: Serial, body: RefundHoldRequest) -> AdminRefund:
    """접수 건을 보류한다. 사유가 필수다."""
    not_implemented()


@router.post("/refunds/{refund_id}/release-hold", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def release_refund_hold(refund_id: Serial, body: RefundVersionRequest) -> AdminRefund:
    not_implemented()


@router.put("/refunds/{refund_id}/approve", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def approve_refund(refund_id: Serial, body: RefundApproveRequest) -> AdminRefund:
    """승인액과 기존 예약액이 원결제액을 넘으면 거절한다. 원결제 행을 잠근 상태에서 확정 검사한다(FN-045)."""
    not_implemented()


@router.put("/refunds/{refund_id}/reject", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def reject_refund(refund_id: Serial, body: RefundRejectRequest) -> AdminRefund:
    not_implemented()


@router.post("/refunds/{refund_id}/execute", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def execute_refund(refund_id: Serial, body: RefundVersionRequest) -> AdminRefund:
    """승인 건의 집행을 요청하거나 실패 건을 재처리한다. 승인한 담당자는 집행할 수 없다(PRD Q22 임시 기준)."""
    not_implemented()


@router.post("/refunds/{refund_id}/confirm-done", responses=STATE_ERRORS, dependencies=[Depends(csrf_header)])
def confirm_refund_done(refund_id: Serial, body: RefundVersionRequest) -> AdminRefund:
    """수동 계좌환불은 담당자가 이체한 뒤 완료를 확인해야 환불완료가 된다."""
    not_implemented()
