# 관리자 앱이 호출하는 /api/admin/v1 라우터를 하나로 묶는다
from fastapi import APIRouter

from app.routers.admin import (
    application,
    attendance,
    auth,
    board,
    content,
    education,
    facility,
    file,
    inquiry,
    instructor_review,
    me,
    member,
    refund,
    role,
    schedule,
    sms,
    stats,
    term,
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
    inquiry,
    content,
    term,
    file,
    stats,
    sms,
    role,
):
    admin_router.include_router(module.router)
