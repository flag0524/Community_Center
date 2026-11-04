# 관리자 교육기수·강좌 관리 라우터. 기수는 AU.CONF_W, 강좌는 조회 AU.CORS_R·변경 AU.CORS_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.education_schemas import (
    AdminCourse,
    AdminCoursePage,
    CancelCourseRequest,
    CancelPreview,
    CourseOptions,
    CourseUpdate,
    CourseWrite,
    Cycle,
    CyclePage,
    CycleUpdate,
    CycleWrite,
)
from app.domain.admin.education_types import CourseAdminStatus
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-education"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
SerialQuery = Annotated[str | None, Query(pattern=r"^[0-9]{1,22}$")]
Page_ = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]
WRITE_ERRORS = error_responses(ErrorCode.VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/cycles")
def list_cycles(page: Page_ = 1, size: Size = 20) -> CyclePage:
    not_implemented()


@router.post("/cycles", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_cycle(body: CycleWrite, idempotency_key: IdempotencyKey) -> Cycle:
    not_implemented()


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: Serial) -> Cycle:
    not_implemented()


@router.put("/cycles/{cycle_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_cycle(cycle_id: Serial, body: CycleUpdate) -> Cycle:
    not_implemented()


@router.get("/course-options")
def get_course_options() -> CourseOptions:
    not_implemented()


@router.get("/courses")
def list_admin_courses(
    q: Annotated[str | None, Query(max_length=100)] = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    class_id: Annotated[str | None, Query(alias="classId", pattern=r"^[0-9]{1,22}$")] = None,
    dong_id: Annotated[str | None, Query(alias="dongId", pattern=r"^[0-9]{1,22}$")] = None,
    status: CourseAdminStatus | None = None,
    page: Page_ = 1,
    size: Size = 20,
) -> AdminCoursePage:
    """범위 밖 강좌는 조건과 무관하게 목록에 나오지 않는다(RQ-SER-NF-009)."""
    not_implemented()


@router.post("/courses", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_course(body: CourseWrite, idempotency_key: IdempotencyKey) -> AdminCourse:
    not_implemented()


@router.get("/courses/{course_id}")
def get_admin_course(course_id: Serial) -> AdminCourse:
    not_implemented()


@router.put("/courses/{course_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_admin_course(course_id: Serial, body: CourseUpdate) -> AdminCourse:
    """모집정원은 현재 점유보다 작게 줄일 수 없다(화면설계서 ADM-EDU-001P)."""
    not_implemented()


@router.post("/courses/{course_id}/publish", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def publish_course(course_id: Serial) -> AdminCourse:
    """공개 요청 검사: 승인 강사, 일정 1건 이상, 기수 내 기간, 접수기간."""
    not_implemented()


@router.post(
    "/courses/{course_id}/close-reception", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def close_course_reception(course_id: Serial) -> AdminCourse:
    not_implemented()


@router.get("/courses/{course_id}/cancel-preview")
def get_cancel_preview(course_id: Serial) -> CancelPreview:
    not_implemented()


@router.post(
    "/courses/{course_id}/cancel-course", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def cancel_course(course_id: Serial, body: CancelCourseRequest) -> AdminCourse:
    not_implemented()
