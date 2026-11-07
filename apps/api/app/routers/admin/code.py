# 관리자 공통 코드 라우터. 표시명·순서·사용 여부만 고치고 코드를 추가하거나 지우지 않는다(PRD Q21 후보 권한)
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.setting_schemas import CodeGroupList, CodeList, CodeUpdate
from app.routers.deps import MEMBER_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-code"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])


@router.get("/code-groups")
def list_code_groups() -> CodeGroupList:
    not_implemented()


@router.get("/codes", responses=error_responses(ErrorCode.NOT_FOUND))
def list_codes(
    group: Annotated[str, Query(max_length=20, description="코드 그룹")],
    q: Annotated[str | None, Query(max_length=100, description="코드·표시명")] = None,
    use: Annotated[bool | None, Query(description="사용 여부")] = None,
) -> CodeList:
    not_implemented()


@router.put(
    "/codes",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED),
    dependencies=[Depends(csrf_header)],
)
def update_codes(body: CodeUpdate) -> CodeList:
    """한 번에 저장한다. 하나라도 거절되면 모두 저장하지 않는다."""
    not_implemented()
