# 관리자 강사 심사 API의 요청·응답 모델
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.education_types import ApplicationSource, ReviewStatus


class InstructorReviewSummary(ApiModel):
    application_id: SerialId
    applicant_name: str
    desired_course: str
    received_on: date
    status: ReviewStatus
    is_public: bool


class InstructorReviewPage(Page[InstructorReviewSummary]):
    pass


class InstructorReviewCreate(ApiModel):
    """방문·외부로 받은 지원서를 관리자가 대신 등록한다. 온라인 지원은 주민 화면에서 들어온다."""

    recruitment_id: SerialId = Field(description="지원서가 속하는 모집 공고(스키마상 필수)")
    applicant_name: str = Field(min_length=1, max_length=50)
    phone: str = Field(
        pattern=r"^01[0-9]{8,9}$",
        description="지원자 휴대전화(숫자만). 암호화해 저장하고 응답·목록·작업이력에 담지 않는다.",
    )
    member_login_id: str | None = Field(
        default=None,
        max_length=20,
        description="이미 가입한 지원자의 아이디. 연결해야 승인할 수 있다(강사는 회원이어야 한다).",
    )
    desired_course: str = Field(min_length=1, max_length=100)
    career: str = Field(min_length=1, max_length=2000)
    source: ApplicationSource


class InstructorReview(ApiModel):
    application_id: SerialId
    applicant_name: str
    desired_course: str
    category_name: str | None
    career: str
    source: ApplicationSource
    received_on: date
    status: ReviewStatus
    is_public: bool
    reason: str | None = Field(description="반려·활동중지 사유")
    memo: str | None = Field(description="검토 메모. 개인정보는 적지 않는다.")
    version: int = Field(ge=1)
    can_review: bool = Field(description="심사 권한이 있을 때만 true다. 화면은 값을 해석하지 않는다.")


class InstructorReviewWrite(ApiModel):
    """승인해도 강좌 배정이나 관리자 권한은 자동으로 부여되지 않는다(FN-051)."""

    status: ReviewStatus
    reason: str | None = Field(default=None, max_length=500)
    is_public: bool = Field(description="승인된 강사만 공개할 수 있다.")
    memo: str | None = Field(default=None, max_length=1000)
    version: int = Field(ge=1)
