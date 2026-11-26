# 강사 본인의 담당 강좌와 출석 입력 라우터. 경로의 번호 대신 세션의 회원에게 연결된 강사만 쓴다(FN-064)
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.deps import Clock, Member, get_clock, request_id_of, require_member, require_member_write
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.attendance import service
from app.domain.attendance.schemas import (
    TeachingAttendanceCreate,
    TeachingAttendanceUpdate,
    TeachingCourseList,
    TeachingSheet,
)
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, csrf_header, error_responses, member_session

member_router = APIRouter(tags=["teaching"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]
SERIAL = r"^[0-9]{1,22}$"


@member_router.get("/me/teaching/courses")
def list_my_teaching_courses(db: Db, me: Me, clock: Now) -> TeachingCourseList:
    """내가 담당하는 강좌와 오늘까지의 수업 회차. 승인 강사가 아니면 빈 목록이다."""
    return service.list_courses(db, me, now=clock())


@member_router.get("/me/teaching/attendance")
def get_my_teaching_sheet(
    db: Db,
    me: Me,
    clock: Now,
    course_id: Annotated[str, Query(alias="courseId", pattern=SERIAL)],
    class_date: Annotated[date, Query(alias="classDate")],
    schedule_id: Annotated[str, Query(alias="scheduleId", pattern=SERIAL)],
    change_id: Annotated[str | None, Query(alias="changeId", pattern=SERIAL)] = None,
) -> TeachingSheet:
    """한 회차의 명단과 저장한 출석. 담당이 아니면 404, 수업 회차가 아니면 422다."""
    return service.get_sheet(
        db,
        me,
        now=clock(),
        course_id=course_id,
        class_date=class_date,
        schedule_id=schedule_id,
        change_id=change_id,
    )


@member_router.post(
    "/me/teaching/attendance",
    status_code=201,
    responses=error_responses(ErrorCode.IDEMPOTENCY_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def create_my_teaching_sheet(
    body: TeachingAttendanceCreate,
    request: Request,
    db: Db,
    me: MeWrite,
    clock: Now,
    idempotency_key: IdempotencyKey,
) -> TeachingSheet:
    """출석부를 만든다. 명단이 달라졌거나 이미 출석부가 있으면 409다."""
    return service.create_sheet(
        db, me, body, idem_key=idempotency_key, now=clock(), request_id=request_id_of(request)
    )


@member_router.put(
    "/me/teaching/attendance/{attendance_id}",
    responses=error_responses(ErrorCode.VERSION_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def update_my_teaching_sheet(
    attendance_id: Annotated[str, Path(pattern=SERIAL)],
    body: TeachingAttendanceUpdate,
    request: Request,
    db: Db,
    me: MeWrite,
    clock: Now,
) -> TeachingSheet:
    """출석을 고친다. 읽은 뒤 다른 저장이 있었으면 409(VERSION_CONFLICT)다."""
    return service.update_sheet(db, me, attendance_id, body, now=clock(), request_id=request_id_of(request))
