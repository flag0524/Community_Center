# 관리자 로그인·로그아웃·세션 조회·세션 연장 라우터
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (
    SEED_COOKIE_NAMES,
    Clock,
    active_admin,
    anonymous_csrf,
    clear_cookie,
    current_session,
    get_clock,
    get_settings,
    request_id_of,
    session_csrf,
    set_cookie,
    verify_csrf,
)
from app.auth.login import admin_login as authenticate_admin
from app.auth.sessions import ADMIN_IDLE_SECONDS, discard, touch
from app.auth.tokens import new_token
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.session import get_db
from app.db.tables import TB_MNGR
from app.domain.admin.schemas import AdminBrief, AdminLoginRequest, AdminSession
from app.routers.deps import (
    ADMIN_SESSION_COOKIE_NAME,
    MEMBER_ERRORS,
    PUBLIC_ERRORS,
    admin_session,
    csrf_header,
    error_responses,
)

router = APIRouter(tags=["admin-auth"], responses=PUBLIC_ERRORS)


@router.post(
    "/auth/login",
    responses=error_responses(ErrorCode.LOGIN_FAILED, ErrorCode.LOGIN_LOCKED),
    dependencies=[Depends(csrf_header)],
)
def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AdminSession:
    """아이디·비밀번호만 받는다. MFA는 범위에서 뺐다. 실패 제한 수치는 관리자 정책 확정이 필요하다(Q28)."""
    now = clock()
    verify_csrf(request, settings, "admin", None)
    done = authenticate_admin(
        db,
        settings,
        login_id=body.login_id,
        password=body.password,
        request_id=request_id_of(request),
        now=now,
    )
    set_cookie(response, settings, ADMIN_SESSION_COOKIE_NAME, done.token)
    clear_cookie(response, settings, SEED_COOKIE_NAMES["admin"])
    return AdminSession(
        server_now=now.replace(tzinfo=UTC),
        authenticated=True,
        csrf_token=session_csrf(settings, done.record),
        admin=AdminBrief(admin_id=str(done.subject_sn), name=done.name, login_id=done.login_id),
        idle_timeout_seconds=ADMIN_IDLE_SECONDS,
        expires_at=done.record.expires_at.replace(tzinfo=UTC),
    )


@router.post(
    "/auth/logout",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(admin_session), Depends(csrf_header)],
)
def admin_logout(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    now = clock()
    record = current_session(request, "admin", db, now)
    verify_csrf(request, settings, "admin", record)
    if record is not None:
        discard(db, record.session_sn, "LOGOUT", now)
    out = Response(status_code=204)
    clear_cookie(out, settings, ADMIN_SESSION_COOKIE_NAME)
    return out


@router.get("/auth/session")
def get_admin_session(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AdminSession:
    """새로 고침 뒤에도 로그인 여부·CSRF 토큰·만료 시각을 알 수 있게 한다. 조회만으로는 연장하지 않는다."""
    now = clock()
    record = current_session(request, "admin", db, now)
    if record is not None and record.admin_sn is not None and active_admin(db, record.admin_sn):
        profile = db.execute(
            select(TB_MNGR.c.MNGR_NM, TB_MNGR.c.LGN_ID).where(TB_MNGR.c.MNGR_SN == record.admin_sn)
        ).one()
        return AdminSession(
            server_now=now.replace(tzinfo=UTC),
            authenticated=True,
            csrf_token=session_csrf(settings, record),
            admin=AdminBrief(
                admin_id=str(record.admin_sn), name=str(profile.MNGR_NM), login_id=str(profile.LGN_ID)
            ),
            idle_timeout_seconds=ADMIN_IDLE_SECONDS,
            expires_at=record.expires_at.replace(tzinfo=UTC),
        )
    seed = request.cookies.get(SEED_COOKIE_NAMES["admin"]) or new_token()
    set_cookie(response, settings, SEED_COOKIE_NAMES["admin"], seed)
    return AdminSession(
        server_now=now.replace(tzinfo=UTC), authenticated=False, csrf_token=anonymous_csrf(settings, seed)
    )


@router.post(
    "/auth/extend",
    responses=MEMBER_ERRORS,
    dependencies=[Depends(admin_session), Depends(csrf_header)],
)
def extend_admin_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AdminSession:
    """만료 2분 전 안내에서 '계속 사용'을 누르면 유휴 시간을 처음부터 다시 센다(RQ-SER-NF-008)."""
    now = clock()
    record = current_session(request, "admin", db, now)
    if record is None or record.admin_sn is None or not active_admin(db, record.admin_sn):
        raise ApiError(ErrorCode.UNAUTHENTICATED)
    verify_csrf(request, settings, "admin", record)
    record = touch(db, record, "admin", now)
    profile = db.execute(
        select(TB_MNGR.c.MNGR_NM, TB_MNGR.c.LGN_ID).where(TB_MNGR.c.MNGR_SN == record.admin_sn)
    ).one()
    return AdminSession(
        server_now=now.replace(tzinfo=UTC),
        authenticated=True,
        csrf_token=session_csrf(settings, record),
        admin=AdminBrief(
            admin_id=str(record.admin_sn), name=str(profile.MNGR_NM), login_id=str(profile.LGN_ID)
        ),
        idle_timeout_seconds=ADMIN_IDLE_SECONDS,
        expires_at=record.expires_at.replace(tzinfo=UTC),
    )
