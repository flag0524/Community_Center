# 관리자 알림 이력·문자 발송 라우터. 모두 AU.SMS_SEND이고 발송은 아웃박스에 쌓은 뒤 워커가 보낸다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import sms_service as service
from app.domain.admin.sms_schemas import (
    SmsAudience,
    SmsPreview,
    SmsRequestDetail,
    SmsRequestPage,
    SmsSendRequest,
)
from app.domain.admin.sms_types import SmsKind
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-sms"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
PREVIEW_ERRORS = error_responses(ErrorCode.RULE_REJECTED)
SEND_ERRORS = error_responses(
    ErrorCode.RULE_REJECTED, ErrorCode.CONFLICT_STATE, ErrorCode.IDEMPOTENCY_CONFLICT
)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/sms")
def list_sms_requests(
    db: Db,
    admin: Me,
    clock: Now,
    kind: SmsKind = SmsKind.AUTO,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SmsRequestPage:
    """자동 알림과 관리자 발송 이력. 최근 요청이 먼저 나온다."""
    return service.list_requests(db, admin, now=clock(), kind=kind, page=page, size=size)


@router.get("/sms/{sms_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_sms_request(sms_id: Serial, db: Db, admin: Me, clock: Now, settings: Config) -> SmsRequestDetail:
    """건별 결과와 실패 사유. 수신번호와 이름은 가려서 준다."""
    return service.get(db, settings, admin, now=clock(), sms_id=sms_id)


@router.post("/sms/preview", responses=PREVIEW_ERRORS, dependencies=[Depends(csrf_header)])
def preview_sms(body: SmsAudience, db: Db, admin: Me, clock: Now) -> SmsPreview:
    """대상을 산정해 수신자 수를 알려준다. 저장하지 않는다. 센터 전체는 센터 전체 범위 권한이 필요하다."""
    return service.preview(db, admin, now=clock(), body=body)


@router.post("/sms", status_code=201, responses=SEND_ERRORS, dependencies=[Depends(csrf_header)])
def send_sms(
    body: SmsSendRequest,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    settings: Config,
) -> SmsRequestDetail:
    """대상을 다시 산정해 요청·강좌 연결·수신명단을 한 트랜잭션으로 저장한다. 발송은 커밋 뒤 워커가 한다."""
    return service.send(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        body=body,
        idem_key=idempotency_key,
    )
