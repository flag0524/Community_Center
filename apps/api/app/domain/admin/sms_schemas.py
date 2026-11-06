# 관리자 알림 이력·문자 발송 API의 요청·응답 모델. 수신번호와 이름은 가려서 내려주고 대상 산정은 서버가 한다
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.sms_types import SmsAudienceStatus, SmsKind, SmsScope, SmsTargetState

SMS_MAX_BYTES = 90


class SmsRequestSummary(ApiModel):
    sms_id: SerialId
    requested_at: AwareDatetime
    kind: SmsKind
    scope: SmsScope
    summary: str = Field(description="문안 앞부분")
    target_count: int = Field(ge=0)
    sent: int = Field(ge=0)
    failed: int = Field(ge=0)
    unknown: int = Field(ge=0, description="결과 확인 중")
    requested_by: str = Field(description="요청한 담당자. 자동 알림은 SYSTEM")


class SmsRequestPage(Page[SmsRequestSummary]):
    pass


class SmsTargetRow(ApiModel):
    target_id: SerialId
    name: str = Field(description="가려진 이름")
    phone: str = Field(description="가려진 수신번호")
    state: SmsTargetState
    attempts: int = Field(ge=0, description="발송 시도 횟수")
    fail_code: str | None
    fail_reason: str | None


class SmsRequestDetail(SmsRequestSummary):
    content: str = Field(description="확정 문안. 발송 접수 뒤에는 고치지 않는다.")
    course_names: list[str] = Field(description="선택 강좌 발송이면 그 강좌")
    targets: list[SmsTargetRow] = Field(description="수신 대상별 결과. 최대 200건")
    targets_truncated: bool = Field(description="수신 대상이 200건을 넘어 일부만 담았는지")


class SmsAudience(ApiModel):
    """수신 대상 산정 조건. 미리보기와 발송 요청이 같은 조건을 쓴다."""

    scope: SmsScope = Field(description="CENTER 또는 COURSE만 쓸 수 있다.")
    course_ids: list[SerialId] = Field(default_factory=list, description="COURSE일 때 선택 강좌")
    statuses: list[SmsAudienceStatus] = Field(min_length=1)
    content: str = Field(min_length=1, max_length=200, description="문안. 90바이트를 넘으면 거절한다.")


class SmsRecipient(ApiModel):
    name: str
    phone: str


class SmsPreview(ApiModel):
    recipient_count: int = Field(ge=0, description="중복을 제거한 최종 수신자 수")
    duplicate_removed: int = Field(ge=0)
    course_count: int = Field(ge=0)
    center_name: str
    byte_length: int = Field(ge=0)
    recipients: list[SmsRecipient] = Field(description="가려진 수신자 목록. 최대 50명")


class SmsSendRequest(SmsAudience):
    """발송 요청. 서버가 대상을 다시 산정해 미리보기 수와 다르면 409다."""

    confirmed: bool = Field(description="수신 대상과 문안을 최종 확인했는지. true만 받는다.")
    expected_recipient_count: int = Field(ge=0, description="사용자가 확인한 수신자 수")
