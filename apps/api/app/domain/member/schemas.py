# 가입, 본인확인 OTP, 로그인 세션 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, ServerTimed
from app.domain.member.types import OtpPurpose, ResidenceDeclared, ResidenceStatus, TermType, WithdrawalReason

PHONE_PATTERN = r"^01[0-9]{8,9}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class MemberBrief(ApiModel):
    member_id: SerialId
    name: str
    login_id: str


class SessionInfo(ServerTimed):
    authenticated: bool
    csrf_token: str | None = Field(default=None, description="상태 변경 요청의 X-CSRF-Token 헤더에 넣는 값")
    member: MemberBrief | None = None
    idle_timeout_seconds: int | None = Field(default=None, description="유휴 만료 시간. 회원 1800초.")


class LoginRequest(ApiModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class OtpRequest(ApiModel):
    purpose: OtpPurpose
    phone: str = Field(pattern=PHONE_PATTERN)
    name: str | None = Field(default=None, max_length=50)
    login_id: str | None = Field(default=None, max_length=64)


class OtpIssued(ServerTimed):
    """대상 존재 여부를 알려 주지 않도록 모든 목적에서 같은 형태로 응답한다(FN-061)."""

    cert_request_id: SerialId
    expires_at: AwareDatetime
    resend_available_at: AwareDatetime


class OtpVerifyRequest(ApiModel):
    cert_request_id: SerialId
    code: str = Field(pattern=r"^[0-9]{6}$")


class OtpVerifyResult(ApiModel):
    verified: bool
    remaining_attempts: int | None = Field(default=None, ge=0)


class LoginIdCheck(ApiModel):
    available: bool


class AgreementItem(ApiModel):
    term_type: TermType
    version: str = Field(min_length=1, max_length=20)
    agreed: bool


class JoinRequest(ApiModel):
    """가입 요청. 화면의 가입 입력 항목(join-info)을 옮길 때 필드를 맞춘다."""

    cert_request_id: SerialId
    code: str = Field(pattern=r"^[0-9]{6}$")
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=64)
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    agreements: list[AgreementItem] = Field(min_length=1)


class MemberProfile(ApiModel):
    member_id: SerialId
    name: str
    login_id: str
    email: str | None = None
    phone_masked: str | None = None
    joined_on: date
    residence_declared: ResidenceDeclared | None = None
    residence_status: ResidenceStatus


class TermDocument(ApiModel):
    term_type: TermType
    version: str
    title: str
    body: str
    effective_on: date | None = None


class ProfileUpdate(ApiModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    residence_declared: ResidenceDeclared | None = None


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=10, max_length=64)


class FindIdRequest(ApiModel):
    """OTP(목적 ID_FIND)를 확인한 뒤 같은 인증 요청 번호와 코드로 결과를 받는다."""

    cert_request_id: SerialId
    code: str = Field(pattern=r"^[0-9]{6}$")


class FindIdResult(ApiModel):
    masked_login_id: str | None = Field(
        default=None, description="앞 2글자만 보이는 아이디. 일치하는 회원이 없으면 null(FN-061)."
    )


class PasswordResetRequest(ApiModel):
    """OTP(목적 PASSWORD_RESET)를 확인한 뒤 새 비밀번호를 정한다. 성공하면 기존 세션이 모두 끊긴다."""

    cert_request_id: SerialId
    code: str = Field(pattern=r"^[0-9]{6}$")
    login_id: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=10, max_length=64)


class WithdrawalRequest(ApiModel):
    password: str = Field(min_length=1, max_length=64)
    reason: WithdrawalReason | None = None
