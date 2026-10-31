# 신청 화면 미리보기, 신청 생성·조회·취소 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.application.schemas import (
    Application,
    ApplicationCreate,
    ApplicationPage,
    ApplyPreview,
)
from app.routers.deps import (
    MEMBER_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

router = APIRouter(tags=["applications"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)])

ApplicationId = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="신청 일련번호(문자열)")]

APPLY_ERRORS = error_responses(
    ErrorCode.APLY_RCPT_CLOSED,
    ErrorCode.APLY_PRIORITY_PERIOD,
    ErrorCode.APLY_ALREADY_APPLIED,
    ErrorCode.APLY_FULL,
    ErrorCode.APLY_MEMBER_INACTIVE,
    ErrorCode.IDEMPOTENCY_CONFLICT,
)


@router.get("/courses/{course_id}/apply-preview")
def get_apply_preview(
    course_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="강좌 일련번호(문자열)")],
) -> ApplyPreview:
    not_implemented()


@router.post("/me/applications", status_code=201, responses=APPLY_ERRORS, dependencies=[Depends(csrf_header)])
def create_application(body: ApplicationCreate, idempotency_key: IdempotencyKey) -> Application:
    not_implemented()


@router.get("/me/applications")
def list_my_applications(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ApplicationPage:
    not_implemented()


@router.get("/me/applications/{application_id}")
def get_my_application(application_id: ApplicationId) -> Application:
    not_implemented()


@router.post(
    "/me/applications/{application_id}/cancel",
    responses=error_responses(ErrorCode.APLY_CANCEL_NOT_ALLOWED, ErrorCode.PAY_RESULT_PENDING),
    dependencies=[Depends(csrf_header)],
)
def cancel_my_application(application_id: ApplicationId) -> Application:
    not_implemented()
