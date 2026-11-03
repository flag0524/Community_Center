# 수강신청 API의 요청·응답 모델
from pydantic import AwareDatetime, Field

from app.core.errors import ErrorCode
from app.core.schema import ApiModel, Page, SerialId, ServerTimed, Won
from app.domain.application.types import ApplicationDisplayState, ApplicationStatus
from app.domain.course.schemas import CourseSummary
from app.domain.payment.types import PaymentStatus


class Eligibility(ApiModel):
    can_apply: bool
    reason_code: ErrorCode | None = None
    reason_message: str | None = None


class ApplyPreview(ServerTimed):
    course: CourseSummary
    fee: Won
    reduction_amount: Won
    payable_amount: Won
    payment_window_seconds: int = Field(description="자리 배정 뒤 결제할 수 있는 시간. 600초.")
    eligibility: Eligibility
    resident_priority_active: bool
    already_applied: bool


class ApplicationCreate(ApiModel):
    """신청 요청에는 금액 필드가 없다. 금액은 서버가 산정한다(R09)."""

    course_id: SerialId


class ApplicationSummary(ApiModel):
    application_id: SerialId
    course: CourseSummary
    status: ApplicationStatus
    display_state: ApplicationDisplayState
    waiting_rank: int | None = Field(default=None, ge=1, description="대기 순번. 대기 상태에서만 값이 있다.")
    payment_status: PaymentStatus | None = None
    payment_id: SerialId | None = Field(
        default=None, description="가장 최근 결제 일련번호. 영수증 조회에 쓴다."
    )
    fee: Won
    reduction_amount: Won
    payable_amount: Won
    applied_at: AwareDatetime
    seat_assigned_at: AwareDatetime | None = None
    payment_deadline: AwareDatetime | None = None
    # 가능 여부는 서버가 판정한다. 화면은 이 값을 그대로 따른다.
    can_cancel: bool
    can_pay: bool
    can_request_refund: bool


class Application(ApplicationSummary, ServerTimed):
    pass


class ApplicationPage(Page[ApplicationSummary]):
    pass
