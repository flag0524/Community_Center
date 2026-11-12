# 관리자 교육기수·강좌 관리 라우터. 기수는 AU.CONF_W, 강좌는 조회 AU.CORS_R·변경 AU.CORS_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin, require_admin_write
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import education_service as service
from app.domain.admin.csv_export import csv_response
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
from app.routers.deps import (
    CSV_RESPONSE,
    MEMBER_ERRORS,
    IdempotencyKey,
    admin_session,
    csrf_header,
    error_responses,
)

router = APIRouter(tags=["admin-education"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
SerialQuery = Annotated[str | None, Query(pattern=r"^[0-9]{1,22}$")]
Page_ = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT_STATE,
    ErrorCode.RULE_REJECTED,
    ErrorCode.VERSION_CONFLICT,
    ErrorCode.IDEMPOTENCY_CONFLICT,
)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
MeWrite = Annotated[Admin, Depends(require_admin_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/cycles")
def list_cycles(db: Db, admin: Me, clock: Now, page: Page_ = 1, size: Size = 20) -> CyclePage:
    return service.list_cycles(db, admin, now=clock(), page=page, size=size)


@router.post("/cycles", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_cycle(
    body: CycleWrite, idempotency_key: IdempotencyKey, request: Request, db: Db, admin: MeWrite, clock: Now
) -> Cycle:
    return service.create_cycle(
        db, admin, now=clock(), request_id=request_id_of(request), body=body, idem_key=idempotency_key
    )


@router.get(
    "/cycles/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_cycles_csv(request: Request, db: Db, admin: Me, clock: Now) -> Response:
    """교육기수 목록 전체. 기간과 접수기간은 한국 시간 날짜로 담는다."""
    content = service.export_cycles_csv(db, admin, now=clock(), request_id=request_id_of(request))
    return csv_response("cycles.csv", content)


@router.get("/cycles/{cycle_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_cycle(cycle_id: Serial, db: Db, admin: Me, clock: Now) -> Cycle:
    return service.get_cycle(db, admin, now=clock(), cycle_id=cycle_id)


@router.put("/cycles/{cycle_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_cycle(
    cycle_id: Serial, body: CycleUpdate, request: Request, db: Db, admin: MeWrite, clock: Now
) -> Cycle:
    return service.update_cycle(
        db, admin, now=clock(), request_id=request_id_of(request), cycle_id=cycle_id, body=body
    )


@router.get("/course-options")
def get_course_options(db: Db, admin: Me, clock: Now) -> CourseOptions:
    return service.get_options(db, admin, now=clock())


@router.get("/courses")
def list_admin_courses(
    db: Db,
    admin: Me,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    class_id: Annotated[str | None, Query(alias="classId", pattern=r"^[0-9]{1,22}$")] = None,
    dong_id: Annotated[str | None, Query(alias="dongId", pattern=r"^[0-9]{1,22}$")] = None,
    status: CourseAdminStatus | None = None,
    page: Page_ = 1,
    size: Size = 20,
) -> AdminCoursePage:
    """범위 밖 강좌는 조건과 무관하게 목록에 나오지 않는다(RQ-SER-NF-009)."""
    return service.list_courses(
        db,
        admin,
        now=clock(),
        q=q,
        cycle_id=cycle_id,
        class_id=class_id,
        dong_id=dong_id,
        status=status,
        page=page,
        size=size,
    )


@router.get(
    "/courses/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_courses_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cycle_id: Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")] = None,
    class_id: Annotated[str | None, Query(alias="classId", pattern=r"^[0-9]{1,22}$")] = None,
    dong_id: Annotated[str | None, Query(alias="dongId", pattern=r"^[0-9]{1,22}$")] = None,
    status: CourseAdminStatus | None = None,
) -> Response:
    """목록과 같은 조건·범위로 만든다. 범위 밖 강좌는 담지 않는다(RQ-SER-NF-009)."""
    content = service.export_courses_csv(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        q=q,
        cycle_id=cycle_id,
        class_id=class_id,
        dong_id=dong_id,
        status=status,
    )
    return csv_response("courses.csv", content)


@router.post("/courses", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_course(
    body: CourseWrite, idempotency_key: IdempotencyKey, request: Request, db: Db, admin: MeWrite, clock: Now
) -> AdminCourse:
    return service.create_course(
        db, admin, now=clock(), request_id=request_id_of(request), body=body, idem_key=idempotency_key
    )


@router.get("/courses/{course_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_course(course_id: Serial, db: Db, admin: Me, clock: Now) -> AdminCourse:
    return service.get_course(db, admin, now=clock(), course_id=course_id)


@router.put("/courses/{course_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_admin_course(
    course_id: Serial, body: CourseUpdate, request: Request, db: Db, admin: MeWrite, clock: Now
) -> AdminCourse:
    """모집정원은 현재 점유보다 작게 줄일 수 없다(화면설계서 ADM-EDU-001P)."""
    return service.update_course(
        db, admin, now=clock(), request_id=request_id_of(request), course_id=course_id, body=body
    )


@router.post("/courses/{course_id}/publish", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def publish_course(course_id: Serial, request: Request, db: Db, admin: MeWrite, clock: Now) -> AdminCourse:
    """공개 요청 검사: 승인 강사, 일정 1건 이상, 기수 내 기간, 접수기간."""
    return service.publish(db, admin, now=clock(), request_id=request_id_of(request), course_id=course_id)


@router.post(
    "/courses/{course_id}/close-reception", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def close_course_reception(
    course_id: Serial, request: Request, db: Db, admin: MeWrite, clock: Now
) -> AdminCourse:
    return service.close_reception(
        db, admin, now=clock(), request_id=request_id_of(request), course_id=course_id
    )


@router.get("/courses/{course_id}/cancel-preview", responses=error_responses(ErrorCode.NOT_FOUND))
def get_cancel_preview(course_id: Serial, db: Db, admin: Me, clock: Now) -> CancelPreview:
    return service.cancel_preview(db, admin, now=clock(), course_id=course_id)


@router.post(
    "/courses/{course_id}/cancel-course", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def cancel_course(
    course_id: Serial,
    body: CancelCourseRequest,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> AdminCourse:
    """유효한 신청을 모두 취소하고 결제한 건은 전액 환불을 접수한다. 폐강은 환불 완료가 아니다(FN-057)."""
    return service.cancel_course(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        course_id=course_id,
        reason=body.reason,
    )
