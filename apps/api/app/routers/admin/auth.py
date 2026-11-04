# 관리자 로그인·로그아웃·세션 조회·세션 연장 라우터
from fastapi import APIRouter, Depends, Response

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.schemas import AdminLoginRequest, AdminSession
from app.routers.deps import MEMBER_ERRORS, PUBLIC_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-auth"], responses=PUBLIC_ERRORS)


@router.post(
    "/auth/login",
    responses=error_responses(ErrorCode.LOGIN_FAILED, ErrorCode.LOGIN_LOCKED),
    dependencies=[Depends(csrf_header)],
)
def admin_login(body: AdminLoginRequest) -> AdminSession:
    """아이디·비밀번호만 받는다. MFA는 범위에서 뺐다. 실패 제한 수치는 관리자 정책 확정이 필요하다(Q28)."""
    not_implemented()


@router.post(
    "/auth/logout",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(admin_session), Depends(csrf_header)],
)
def admin_logout() -> None:
    not_implemented()


@router.get("/auth/session")
def get_admin_session() -> AdminSession:
    """새로 고침 뒤에도 로그인 여부·CSRF 토큰·만료 시각을 알 수 있게 한다. 조회만으로는 연장하지 않는다."""
    not_implemented()


@router.post(
    "/auth/extend",
    responses=MEMBER_ERRORS,
    dependencies=[Depends(admin_session), Depends(csrf_header)],
)
def extend_admin_session() -> AdminSession:
    """만료 2분 전 안내에서 '계속 사용'을 누르면 유휴 시간을 처음부터 다시 센다(RQ-SER-NF-008)."""
    not_implemented()
