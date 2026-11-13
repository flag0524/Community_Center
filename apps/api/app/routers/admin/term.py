# 관리자 약관·동의문 라우터. 모두 AU.SITE_W이고 확정·게시된 문안은 덮어쓰지 않고 새 버전으로 개정한다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import term_service as service
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
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/terms")
def list_term_versions(
    db: Db,
    admin: Me,
    clock: Now,
    term_type: Annotated[TermType | None, Query(alias="type")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TermVersionPage:
    """문안 종류별 버전 목록. 최신 시행일이 먼저 나온다."""
    return service.list_versions(db, admin, now=clock(), term_type=term_type, page=page, size=size)


@router.get("/terms/versions/{version_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_term_version(version_id: Serial, db: Db, admin: Me, clock: Now) -> TermVersion:
    return service.get_version(db, admin, now=clock(), version_id=version_id)


@router.post(
    "/terms/{term_type}/versions",
    status_code=201,
    responses=CREATE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_term_version(
    term_type: TermType,
    body: TermVersionCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> TermVersion:
    """새 버전을 검토 상태로 만든다. 이전 버전을 복제해 시작할 수 있다."""
    return service.create_version(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        term_type=term_type,
        body=body,
        idem_key=idempotency_key,
    )


@router.put("/terms/versions/{version_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_term_version(
    version_id: Serial, body: TermVersionUpdate, request: Request, db: Db, admin: Me, clock: Now
) -> TermVersion:
    """검토 상태의 버전만 고친다. 확정·게시된 버전은 409다."""
    return service.update_version(
        db, admin, now=clock(), request_id=request_id_of(request), version_id=version_id, body=body
    )


@router.post("/terms/versions/{version_id}/fix", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def fix_term_version(
    version_id: Serial, body: TermVersionAction, request: Request, db: Db, admin: Me, clock: Now
) -> TermVersion:
    """검토 버전을 확정한다. 문안 SHA-256 해시가 고정된다."""
    return service.fix_version(
        db, admin, now=clock(), request_id=request_id_of(request), version_id=version_id, body=body
    )


@router.post(
    "/terms/versions/{version_id}/publish", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def publish_term_version(
    version_id: Serial, body: TermVersionAction, request: Request, db: Db, admin: Me, clock: Now
) -> TermVersion:
    """확정 버전을 게시한다. 같은 종류의 이전 게시 버전은 게시 종료가 된다."""
    return service.publish_version(
        db, admin, now=clock(), request_id=request_id_of(request), version_id=version_id, body=body
    )
