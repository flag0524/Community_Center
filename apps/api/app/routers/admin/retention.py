# 관리자 보존·파기 검토 라우터. 조회 AU.LOG_R, 실행(되돌릴 수 없음)은 아직 구현하지 않는다(ADR-074)
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock
from app.core.errors import ErrorCode, not_implemented
from app.db.session import get_db
from app.domain.admin import retention_service as service
from app.domain.admin.retention_schemas import RetentionDetail, RetentionExecute, RetentionList
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-retention"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/retention")
def list_retention(db: Db, admin: Me, clock: Now) -> RetentionList:
    """파기 예정 자료와 건수. 정산자료는 법정 보존 대상이라 제외하고 이유를 함께 준다."""
    return service.list_retention(db, admin, now=clock())


@router.get("/retention/{item_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_retention(item_id: Serial, db: Db, admin: Me, clock: Now) -> RetentionDetail:
    return service.get_retention(db, admin, now=clock(), item_id=item_id)


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
