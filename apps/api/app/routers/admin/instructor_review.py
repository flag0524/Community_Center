# 관리자 강사 심사 라우터. 조회와 변경 모두 AU.INSTR_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import instructor_review_service as service
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
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT_STATE,
    ErrorCode.VERSION_CONFLICT,
    ErrorCode.IDEMPOTENCY_CONFLICT,
    ErrorCode.RULE_REJECTED,
)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/instructor-applications")
def list_instructor_reviews(
    db: Db,
    admin: Me,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100, description="지원자 또는 희망 강좌")] = None,
    status: ReviewStatus | None = None,
    is_public: Annotated[bool | None, Query(alias="isPublic")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> InstructorReviewPage:
    return service.list_reviews(
        db, admin, now=clock(), q=q, status=status, is_public=is_public, page=page, size=size
    )


@router.post(
    "/instructor-applications", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def create_instructor_review(
    body: InstructorReviewCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    settings: Annotated[Settings, Depends(get_settings)],
) -> InstructorReview:
    """방문·외부 접수 건을 등록한다. 처음 상태는 심사대기다."""
    return service.create_review(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        body=body,
        idem_key=idempotency_key,
    )


@router.get("/instructor-applications/{application_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_instructor_review(application_id: Serial, db: Db, admin: Me, clock: Now) -> InstructorReview:
    return service.get_review(db, admin, now=clock(), application_id=application_id)


@router.put(
    "/instructor-applications/{application_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def review_instructor(
    application_id: Serial, body: InstructorReviewWrite, request: Request, db: Db, admin: Me, clock: Now
) -> InstructorReview:
    """반려·활동중지는 사유가 필수이고 공개는 승인된 강사만 가능하다."""
    return service.review(
        db, admin, now=clock(), request_id=request_id_of(request), application_id=application_id, body=body
    )
