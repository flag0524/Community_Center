# 본인확인 OTP, 로그인·로그아웃, 세션 조회, 가입 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.errors import ErrorCode, not_implemented
from app.domain.member.schemas import (
    JoinRequest,
    LoginIdCheck,
    LoginRequest,
    MemberBrief,
    OtpIssued,
    OtpRequest,
    OtpVerifyRequest,
    OtpVerifyResult,
    SessionInfo,
)
from app.routers.deps import PUBLIC_ERRORS, csrf_header, error_responses

router = APIRouter(tags=["auth"], responses=PUBLIC_ERRORS)

OTP_ERRORS = error_responses(ErrorCode.OTP_INVALID, ErrorCode.OTP_EXPIRED, ErrorCode.OTP_RESEND_TOO_SOON)


@router.post("/auth/otp", responses=OTP_ERRORS, dependencies=[Depends(csrf_header)])
def request_otp(body: OtpRequest) -> OtpIssued:
    not_implemented()


@router.post("/auth/otp/verify", responses=OTP_ERRORS, dependencies=[Depends(csrf_header)])
def verify_otp(body: OtpVerifyRequest) -> OtpVerifyResult:
    not_implemented()


@router.post(
    "/auth/login",
    responses=error_responses(ErrorCode.LOGIN_FAILED, ErrorCode.LOGIN_LOCKED),
    dependencies=[Depends(csrf_header)],
)
def login(body: LoginRequest) -> SessionInfo:
    not_implemented()


@router.post("/auth/logout", status_code=204, response_class=Response, dependencies=[Depends(csrf_header)])
def logout() -> None:
    not_implemented()


@router.get("/auth/session")
def get_session() -> SessionInfo:
    """새로 고침 뒤에도 로그인 여부와 CSRF 토큰을 알 수 있게 한다. 로그인하지 않았으면 authenticated=false."""
    not_implemented()


@router.get("/join/check-id")
def check_login_id(
    login_id: Annotated[str, Query(alias="loginId", min_length=1, max_length=64)],
) -> LoginIdCheck:
    not_implemented()


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
