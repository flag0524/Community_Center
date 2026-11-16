# 로그인한 관리자의 권한과 메뉴를 돌려주는 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock
from app.db.session import get_db
from app.domain.admin import permission_service as service
from app.domain.admin.schemas import AdminPermissions
from app.routers.deps import MEMBER_ERRORS, admin_session

router = APIRouter(tags=["admin-me"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])


@router.get("/me/permissions")
def get_my_permissions(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[Admin, Depends(require_admin)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AdminPermissions:
    """메뉴 노출용이다. 서버는 이 응답과 무관하게 모든 요청을 대상 레코드 기준으로 다시 판정한다(C06)."""
    return service.get_permissions(db, admin, now=clock())
