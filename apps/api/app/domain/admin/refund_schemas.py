# 관리자 환불 검토 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.application_types import ExecutionMethod, RefundRequester
from app.domain.payment.types import PaymentMethod
from app.domain.refund.types import RefundRule, RefundStatus

Amount = Field(ge=1, le=10_000_000, description="원 단위 금액. 1원 이상")


class AdminRefundSummary(ApiModel):
    refund_id: SerialId
    refund_no: str
    application_no: str
    course_name: str
    requested_amount: Won
    status: RefundStatus
    received_on: date
    elapsed_business_days: int = Field(ge=0, description="접수 뒤 지난 영업일(공휴일 자료 전)")
    overdue: bool = Field(description="심사 목표 3영업일을 넘겼는지. 서버가 정한다.")
    requester: RefundRequester


class AdminRefundPage(Page[AdminRefundSummary]):
    pass


class RefundHistoryEntry(ApiModel):
    at: AwareDatetime
    status: RefundStatus
    actor: str = Field(description="회원, SYSTEM, 또는 처리한 담당자 이름")
    note: str | None


class ManualAccount(ApiModel):
    """수동 계좌환불 정보. 계좌와 예금주는 가려서 주고 원문은 감사기록과 함께 별도로 연다."""

    bank_name: str
    holder_masked: str
    account_masked: str


class AdminRefund(AdminRefundSummary):
    payment_order_no: str
    paid_amount: Won = Field(description="원결제액. 환불로 줄지 않는다.")
    payment_method: PaymentMethod
    paid_at: AwareDatetime
    reserved_amount: Won = Field(description="완료·승인·처리중 환불의 합(이 환불 제외)")
    remaining_amount: Won = Field(description="원결제액 − 예약액. 계산값이다.")
    baseline_amount: Won = Field(description="승인 시 산정하는 반환 기준액")
    baseline_rule: RefundRule
    education_start: date
    reason: str
    detail: str | None
    evidence_count: int = Field(ge=0)
    requester_name: str = Field(description="회원 이름은 가려서, 대리 접수는 담당자 이름을 준다.")
    approved_amount: Won | None
    decision_reason: str | None
    decided_by: str | None
    execution_method: ExecutionMethod
    manual_account: ManualAccount | None
    executed_by: str | None
    execution_result: str | None
    history: list[RefundHistoryEntry]
    version: int = Field(ge=1)
    can_review: bool = Field(description="승인 권한이 있고 접수·보류 상태일 때만 true다.")
    can_execute: bool = Field(
        description="집행 권한이 있고 승인(또는 실패) 상태이며 승인자와 다른 담당자일 때만 true다."
    )
    can_confirm_transfer: bool = Field(description="수동 계좌환불의 이체 완료를 확인할 수 있을 때만 true다.")
    execute_note: str | None = Field(description="집행할 수 없는 이유(예: 승인한 담당자와 같음)")


class AdminRefundCreate(ApiModel):
    """방문·유선으로 받은 환불을 담당자가 대신 접수한다. 승인은 따로 한다."""

    application_no: str = Field(min_length=1, max_length=30)
    requested_amount: int = Amount
    reason: str = Field(min_length=1, max_length=500)
    detail: str | None = Field(default=None, max_length=2000)


class RefundHoldRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class RefundApproveRequest(ApiModel):
    amount: int = Amount
    version: int = Field(ge=1)


class RefundRejectRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)


class RefundVersionRequest(ApiModel):
    version: int = Field(ge=1, description="화면이 읽은 RCRD_VER. 다르면 409")
