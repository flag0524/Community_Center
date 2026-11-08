# 주민 앱이 호출하는 /api/v1 라우터를 하나로 묶는다
from fastapi import APIRouter

from app.routers.user import (
    applications,
    auth,
    board,
    community,
    courses,
    instructor,
    me,
    member_file,
    payments,
    refunds,
    site,
)

user_router = APIRouter(prefix="/api/v1")
for module in (site, courses, auth, me, applications, payments, refunds, board, community, instructor):
    user_router.include_router(module.router)
user_router.include_router(community.member_router)
user_router.include_router(instructor.member_router)
user_router.include_router(member_file.member_router)
