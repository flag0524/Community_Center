# 관리자 앱이 호출하는 /api/admin/v1 라우터를 하나로 묶는다
from fastapi import APIRouter

from app.routers.admin import auth, education, me

admin_router = APIRouter(prefix="/api/admin/v1")
for module in (auth, me, education):
    admin_router.include_router(module.router)
