# 관리자 강좌 일정·휴보강 라우터. 조회는 AU.CORS_R, 변경은 AU.CORS_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, Security

from app.core.errors import ErrorCode, not_implemented
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
WRITE_ERRORS = error_responses(ErrorCode.VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/courses/{course_id}/schedules")
def get_course_schedules(course_id: Serial) -> CourseSchedules:
    not_implemented()


@router.post(
    "/courses/{course_id}/schedules",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_schedule(course_id: Serial, body: ScheduleWrite, idempotency_key: IdempotencyKey) -> Schedule:
    """같은 시설·요일·시간·기간에 다른 강좌 일정이 있으면 422(FN-049)."""
    not_implemented()


@router.put(
    "/courses/{course_id}/schedules/{schedule_id}",
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def update_schedule(course_id: Serial, schedule_id: Serial, body: ScheduleUpdate) -> Schedule:
    not_implemented()


@router.delete(
    "/courses/{course_id}/schedules/{schedule_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(csrf_header)],
)
def delete_schedule(course_id: Serial, schedule_id: Serial) -> None:
    not_implemented()


@router.post(
    "/courses/{course_id}/schedule-changes",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_schedule_change(
    course_id: Serial, body: ScheduleChangeWrite, idempotency_key: IdempotencyKey
) -> ScheduleChange:
    not_implemented()


@router.delete(
    "/courses/{course_id}/schedule-changes/{change_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(csrf_header)],
)
def delete_schedule_change(course_id: Serial, change_id: Serial) -> None:
    not_implemented()
