# 관리자 강사 심사 라우터. 조회와 변경 모두 AU.INSTR_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.education_types import ReviewStatus
from app.domain.admin.instructor_review_schemas import (
    InstructorReview,
    InstructorReviewCreate,
    InstructorReviewPage,
    InstructorReviewWrite,
)
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-instructor"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(ErrorCode.VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/instructor-applications")
def list_instructor_reviews(
    q: Annotated[str | None, Query(max_length=100, description="지원자 또는 희망 강좌")] = None,
    status: ReviewStatus | None = None,
    is_public: Annotated[bool | None, Query(alias="isPublic")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InstructorReviewPage:
    not_implemented()


@router.post(
    "/instructor-applications", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def create_instructor_review(
    body: InstructorReviewCreate, idempotency_key: IdempotencyKey
) -> InstructorReview:
    """방문·외부 접수 건을 등록한다. 처음 상태는 심사대기다."""
    not_implemented()


@router.get("/instructor-applications/{application_id}")
def get_instructor_review(application_id: Serial) -> InstructorReview:
    not_implemented()


@router.put(
    "/instructor-applications/{application_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def review_instructor(application_id: Serial, body: InstructorReviewWrite) -> InstructorReview:
    """반려·활동중지는 사유가 필수이고 공개는 승인된 강사만 가능하다."""
    not_implemented()
