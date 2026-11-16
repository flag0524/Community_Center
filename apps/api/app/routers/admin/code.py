# 관리자 공통 코드 라우터. 표시명·순서·사용 여부만 고치고 코드를 추가하거나 지우지 않는다(PRD Q21 후보 권한)
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import setting_service as service
from app.domain.admin.setting_schemas import CodeGroupList, CodeList, CodeUpdate
from app.routers.deps import MEMBER_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-code"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/code-groups")
def list_code_groups(db: Db, admin: Me, clock: Now) -> CodeGroupList:
    return service.list_groups(db, admin, now=clock())


@router.get("/codes", responses=error_responses(ErrorCode.NOT_FOUND))
def list_codes(
    db: Db,
    admin: Me,
    clock: Now,
    group: Annotated[str, Query(max_length=20, description="코드 그룹")],
    q: Annotated[str | None, Query(max_length=100, description="코드·표시명")] = None,
    use: Annotated[bool | None, Query(description="사용 여부")] = None,
) -> CodeList:
    return service.list_codes(db, admin, now=clock(), group=group, q=q, use=use)


@router.put(
    "/codes",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED),
    dependencies=[Depends(csrf_header)],
)
def update_codes(body: CodeUpdate, request: Request, db: Db, admin: Me, clock: Now) -> CodeList:
    """한 번에 저장한다. 하나라도 거절되면 모두 저장하지 않는다."""
    return service.update_codes(db, admin, now=clock(), request_id=request_id_of(request), body=body)
