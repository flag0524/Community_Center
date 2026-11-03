# 주민 앱이 호출하는 /api/v1 라우터를 하나로 묶는다
from fastapi import APIRouter

from app.routers.user import applications, auth, board, courses, me, payments, refunds, site

user_router = APIRouter(prefix="/api/v1")
for module in (site, courses, auth, me, applications, payments, refunds, board):
    user_router.include_router(module.router)
