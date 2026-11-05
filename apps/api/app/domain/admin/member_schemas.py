# 관리자 회원 조회·검토 기록 API의 요청·응답 모델. 회원 정보를 수정하는 필드는 없다(FN-065)
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.member_types import MemberReviewKind, MemberReviewState, MemberStatus
from app.domain.application.types import ApplicationDisplayState
from app.domain.member.types import ResidenceDeclared, ResidenceStatus
from app.domain.payment.types import PaymentStatus


class AdminMemberSummary(ApiModel):
    member_id: SerialId
    login_id: str
    name_masked: str = Field(description="이름은 가려서 준다.")
    residence_declared: ResidenceDeclared | None = Field(description="회원이 입력한 거주 구분(참고용)")
    residence_status: ResidenceStatus = Field(description="센터 담당자가 확인한 결과만 인정한다(PRD Q5).")
    joined_on: date
    status: MemberStatus


class AdminMemberPage(Page[AdminMemberSummary]):
    pass


class MemberApplication(ApiModel):
    application_no: str
    course_name: str
    display_state: ApplicationDisplayState
    payment_status: PaymentStatus | None


class MemberReview(ApiModel):
    review_id: SerialId
    kind: MemberReviewKind
    state: MemberReviewState
    reason: str
    recorded_by: str
    recorded_at: AwareDatetime
    closed_note: str | None
    closed_at: AwareDatetime | None


class AdminMember(AdminMemberSummary):
    phone_masked: str
    email_masked: str
    application_count: int = Field(ge=0)
    paid_total: Won = Field(description="결제완료 금액의 합(환불 전)")
    applications: list[MemberApplication]
    reviews: list[MemberReview]
    can_review: bool = Field(description="검토 기록을 남길 수 있는 권한이 있을 때만 true다.")


class RevealRequest(ApiModel):
    """가려진 연락처를 보려면 사유를 남긴다. 조회는 감사기록에 쌓인다."""

    reason: str = Field(min_length=5, max_length=300)


class MemberContact(ApiModel):
    phone: str
    email: str


class MemberReviewCreate(ApiModel):
    kind: MemberReviewKind
    reason: str = Field(min_length=1, max_length=500)


class MemberReviewClose(ApiModel):
    note: str = Field(min_length=1, max_length=500)


class ResidenceRecord(ApiModel):
    """거주지 확인 결과 기록. 확인 수행 권한 코드는 PRD Q5가 확정되기 전이다."""

    result: ResidenceStatus
    note: str = Field(min_length=1, max_length=300)
