# 관리자 홈·센터 콘텐츠 라우터. 모두 AU.SITE_W이고 이력이 있는 콘텐츠는 삭제 대신 게시 여부로 끈다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.content_schemas import (
    AdminContent,
    AdminContentPage,
    AdminContentUpdate,
    AdminContentWrite,
)
from app.domain.admin.content_types import ContentType
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-content"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED)
CREATE_ERRORS = error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/contents")
def list_admin_contents(
    content_type: Annotated[ContentType | None, Query(alias="type")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminContentPage:
    not_implemented()


@router.post("/contents", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_content(body: AdminContentWrite, idempotency_key: IdempotencyKey) -> AdminContent:
    """게시 기간은 시작이 종료보다 앞서야 한다. 연락처는 하나만 둘 수 있다."""
    not_implemented()


@router.get("/contents/{content_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_content(content_id: Serial) -> AdminContent:
    not_implemented()


@router.put("/contents/{content_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_admin_content(content_id: Serial, body: AdminContentUpdate) -> AdminContent:
    not_implemented()
