# 관리자 보존·파기 검토 라우터. 조회 AU.LOG_R, 실행 후보 AU.GRANT_W(PRD Q21)이며 실행은 되돌릴 수 없다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.retention_schemas import RetentionDetail, RetentionExecute, RetentionList
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-retention"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]


@router.get("/retention")
def list_retention() -> RetentionList:
    """파기 예정 자료와 건수. 정산자료는 법정 보존 대상이라 제외하고 이유를 함께 준다."""
    not_implemented()


@router.get("/retention/{item_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_retention(item_id: Serial) -> RetentionDetail:
    not_implemented()


@router.post(
    "/retention/{item_id}/execute",
    responses=error_responses(
        ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT
    ),
    dependencies=[Depends(csrf_header)],
)
def execute_retention(
    item_id: Serial, body: RetentionExecute, idempotency_key: IdempotencyKey
) -> RetentionDetail:
    """대상을 다시 세어 확인한 건수와 같을 때만 파기·비식별 처리하고 실행 결과를 감사기록에 남긴다."""
    not_implemented()
