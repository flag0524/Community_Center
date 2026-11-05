# 관리자 수강신청 조회와 대기·자리 배정 조회 API의 응답 모델. 둘 다 조회 전용이다
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.application_types import ReplayOutcome, SmsResult
from app.domain.application.types import ApplicationDisplayState, ApplicationStatus
from app.domain.payment.types import PaymentMethod, PaymentStatus
from app.domain.refund.types import RefundStatus


class AdminApplicationSummary(ApiModel):
    application_id: SerialId
    application_no: str
    course_name: str
    applicant_name: str = Field(description="신청자 이름은 가려서 준다.")
    status: ApplicationStatus
    display_state: ApplicationDisplayState = Field(description="신청·결제 상태를 합쳐 서버가 정한 표시 상태")
    payment_status: PaymentStatus | None
    refund_status: RefundStatus | None
    applied_at: AwareDatetime


class AdminApplicationPage(Page[AdminApplicationSummary]):
    pass


class HistoryEntry(ApiModel):
    at: AwareDatetime
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    actor: str = Field(description="SYSTEM, 회원, 또는 처리한 관리자 이름")
    note: str | None


class LinkedPayment(ApiModel):
    order_no: str
    method: PaymentMethod
    amount: Won
    status: PaymentStatus
    approved_at: AwareDatetime | None


class LinkedRefund(ApiModel):
    refund_no: str
    amount: Won
    status: RefundStatus


class ReplayEntry(ApiModel):
    at: AwareDatetime
    outcome: ReplayOutcome


class AdminApplication(AdminApplicationSummary):
    """신청 원장 전체 이력이다. 관리자가 상태를 직접 바꾸는 기능은 없다."""

    course_id: SerialId
    cycle_name: str
    waiting_order: int | None = Field(description="대기 중일 때의 순번")
    seat_allotted_at: AwareDatetime | None = Field(description="자리 배정 시각(DB 시각)")
    payment_deadline_at: AwareDatetime | None = Field(description="배정 시각 + 600초")
    history: list[HistoryEntry]
    payment: LinkedPayment | None
    refund: LinkedRefund | None
    replays: list[ReplayEntry] = Field(description="멱등 재요청 기록")


class WaitlistCourse(ApiModel):
    course_id: SerialId
    course_name: str
    capacity: int
    occupied: int = Field(ge=0, description="ES.HOLD + ES.CONFIRM 신청 수(ADR-028)")
    wait_count: int = Field(ge=0)
    next_wait_order: int | None
    last_promoted_at: AwareDatetime | None


class WaitlistPage(Page[WaitlistCourse]):
    pass


class Waiter(ApiModel):
    order: int = Field(ge=1)
    application_no: str
    applicant_name: str
    applied_at: AwareDatetime


class Promotion(ApiModel):
    """자동 승격 이력. 수동 승격은 없다(FN-035)."""

    promoted_at: AwareDatetime
    application_no: str
    deadline_at: AwareDatetime
    sms_result: SmsResult


class WaitlistDetail(WaitlistCourse):
    waiters: list[Waiter]
    promotions: list[Promotion]
