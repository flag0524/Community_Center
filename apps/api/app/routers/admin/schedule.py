# 관리자 강좌 일정·휴보강 라우터. 조회는 AU.CORS_R, 변경은 AU.CORS_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import schedule_service as service
from app.domain.admin.schedule_schemas import (
    CourseSchedules,
    Schedule,
    ScheduleChange,
    ScheduleChangeWrite,
    ScheduleUpdate,
    ScheduleWrite,
)
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-schedule"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT_STATE,
    ErrorCode.VERSION_CONFLICT,
    ErrorCode.IDEMPOTENCY_CONFLICT,
    ErrorCode.RULE_REJECTED,
)
DELETE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.RULE_REJECTED)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/courses/{course_id}/schedules", responses=error_responses(ErrorCode.NOT_FOUND))
def get_course_schedules(course_id: Serial, db: Db, admin: Me, clock: Now) -> CourseSchedules:
    return service.get_schedules(db, admin, now=clock(), course_id=course_id)


@router.post(
    "/courses/{course_id}/schedules",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_schedule(
    course_id: Serial,
    body: ScheduleWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> Schedule:
    """같은 시설·요일·시간·기간에 다른 강좌 일정이 있으면 422(FN-049)."""
    return service.create_schedule(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        course_id=course_id,
        body=body,
        idem_key=idempotency_key,
    )


@router.put(
    "/courses/{course_id}/schedules/{schedule_id}",
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def update_schedule(
    course_id: Serial,
    schedule_id: Serial,
    body: ScheduleUpdate,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> Schedule:
    return service.update_schedule(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        course_id=course_id,
        schedule_id=schedule_id,
        body=body,
    )


@router.delete(
    "/courses/{course_id}/schedules/{schedule_id}",
    status_code=204,
    response_class=Response,
    responses=DELETE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def delete_schedule(
    course_id: Serial, schedule_id: Serial, request: Request, db: Db, admin: Me, clock: Now
) -> None:
    service.delete_schedule(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        course_id=course_id,
        schedule_id=schedule_id,
    )


@router.post(
    "/courses/{course_id}/schedule-changes",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_schedule_change(
    course_id: Serial,
    body: ScheduleChangeWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> ScheduleChange:
    return service.create_change(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        course_id=course_id,
        body=body,
        idem_key=idempotency_key,
    )


@router.delete(
    "/courses/{course_id}/schedule-changes/{change_id}",
    status_code=204,
    response_class=Response,
    responses=DELETE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def delete_schedule_change(
    course_id: Serial, change_id: Serial, request: Request, db: Db, admin: Me, clock: Now
) -> None:
    service.delete_change(
        db, admin, now=clock(), request_id=request_id_of(request), course_id=course_id, change_id=change_id
    )
