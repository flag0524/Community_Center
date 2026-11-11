# 관리자 앱이 호출하는 /api/admin/v1 라우터를 하나로 묶는다
from fastapi import APIRouter, Depends

from app.auth.admin_access import require_admin
from app.routers.admin import (
    application,
    attendance,
    auth,
    board,
    code,
    content,
    course_class,
    education,
    export,
    facility,
    file,
    inquiry,
    instructor_review,
    me,
    member,
    reduction,
    refund,
    retention,
    role,
    schedule,
    setting,
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
    export,
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
    reduction,
    setting,
    code,
    course_class,
    retention,
):
    # 로그인 전용 라우터를 뺀 모든 관리자 엔드포인트는 로그인한 관리자만 부른다(미구현 포함).
    # 기능별 권한·범위는 구현할 때 각 서비스가 대상 레코드로 판정한다(ADR-043).
    admin_router.include_router(
        module.router, dependencies=[] if module is auth else [Depends(require_admin)]
    )
