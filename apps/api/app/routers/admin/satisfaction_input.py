# 관리자 강좌 만족도 집계자료 등록·승인 라우터(연령·성별 집계자료와 같은 임시 권한, ADR-091)
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import satisfaction_input_service as service
from app.domain.admin.satisfaction_input_schemas import (
    SatisfactionSourceCreate,
    SatisfactionSourceDetail,
    SatisfactionSourceList,
)
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(
    tags=["admin-satisfaction-input"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]
BASE = "/stats/satisfaction/sources"


@router.get(BASE)
def list_satisfaction_sources(db: Db, admin: Me, clock: Now) -> SatisfactionSourceList:
    """등록한 만족도 자료를 최근 등록 순으로 100건까지 준다. 검토 전·승인·반려가 모두 보인다."""
    return service.list_sources(db, admin, now=clock())


@router.get(BASE + "/{source_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_satisfaction_source(source_id: Serial, db: Db, admin: Me, clock: Now) -> SatisfactionSourceDetail:
    return service.get_source(db, admin, now=clock(), source_id=source_id)


@router.post(
    BASE,
    status_code=201,
    responses=error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def create_satisfaction_source(
    body: SatisfactionSourceCreate,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    idempotency_key: IdempotencyKey,
) -> SatisfactionSourceDetail:
    """검토 전 자료로 등록한다. 버전은 서버가 정하고 승인한 자료는 고치지 않는다."""
    return service.create_source(
        db, admin, now=clock(), request_id=request_id_of(request), body=body, idem_key=idempotency_key
    )


@router.post(
    BASE + "/{source_id}/approve",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def approve_satisfaction_source(
    source_id: Serial, request: Request, db: Db, admin: Me, clock: Now
) -> SatisfactionSourceDetail:
    """검토 전 자료를 승인한다. 승인하면 만족도 통계에 보이는 최신 버전이 된다."""
    return service.approve_source(
        db, admin, now=clock(), request_id=request_id_of(request), source_id=source_id
    )


@router.post(
    BASE + "/{source_id}/reject",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def reject_satisfaction_source(
    source_id: Serial, request: Request, db: Db, admin: Me, clock: Now
) -> SatisfactionSourceDetail:
    return service.reject_source(
        db, admin, now=clock(), request_id=request_id_of(request), source_id=source_id
    )
