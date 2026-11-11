# 환불 미리보기·접수·내역 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field, model_validator

from app.core.schema import ApiModel, Page, SerialId, ServerTimed, Won
from app.domain.refund.types import RefundRule, RefundStage, RefundStatus


class RefundBasis(ApiModel):
    """반환 기준액 산정 근거. 공식은 기관 승인본이 나오면 바뀔 수 있다(PRD Q15)."""

    rule: RefundRule
    reference_date: date
    education_months: int | None = Field(default=None, ge=1)
    elapsed_months: int | None = Field(default=None, ge=0)
    monthly_fee: Won | None = None


class RefundPreview(ServerTimed):
    application_id: SerialId
    paid_amount: Won
    refundable_amount: Won = Field(
        description="서버가 산정한 반환 기준액. 회원은 금액을 입력하지 않는다(DV25)."
    )
    reserved_amount: Won = Field(description="이미 접수·승인·처리 중인 환불 합계")
    basis: RefundBasis


class RefundCreate(ApiModel):
    """수동 계좌환불이 필요할 때만 은행·예금주·계좌를 함께 보낸다. 셋 중 일부만 보내면 400이다(R15)."""

    application_id: SerialId
    reason: str | None = Field(default=None, max_length=500)
    bank_code: str | None = Field(default=None, min_length=1, max_length=20)
    account_holder: str | None = Field(default=None, min_length=1, max_length=50)
    account_number: str | None = Field(default=None, pattern=r"^[0-9-]{6,20}$")

    @model_validator(mode="after")
    def _account_all_or_none(self) -> "RefundCreate":
        given = [v is not None for v in (self.bank_code, self.account_holder, self.account_number)]
        if any(given) and not all(given):
            raise ValueError("은행, 예금주, 계좌번호는 함께 입력해야 합니다.")
        return self


class Refund(ApiModel):
    refund_id: SerialId
    application_id: SerialId
    course_name: str
    amount: Won
    status: RefundStatus
    stage: RefundStage
    reason: str | None = Field(default=None, description="보류·반려 사유")
    requested_at: AwareDatetime
    completed_at: AwareDatetime | None = None


class RefundPage(Page[Refund]):
    pass
