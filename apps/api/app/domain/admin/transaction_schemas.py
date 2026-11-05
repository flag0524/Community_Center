# 관리자 결제·거래 대조 API의 요청·응답 모델
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.application_schemas import LinkedRefund
from app.domain.admin.application_types import ActionKind, NoticeHandling, ReconcileOutcome
from app.domain.application.types import ApplicationDisplayState
from app.domain.payment.types import PaymentMethod, PaymentStatus


class TransactionSummary(ApiModel):
    transaction_id: SerialId
    order_no: str
    application_no: str
    amount: Won
    method: PaymentMethod
    status: PaymentStatus
    requested_at: AwareDatetime
    approved_at: AwareDatetime | None
    recheck_count: int = Field(ge=0)
    has_conflict: bool = Field(description="충돌로 격리된 PG 통보가 있는 거래")


class TransactionPage(Page[TransactionSummary]):
    pass


class PgNotice(ApiModel):
    at: AwareDatetime
    hash_prefix: str = Field(description="통보 내용 해시의 앞부분. 원문은 보여 주지 않는다.")
    handling: NoticeHandling


class TransactionAction(ApiModel):
    at: AwareDatetime
    kind: ActionKind
    actor: str = Field(description="SYSTEM 또는 처리한 관리자 이름")
    result: str


class Transaction(TransactionSummary):
    application_id: SerialId
    course_name: str
    applicant_name: str = Field(description="신청자 이름은 가려서 준다.")
    application_state: ApplicationDisplayState
    merchant_id: str
    payment_deadline_at: AwareDatetime | None
    recheck_max: int = Field(ge=1, description="자동 재조회 횟수 한도")
    last_recheck_at: AwareDatetime | None
    notices: list[PgNotice]
    actions: list[TransactionAction]
    refund: LinkedRefund | None
    can_recheck: bool = Field(description="결과 확인 중인 거래에 조회 권한이 있을 때만 true다.")
    can_reconcile: bool = Field(description="결과 확인 중인 거래에 대사 권한이 있을 때만 true다.")
    version: int = Field(ge=1)


class ReconcileRequest(ApiModel):
    """PG 관리자 화면에서 확인한 결과만 입력한다. 확인되지 않은 상태를 임의로 정하지 않는다."""

    outcome: ReconcileOutcome
    approval_no: str | None = Field(default=None, max_length=40, description="성공이면 PG 승인번호가 필수다.")
    evidence: str = Field(
        min_length=5, max_length=1000, description="확인 근거(필수). 파일 첨부는 첨부 설계 뒤에 더한다."
    )
    version: int = Field(ge=1)
