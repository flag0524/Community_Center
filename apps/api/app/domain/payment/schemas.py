# 결제 요청·승인 확인·영수증 API의 요청·응답 모델
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, ServerTimed, Won
from app.domain.application.types import ApplicationDisplayState
from app.domain.payment.types import PaymentMethod, PaymentStatus


class PaymentRequestCreate(ApiModel):
    method: PaymentMethod


class PaymentRequestResult(ServerTimed):
    payment_id: SerialId
    order_no: str
    amount: Won
    method: PaymentMethod
    deadline: AwareDatetime = Field(description="결제기한. 새로고침·재접속·수단 변경으로 늘어나지 않는다.")
    gateway: str = Field(description="결제대행사 식별자. 대행사는 계약 후 확정(TBD).")
    gateway_params: dict[str, str] = Field(description="결제창을 여는 데 필요한 값")


class PaymentConfirmRequest(ApiModel):
    """결제창 인증 뒤 브라우저가 넘기는 값. 금액은 저장값과 대조에만 쓴다(R13)."""

    order_no: str = Field(min_length=1, max_length=64)
    payment_key: str = Field(min_length=1, max_length=200)
    amount: Won


class PaymentConfirmResult(ServerTimed):
    payment_id: SerialId
    status: PaymentStatus
    application_id: SerialId
    application_display_state: ApplicationDisplayState


class Receipt(ApiModel):
    payment_id: SerialId
    application_id: SerialId
    course_name: str
    method: PaymentMethod
    amount: Won
    approval_no: str
    approved_at: AwareDatetime
    payer_name: str
