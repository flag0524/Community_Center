# 관리자 결제·거래 대조 라우터. 조회는 AU.STLM_R, 재조회와 수동 대사는 AU.STLM_W다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.transaction_schemas import ReconcileRequest, Transaction, TransactionPage
from app.domain.payment.types import PaymentMethod, PaymentStatus
from app.routers.deps import CSV_RESPONSE, MEMBER_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(
    tags=["admin-transaction"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT)


@router.get("/transactions")
def list_transactions(
    q: Annotated[str | None, Query(max_length=100, description="주문번호 또는 신청번호")] = None,
    status: PaymentStatus | None = None,
    method: PaymentMethod | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    conflict_only: Annotated[
        bool, Query(alias="conflictOnly", description="충돌 통보가 있는 거래만")
    ] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TransactionPage:
    """결과 확인 중인 거래를 먼저 보이고 그 안에서는 최근 요청이 앞이다."""
    not_implemented()


@router.get(
    "/transactions/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_transactions_csv(
    q: Annotated[str | None, Query(max_length=100, description="주문번호 또는 신청번호")] = None,
    status: PaymentStatus | None = None,
    method: PaymentMethod | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    conflict_only: Annotated[bool, Query(alias="conflictOnly")] = False,
) -> Response:
    """목록과 같은 조건·권한으로 만든다. 확인 중인 금액은 순수납에 넣지 않고 상태 열로 구분한다."""
    not_implemented()


@router.get("/transactions/{transaction_id}", responses=NOT_FOUND)
def get_transaction(transaction_id: Serial) -> Transaction:
    not_implemented()


@router.post(
    "/transactions/{transaction_id}/recheck", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def recheck_transaction(transaction_id: Serial) -> Transaction:
    """PG에 결과를 다시 묻는다. 결과 확인 중인 거래에만 하고 결과가 불명이면 그대로 둔다."""
    not_implemented()


@router.post(
    "/transactions/{transaction_id}/manual-reconcile",
    responses=error_responses(
        ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED
    ),
    dependencies=[Depends(csrf_header)],
)
def reconcile_transaction(transaction_id: Serial, body: ReconcileRequest) -> Transaction:
    """결과 확인 중인 거래에만 한다. 근거는 필수이고 성공이면 승인번호도 필수다(FN-042)."""
    not_implemented()
