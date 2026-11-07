# 관리자 감면 사전심사 라우터. 조회 AU.APLY_R, 심사 후보 AU.APLY_W(PRD Q21). 재심사는 새 건이다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.reduction_schemas import (
    ReductionDecisionRequest,
    ReductionHistoryPage,
    ReductionReview,
    ReductionReviewPage,
)
from app.domain.admin.reduction_types import ReductionDecision, ReductionStatus
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-reduction"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
DECIDE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED
)


@router.get("/reductions")
def list_reductions(
    status: ReductionStatus | None = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReductionReviewPage:
    """접수된 심사가 먼저, 오래된 신청부터 나온다."""
    not_implemented()


@router.get("/reductions/{review_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_reduction(review_id: Serial) -> ReductionReview:
    not_implemented()


@router.post("/reductions/{review_id}/decision", responses=DECIDE_ERRORS, dependencies=[Depends(csrf_header)])
def decide_reduction(review_id: Serial, body: ReductionDecisionRequest) -> ReductionReview:
    """승인·반려. 조리읍 거주가 확인되지 않은 회원은 승인할 수 없다."""
    not_implemented()


@router.post(
    "/reductions/{review_id}/re-review",
    status_code=201,
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.IDEMPOTENCY_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def re_review_reduction(review_id: Serial, idempotency_key: IdempotencyKey) -> ReductionReview:
    """이전 심사는 그대로 두고 같은 회원·기수의 새 심사건을 접수 상태로 만든다."""
    not_implemented()


@router.get("/reduction-history")
def list_reduction_history(
    result: ReductionDecision | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReductionHistoryPage:
    """신청에 적용된 판정 이력. 판정마다 새 행이 쌓이고 고치지 않는다(FN-038)."""
    not_implemented()
