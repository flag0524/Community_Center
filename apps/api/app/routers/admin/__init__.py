# 관리자 앱이 호출하는 /api/admin/v1 라우터를 하나로 묶는다
from fastapi import APIRouter

from app.routers.admin import (
    application,
    attendance,
    auth,
    board,
    education,
    facility,
    instructor_review,
    me,
    member,
    refund,
    schedule,
    transaction,
)

admin_router = APIRouter(prefix="/api/admin/v1")
for module in (
    auth,
    me,
    education,
    facility,
    schedule,
    instructor_review,
    attendance,
    application,
    transaction,
    refund,
    member,
    board,
):
    admin_router.include_router(module.router)
