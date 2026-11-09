# 본인확인 OTP, 로그인·로그아웃, 세션 조회, 가입 라우터
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.sms.base import SmsSender
from app.auth.deps import (
    SEED_COOKIE_NAMES,
    Clock,
    active_member,
    anonymous_csrf,
    clear_cookie,
    current_session,
    get_bundle_resolver,
    get_clock,
    get_sms_sender,
    request_id_of,
    session_csrf,
    set_cookie,
    verify_csrf,
)
from app.auth.login import member_login
from app.auth.otp import GATE_COOKIE, gate_blocks, issue_otp, make_gate
from app.auth.otp import verify_otp as check_otp
from app.auth.sessions import MEMBER_IDLE_SECONDS, discard
from app.auth.tokens import new_token
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode, not_implemented
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.db.tables import TB_MBR
from app.domain.member.schemas import (
    FindIdRequest,
    FindIdResult,
    JoinRequest,
    LoginIdCheck,
    LoginRequest,
    MemberBrief,
    OtpIssued,
    OtpRequest,
    OtpVerifyRequest,
    OtpVerifyResult,
    PasswordResetRequest,
    SessionInfo,
)
from app.routers.deps import PUBLIC_ERRORS, SESSION_COOKIE_NAME, csrf_header, error_responses

router = APIRouter(tags=["auth"], responses=PUBLIC_ERRORS)

OTP_ERRORS = error_responses(ErrorCode.OTP_INVALID, ErrorCode.OTP_EXPIRED, ErrorCode.OTP_RESEND_TOO_SOON)


@router.post("/auth/otp", responses=OTP_ERRORS, dependencies=[Depends(csrf_header)])
def request_otp(
    body: OtpRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
    clock: Annotated[Clock, Depends(get_clock)],
    sender: Annotated[SmsSender, Depends(get_sms_sender)],
) -> OtpIssued:
    """대상이 있든 없든 같은 모양으로 답한다(FN-061). 재전송은 60초에 한 번이다."""
    now = clock()
    record = current_session(request, "member", db, now)
    verify_csrf(request, settings, "member", record)
    if gate_blocks(settings.secret_key, request.cookies.get(GATE_COOKIE), now):
        raise ApiError(ErrorCode.OTP_RESEND_TOO_SOON)
    issued = issue_otp(
        db,
        settings,
        sender,
        bundle_sn=bundles.resolve(db),
        purpose=body.purpose,
        phone=body.phone,
        name=body.name,
        login_id=body.login_id,
        request_id=request_id_of(request),
        now=now,
    )
    set_cookie(response, settings, GATE_COOKIE, make_gate(settings.secret_key, now))
    return OtpIssued(
        server_now=now.replace(tzinfo=UTC),
        cert_request_id=str(issued.cert_sn),
        expires_at=issued.expires_at.replace(tzinfo=UTC),
        resend_available_at=issued.resend_available_at.replace(tzinfo=UTC),
    )


@router.post("/auth/otp/verify", responses=OTP_ERRORS, dependencies=[Depends(csrf_header)])
def verify_otp(
    body: OtpVerifyRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> OtpVerifyResult:
    """일치 여부만 확인한다. 틀리면 실패 횟수가 늘고 5회가 되면 무효다."""
    now = clock()
    record = current_session(request, "member", db, now)
    verify_csrf(request, settings, "member", record)
    result = check_otp(db, settings, cert_sn=int(body.cert_request_id), code=body.code, now=now)
    return OtpVerifyResult(verified=result.verified, remaining_attempts=result.remaining_attempts)


@router.post(
    "/auth/login",
    responses=error_responses(ErrorCode.LOGIN_FAILED, ErrorCode.LOGIN_LOCKED),
    dependencies=[Depends(csrf_header)],
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> SessionInfo:
    now = clock()
    verify_csrf(request, settings, "member", None)  # 로그인 전이라 시드 쿠키에서 파생한 토큰을 받는다
    done = member_login(
        db,
        settings,
        bundle_sn=bundles.resolve(db),
        login_id=body.login_id,
        password=body.password,
        request_id=request_id_of(request),
        now=now,
    )
    set_cookie(response, settings, SESSION_COOKIE_NAME, done.token)
    clear_cookie(response, settings, SEED_COOKIE_NAMES["member"])
    return SessionInfo(
        server_now=now.replace(tzinfo=UTC),
        authenticated=True,
        csrf_token=session_csrf(settings, done.record),
        member=MemberBrief(member_id=str(done.subject_sn), name=done.name, login_id=done.login_id),
        idle_timeout_seconds=MEMBER_IDLE_SECONDS,
    )


@router.post("/auth/logout", status_code=204, response_class=Response, dependencies=[Depends(csrf_header)])
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    now = clock()
    record = current_session(request, "member", db, now)
    verify_csrf(request, settings, "member", record)
    if record is not None:
        discard(db, record.session_sn, "LOGOUT", now)
    # 세션이 이미 없어도 쿠키는 지워 준다. 로그아웃은 몇 번 불러도 같은 결과(멱등)다.
    out = Response(status_code=204)
    clear_cookie(out, settings, SESSION_COOKIE_NAME)
    return out


@router.get("/auth/session")
def get_session(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> SessionInfo:
    """새로 고침 뒤에도 로그인 여부와 CSRF 토큰을 알 수 있게 한다. 조회만으로 연장하지 않는다."""
    now = clock()
    record = current_session(request, "member", db, now)
    if record is not None and record.member_sn is not None and active_member(db, record.member_sn):
        profile = db.execute(
            select(TB_MBR.c.MBR_NM, TB_MBR.c.LGN_ID).where(TB_MBR.c.MBR_SN == record.member_sn)
        ).one()
        return SessionInfo(
            server_now=now.replace(tzinfo=UTC),
            authenticated=True,
            csrf_token=session_csrf(settings, record),
            member=MemberBrief(
                member_id=str(record.member_sn), name=str(profile.MBR_NM), login_id=str(profile.LGN_ID)
            ),
            idle_timeout_seconds=MEMBER_IDLE_SECONDS,
        )
    # 로그인 전에도 로그인 요청이 쓸 CSRF 토큰이 필요하다. 시드는 이 브라우저에만 있는 무작위 값이다.
    seed = request.cookies.get(SEED_COOKIE_NAMES["member"]) or new_token()
    set_cookie(response, settings, SEED_COOKIE_NAMES["member"], seed)
    return SessionInfo(
        server_now=now.replace(tzinfo=UTC), authenticated=False, csrf_token=anonymous_csrf(settings, seed)
    )


@router.get("/join/check-id")
def check_login_id(
    login_id: Annotated[str, Query(alias="loginId", min_length=1, max_length=64)],
    db: Annotated[Session, Depends(get_db)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
) -> LoginIdCheck:
    taken = db.execute(
        select(TB_MBR.c.MBR_SN).where(
            TB_MBR.c.OPER_BNDL_SN == bundles.resolve(db), TB_MBR.c.LGN_ID == login_id
        )
    ).first()
    return LoginIdCheck(available=taken is None)


@router.post(
    "/join",
    status_code=201,
    responses={
        **OTP_ERRORS,
        **error_responses(ErrorCode.JOIN_LOGIN_ID_TAKEN),
    },
    dependencies=[Depends(csrf_header)],
)
def join(body: JoinRequest) -> MemberBrief:
    not_implemented()


@router.post("/auth/find-id", responses=OTP_ERRORS, dependencies=[Depends(csrf_header)])
def find_id(body: FindIdRequest) -> FindIdResult:
    not_implemented()


@router.post(
    "/auth/password-reset",
    status_code=204,
    response_class=Response,
    responses=OTP_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def reset_password(body: PasswordResetRequest) -> None:
    not_implemented()
