# 로그인한 관리자의 권한과 메뉴를 돌려주는 라우터
from fastapi import APIRouter, Depends

from app.core.errors import not_implemented
from app.domain.admin.schemas import AdminPermissions
from app.routers.deps import MEMBER_ERRORS, admin_session

router = APIRouter(tags=["admin-me"], responses=MEMBER_ERRORS, dependencies=[Depends(admin_session)])


@router.get("/me/permissions")
def get_my_permissions() -> AdminPermissions:
    """메뉴 노출용이다. 서버는 이 응답과 무관하게 모든 요청을 대상 레코드 기준으로 다시 판정한다(C06)."""
    not_implemented()
