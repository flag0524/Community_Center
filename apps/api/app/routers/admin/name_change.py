# 관리자 이름 변경 요청 검토 라우터. 목록·승인·반려는 AU.GRANT_W 묶음 전체 범위(임시 매핑, ADR-090)
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.member import name_change_service as service
from app.domain.member.name_change_schemas import (
    AdminNameChange,
    AdminNameChangeList,
    NameChangeDecide,
    NameChangeFilter,
)
from app.routers.deps import MEMBER_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(
    tags=["admin-name-change"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/name-change-requests")
def list_name_changes(
    db: Db,
    settings: Config,
    admin: Me,
    clock: Now,
    state: NameChangeFilter = NameChangeFilter.PENDING,
) -> AdminNameChangeList:
    """검토 중이면 오래된 것부터, 처리한 요청이면 최근 것부터 100건까지 준다. 현재 이름은 가려서 준다."""
    return service.list_requests(db, settings, admin, now=clock(), state=state)


@router.post(
    "/name-change-requests/{name_change_id}/approve",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def approve_name_change(
    name_change_id: Serial,
    body: NameChangeDecide,
    request: Request,
    db: Db,
    settings: Config,
    admin: Me,
    clock: Now,
) -> AdminNameChange:
    """검토 중인 요청을 승인하고 회원 이름을 바꾼다. 정상 회원의 요청만 승인할 수 있다."""
    return service.decide(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        name_change_id=name_change_id,
        body=body,
        approve=True,
    )


@router.post(
    "/name-change-requests/{name_change_id}/reject",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def reject_name_change(
    name_change_id: Serial,
    body: NameChangeDecide,
    request: Request,
    db: Db,
    settings: Config,
    admin: Me,
    clock: Now,
) -> AdminNameChange:
    return service.decide(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        name_change_id=name_change_id,
        body=body,
        approve=False,
    )
