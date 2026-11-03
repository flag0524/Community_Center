# 로그인한 회원 본인 정보 라우터. 경로의 회원 번호 대신 세션의 회원만 쓴다.
from fastapi import APIRouter, Depends, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.member.schemas import MemberProfile, PasswordChange, ProfileUpdate, WithdrawalRequest
from app.routers.deps import MEMBER_ERRORS, csrf_header, error_responses, member_session

router = APIRouter(tags=["me"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])


@router.get("/me/profile")
def get_my_profile() -> MemberProfile:
    not_implemented()


@router.put("/me/profile", dependencies=[Depends(csrf_header)])
def update_my_profile(body: ProfileUpdate) -> MemberProfile:
    """이메일과 본인 입력 거주지역만 고칠 수 있다. 센터 확인 거주구분과 확인 상태는 바꿀 수 없다."""
    not_implemented()


@router.put("/me/password", status_code=204, response_class=Response, dependencies=[Depends(csrf_header)])
def change_my_password(body: PasswordChange) -> None:
    """현재 비밀번호가 틀리면 400(fields.currentPassword). 성공하면 이 세션을 빼고 다른 세션은 끊는다."""
    not_implemented()


@router.post(
    "/me/withdraw",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.RULE_REJECTED),
    dependencies=[Depends(csrf_header)],
)
def withdraw(body: WithdrawalRequest) -> None:
    """진행 중인 신청·결제·환불이 있으면 422(RULE_REJECTED). 성공하면 세션을 끊고 30일 뒤 파기한다."""
    not_implemented()
