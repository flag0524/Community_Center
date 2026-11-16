# 로그인한 회원 본인 정보 라우터. 경로의 회원 번호 대신 세션의 회원만 쓴다.
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.deps import (
    Clock,
    Member,
    clear_cookie,
    get_clock,
    request_id_of,
    require_member,
    require_member_write,
)
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.member import profile_service as service
from app.domain.member.schemas import MemberProfile, PasswordChange, ProfileUpdate, WithdrawalRequest
from app.routers.deps import MEMBER_ERRORS, SESSION_COOKIE_NAME, csrf_header, error_responses, member_session

router = APIRouter(tags=["me"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/me/profile")
def get_my_profile(db: Db, me: Me) -> MemberProfile:
    return service.get_profile(db, me)


@router.put("/me/profile", dependencies=[Depends(csrf_header)])
def update_my_profile(
    body: ProfileUpdate, request: Request, db: Db, me: MeWrite, clock: Now
) -> MemberProfile:
    """이메일과 본인 입력 거주지역만 고칠 수 있다. 센터 확인 거주구분과 확인 상태는 바꿀 수 없다."""
    return service.update_profile(db, me, body, request_id=request_id_of(request), now=clock())


@router.put("/me/password", status_code=204, response_class=Response, dependencies=[Depends(csrf_header)])
def change_my_password(
    body: PasswordChange, request: Request, db: Db, settings: Config, me: MeWrite, clock: Now
) -> None:
    """현재 비밀번호가 틀리면 400(fields.currentPassword). 성공하면 이 세션을 빼고 다른 세션은 끊는다."""
    service.change_password(db, settings, me, body, request_id=request_id_of(request), now=clock())


@router.post(
    "/me/withdraw",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.RULE_REJECTED),
    dependencies=[Depends(csrf_header)],
)
def withdraw(
    body: WithdrawalRequest, request: Request, db: Db, settings: Config, me: MeWrite, clock: Now
) -> Response:
    """진행 중인 신청·결제·환불이 있으면 422(RULE_REJECTED). 성공하면 세션을 끊고 30일 뒤 파기한다."""
    service.withdraw(db, me, body, request_id=request_id_of(request), now=clock())
    out = Response(status_code=204)
    clear_cookie(out, settings, SESSION_COOKIE_NAME)
    return out
