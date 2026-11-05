# 관리자 수강신청 조회와 대기·자리 배정 조회 라우터. 모두 조회 전용이며 AU.APLY_R이다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.application_schemas import (
    AdminApplication,
    AdminApplicationPage,
    WaitlistDetail,
    WaitlistPage,
)
from app.domain.application.types import ApplicationStatus
from app.domain.payment.types import PaymentStatus
from app.routers.deps import MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(
    tags=["admin-application"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)


@router.get("/applications")
def list_admin_applications(
    q: Annotated[str | None, Query(max_length=100, description="신청번호 또는 이름")] = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    course_id: Annotated[str | None, Query(alias="courseId", pattern=r"^[0-9]{1,22}$")] = None,
    status: ApplicationStatus | None = None,
    payment_status: Annotated[PaymentStatus | None, Query(alias="paymentStatus")] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminApplicationPage:
    """범위 밖 강좌의 신청은 나오지 않는다. 범위는 신청자 거주지가 아니라 강좌의 운영 동이다."""
    not_implemented()


@router.get("/applications/{application_id}", responses=NOT_FOUND)
def get_admin_application(application_id: Serial) -> AdminApplication:
    not_implemented()


@router.get("/waitlist")
def list_waitlist(
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WaitlistPage:
    not_implemented()


@router.get("/waitlist/{course_id}", responses=NOT_FOUND)
def get_waitlist(course_id: Serial) -> WaitlistDetail:
    not_implemented()
