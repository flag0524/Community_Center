# 공개 강사·모집공고 조회와 강사 지원(작성·수정·내 지원내역) 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.instructor.schemas import (
    InstructorApplication,
    InstructorApplicationPage,
    InstructorApplyWrite,
    InstructorDetail,
    InstructorPage,
    RecruitmentDetail,
    RecruitmentPage,
)
from app.routers.deps import (
    MEMBER_ERRORS,
    PUBLIC_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

# 강사현황과 모집공고는 누구나 본다.
router = APIRouter(tags=["instructor"], responses=PUBLIC_ERRORS)
# 지원은 로그인한 회원만이다.
member_router = APIRouter(
    tags=["instructor"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Page_ = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=50)]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/instructors")
def list_instructors(
    q: Annotated[str | None, Query(max_length=100, description="강사명 또는 강좌명")] = None,
    page: Page_ = 1,
    size: Size = 10,
) -> InstructorPage:
    not_implemented()


@router.get("/instructors/{instructor_id}", responses=NOT_FOUND)
def get_instructor(instructor_id: Serial) -> InstructorDetail:
    not_implemented()


@router.get("/instructor-recruitments")
def list_recruitments(page: Page_ = 1, size: Size = 10) -> RecruitmentPage:
    not_implemented()


@router.get("/instructor-recruitments/{recruitment_id}", responses=NOT_FOUND)
def get_recruitment(recruitment_id: Serial) -> RecruitmentDetail:
    not_implemented()


@member_router.get("/me/instructor-applications")
def list_my_instructor_applications(page: Page_ = 1, size: Size = 10) -> InstructorApplicationPage:
    not_implemented()


@member_router.post(
    "/me/instructor-applications",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_instructor_application(
    body: InstructorApplyWrite, idempotency_key: IdempotencyKey
) -> InstructorApplication:
    """모집중이 아닌 공고나 이미 지원한 공고는 RULE_REJECTED다. 직접 요청도 같은 검사를 한다."""
    not_implemented()


@member_router.get("/me/instructor-applications/{application_id}", responses=NOT_FOUND)
def get_my_instructor_application(application_id: Serial) -> InstructorApplication:
    not_implemented()


@member_router.put(
    "/me/instructor-applications/{application_id}",
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def update_instructor_application(
    application_id: Serial, body: InstructorApplyWrite
) -> InstructorApplication:
    """서류 검토중·보완요청일 때만 고칠 수 있다(RULE_REJECTED)."""
    not_implemented()
