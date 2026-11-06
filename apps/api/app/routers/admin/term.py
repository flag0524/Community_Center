# 관리자 약관·동의문 라우터. 모두 AU.SITE_W이고 확정·게시된 문안은 덮어쓰지 않고 새 버전으로 개정한다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.term_schemas import (
    TermVersion,
    TermVersionAction,
    TermVersionCreate,
    TermVersionPage,
    TermVersionUpdate,
)
from app.domain.member.types import TermType
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-term"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED
)
CREATE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/terms")
def list_term_versions(
    term_type: Annotated[TermType | None, Query(alias="type")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TermVersionPage:
    """문안 종류별 버전 목록. 최신 시행일이 먼저 나온다."""
    not_implemented()


@router.get("/terms/versions/{version_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_term_version(version_id: Serial) -> TermVersion:
    not_implemented()


@router.post(
    "/terms/{term_type}/versions",
    status_code=201,
    responses=CREATE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_term_version(
    term_type: TermType, body: TermVersionCreate, idempotency_key: IdempotencyKey
) -> TermVersion:
    """새 버전을 검토 상태로 만든다. 이전 버전을 복제해 시작할 수 있다."""
    not_implemented()


@router.put("/terms/versions/{version_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_term_version(version_id: Serial, body: TermVersionUpdate) -> TermVersion:
    """검토 상태의 버전만 고친다. 확정·게시된 버전은 409다."""
    not_implemented()


@router.post("/terms/versions/{version_id}/fix", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def fix_term_version(version_id: Serial, body: TermVersionAction) -> TermVersion:
    """검토 버전을 확정한다. 문안 SHA-256 해시가 고정된다."""
    not_implemented()


@router.post(
    "/terms/versions/{version_id}/publish", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def publish_term_version(version_id: Serial, body: TermVersionAction) -> TermVersion:
    """확정 버전을 게시한다. 같은 종류의 이전 게시 버전은 게시 종료가 된다."""
    not_implemented()
