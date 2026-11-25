# 관리자 권한 배정 라우터. 모두 AU.GRANT_W이고 수정 없이 새로 배정하거나 회수한다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.core.schema import MAX_PAGE
from app.db.session import get_db
from app.domain.admin import role_service as service
from app.domain.admin.role_schemas import (
    AssignmentCreate,
    AssignmentOptions,
    AssignmentRevoke,
    RoleAssignment,
    RoleAssignmentPage,
)
from app.domain.admin.role_types import AssignmentStatus
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-role"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
CREATE_ERRORS = error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)
REVOKE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED
)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/role-assignment-options")
def get_assignment_options(db: Db, admin: Me, clock: Now) -> AssignmentOptions:
    """위임할 수 있는 역할만 준다. 내 유효 배정의 권한·범위·기간 안에 드는 것이다."""
    return service.get_options(db, admin, now=clock())


@router.get("/role-assignments")
def list_role_assignments(
    db: Db,
    admin: Me,
    clock: Now,
    status: AssignmentStatus | None = None,
    q: Annotated[str | None, Query(max_length=100, description="관리자 이름")] = None,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RoleAssignmentPage:
    """내 범위 안의 배정만 나온다. 시스템 관리자는 업무 본문을 보지 못하므로 업무 범위 배정은 요약만 본다."""
    return service.list_assignments(db, admin, now=clock(), status=status, q=q, page=page, size=size)


@router.get("/role-assignments/{assignment_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_role_assignment(assignment_id: Serial, db: Db, admin: Me, clock: Now) -> RoleAssignment:
    return service.get_assignment(db, admin, now=clock(), assignment_id=assignment_id)


@router.post(
    "/role-assignments", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)]
)
def create_role_assignment(
    body: AssignmentCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> RoleAssignment:
    """자기 자신에게는 줄 수 없고 내가 가진 권한·범위·기간을 넘는 배정은 거절한다."""
    return service.create_assignment(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        body=body,
        idem_key=idempotency_key,
    )


@router.post(
    "/role-assignments/{assignment_id}/revoke", responses=REVOKE_ERRORS, dependencies=[Depends(csrf_header)]
)
def revoke_role_assignment(
    assignment_id: Serial, body: AssignmentRevoke, request: Request, db: Db, admin: Me, clock: Now
) -> RoleAssignment:
    """배정을 지우지 않고 사용 중지로 바꾼다. 자기 배정은 회수할 수 없다."""
    return service.revoke_assignment(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        assignment_id=assignment_id,
        body=body,
    )
