# 로그인한 회원 본인 정보 라우터. 경로의 회원 번호 대신 세션의 회원만 쓴다.
from fastapi import APIRouter, Security

from app.core.errors import not_implemented
from app.domain.member.schemas import MemberProfile
from app.routers.deps import MEMBER_ERRORS, member_session

router = APIRouter(tags=["me"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])


@router.get("/me/profile")
def get_my_profile() -> MemberProfile:
    not_implemented()
