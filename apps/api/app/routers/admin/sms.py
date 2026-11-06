# 관리자 알림 이력·문자 발송 라우터. 모두 AU.SMS_SEND이고 발송은 아웃박스에 쌓은 뒤 워커가 보낸다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
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


@router.get("/sms")
def list_sms_requests(
    kind: SmsKind = SmsKind.AUTO,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SmsRequestPage:
    """자동 알림과 관리자 발송 이력. 최근 요청이 먼저 나온다."""
    not_implemented()


@router.get("/sms/{sms_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_sms_request(sms_id: Serial) -> SmsRequestDetail:
    """건별 결과와 실패 사유. 수신번호와 이름은 가려서 준다."""
    not_implemented()


@router.post("/sms/preview", responses=PREVIEW_ERRORS, dependencies=[Depends(csrf_header)])
def preview_sms(body: SmsAudience) -> SmsPreview:
    """대상을 산정해 수신자 수를 알려준다. 저장하지 않는다. 센터 전체는 센터 전체 범위 권한이 필요하다."""
    not_implemented()


@router.post("/sms", status_code=201, responses=SEND_ERRORS, dependencies=[Depends(csrf_header)])
def send_sms(body: SmsSendRequest, idempotency_key: IdempotencyKey) -> SmsRequestDetail:
    """대상을 다시 산정해 요청·강좌 연결·수신명단을 한 트랜잭션으로 저장한다. 발송은 커밋 뒤 워커가 한다."""
    not_implemented()
