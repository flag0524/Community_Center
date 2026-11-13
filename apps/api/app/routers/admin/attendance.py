# 관리자 출석 현황 조회 라우터. 조회 전용이며 AU.ATND_R이다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import attendance_service as service
from app.domain.admin.attendance_schemas import AttendanceDetail, AttendancePage
from app.domain.admin.education_types import AttendanceInputStatus
from app.routers.deps import MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(tags=["admin-attendance"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
SerialQuery = Annotated[str | None, Query(pattern=r"^[0-9]{1,22}$")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/attendance")
def list_attendance(
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    course_id: Annotated[str | None, Query(alias="courseId", pattern=r"^[0-9]{1,22}$")] = None,
    class_date: Annotated[date | None, Query(alias="classDate")] = None,
    input_status: Annotated[AttendanceInputStatus | None, Query(alias="inputStatus")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AttendancePage:
    """출석부는 CSV로 내려받을 수 없다(FN-064)."""
    return service.list_attendance(
        db,
        admin,
        now=clock(),
        cycle_id=cycle_id,
        course_id=course_id,
        class_date=class_date,
        input_status=input_status,
        page=page,
        size=size,
    )


@router.get("/attendance/{attendance_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_attendance(attendance_id: Serial, db: Db, admin: Me, clock: Now) -> AttendanceDetail:
    return service.get_attendance(db, admin, now=clock(), attendance_id=attendance_id)
