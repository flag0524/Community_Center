# 관리자 강좌분류 라우터. 조회 AU.CORS_R, 변경 제안 권한 AU.CORS_W(PRD Q21). 삭제는 논리삭제다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.class_schemas import (
    ClassHistoryList,
    CourseClass,
    CourseClassAction,
    CourseClassList,
    CourseClassUpdate,
    CourseClassWrite,
)
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(
    tags=["admin-course-class"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED
)


@router.get("/course-classes")
def list_course_classes() -> CourseClassList:
    """삭제하지 않은 분류를 순서대로 준다. 연결 강좌 수를 확인하지 못하면 해당 분류의 수는 null이다."""
    not_implemented()


@router.post(
    "/course-classes",
    status_code=201,
    responses=error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def create_course_class(body: CourseClassWrite, idempotency_key: IdempotencyKey) -> CourseClass:
    """이름을 NFKC·공백 정리·대소문자 통일로 정규화해 삭제한 분류를 포함해 중복을 검사한다."""
    not_implemented()


@router.put("/course-classes/{class_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_course_class(class_id: Serial, body: CourseClassUpdate) -> CourseClass:
    not_implemented()


@router.post(
    "/course-classes/{class_id}/deactivate", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def deactivate_course_class(class_id: Serial, body: CourseClassAction) -> CourseClass:
    """연결 강좌가 있거나 수를 확인하지 못하면 거절한다. 기존 연결은 그대로 둔다."""
    not_implemented()


@router.post(
    "/course-classes/{class_id}/activate", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def activate_course_class(class_id: Serial, body: CourseClassAction) -> CourseClass:
    not_implemented()


@router.delete(
    "/course-classes/{class_id}",
    status_code=204,
    response_class=Response,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def delete_course_class(class_id: Serial, version: Annotated[int, Query(ge=1)]) -> None:
    """논리삭제한다. 연결 강좌가 있거나 수를 확인하지 못하면 거절하고 삭제한 이름은 다시 쓸 수 없다."""
    not_implemented()


@router.get("/course-classes/{class_id}/history", responses=error_responses(ErrorCode.NOT_FOUND))
def list_course_class_history(class_id: Serial) -> ClassHistoryList:
    """등록·명칭·순서 변경·비활성·재활성·삭제의 전후 값과 처리자. 고치거나 지우지 않는다."""
    not_implemented()
