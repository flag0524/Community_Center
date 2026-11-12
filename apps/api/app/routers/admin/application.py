# 관리자 수강신청 조회와 대기·자리 배정 조회 라우터. 모두 조회 전용이며 AU.APLY_R이다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import application_service as service
from app.domain.admin.application_schemas import (
    AdminApplication,
    AdminApplicationPage,
    WaitlistDetail,
    WaitlistPage,
)
from app.domain.admin.csv_export import csv_response
from app.domain.application.types import ApplicationStatus
from app.domain.payment.types import PaymentStatus
from app.routers.deps import CSV_RESPONSE, MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(
    tags=["admin-application"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/applications")
def list_admin_applications(
    db: Db,
    admin: Me,
    clock: Now,
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
    return service.list_applications(
        db,
        admin,
        now=clock(),
        q=q,
        cycle_id=cycle_id,
        course_id=course_id,
        status=status,
        payment_status=payment_status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        size=size,
    )


@router.get(
    "/applications/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_applications_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100, description="신청번호 또는 이름")] = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    course_id: Annotated[str | None, Query(alias="courseId", pattern=r"^[0-9]{1,22}$")] = None,
    status: ApplicationStatus | None = None,
    payment_status: Annotated[PaymentStatus | None, Query(alias="paymentStatus")] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> Response:
    """목록과 같은 조건·권한·가려진 값으로 만든다. 페이지 제한만 없다. 만들 때마다 작업이력에 남긴다."""
    content = service.export_csv(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        q=q,
        cycle_id=cycle_id,
        course_id=course_id,
        status=status,
        payment_status=payment_status,
        from_date=from_date,
        to_date=to_date,
    )
    return csv_response("applications.csv", content)


@router.get("/applications/{application_id}", responses=NOT_FOUND)
def get_admin_application(application_id: Serial, db: Db, admin: Me, clock: Now) -> AdminApplication:
    return service.get_application(db, admin, now=clock(), application_id=application_id)


@router.get("/waitlist")
def list_waitlist(
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WaitlistPage:
    return service.list_waitlist(db, admin, now=clock(), cycle_id=cycle_id, page=page, size=size)


@router.get("/waitlist/{course_id}", responses=NOT_FOUND)
def get_waitlist(course_id: Serial, db: Db, admin: Me, clock: Now) -> WaitlistDetail:
    return service.get_waitlist(db, admin, now=clock(), course_id=course_id)
