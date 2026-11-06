# 관리자 감면 사전심사 API의 요청·응답 모델. 회원 이름은 가리고 증빙 열람은 감사기록을 남긴다
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.reduction_types import ReductionDecision, ReductionStatus, ReductionType
from app.domain.admin.term_types import FileStatus


class ReductionReviewSummary(ApiModel):
    review_id: SerialId
    member_name: str = Field(description="가려진 회원 이름")
    cycle_name: str
    reduction_type: ReductionType
    evidence_count: int = Field(ge=0)
    applied_on: date = Field(description="심사 신청일")
    status: ReductionStatus


class ReductionReviewPage(Page[ReductionReviewSummary]):
    pass


class ReductionEvidence(ApiModel):
    file_id: SerialId
    file_name: str
    size_bytes: int = Field(ge=0)
    status: FileStatus


class EvidenceView(ApiModel):
    at: AwareDatetime
    by: str = Field(description="열람한 담당자")
    file_name: str


class ReductionReview(ReductionReviewSummary):
    residence_confirmed: bool = Field(description="조리읍 거주 확인 결과. 확인된 회원만 승인할 수 있다.")
    evidence: list[ReductionEvidence]
    evidence_views: list[EvidenceView] = Field(description="증빙 열람 감사기록")
    reviewed_by: str | None
    reviewed_at: AwareDatetime | None
    review_note: str | None
    reject_reason: str | None
    valid_until: date | None = Field(description="승인의 유효 종료일")
    version: int = Field(ge=1)
    can_decide: bool = Field(description="접수 상태이고 심사 권한이 있을 때만 true")
    can_re_review: bool = Field(description="승인·반려된 건만 새 심사건을 만들 수 있다.")
    can_view_evidence: bool = Field(description="심사 권한이 있을 때만 증빙을 열람할 수 있다.")


class EvidenceViewRequest(ApiModel):
    file_id: SerialId


class ReductionDecisionRequest(ApiModel):
    """승인은 유효기간이, 반려는 사유가 필수다. 결정한 뒤에는 내용과 증빙을 고칠 수 없다."""

    decision: ReductionDecision
    review_note: str | None = Field(default=None, max_length=4000)
    reject_reason: str | None = Field(default=None, max_length=4000)
    valid_until: date | None = None
    version: int = Field(ge=1)


class ReductionHistoryRow(ApiModel):
    history_id: SerialId
    decided_at: AwareDatetime
    member_name: str
    cycle_name: str
    result: ReductionDecision
    amount: Won | None = Field(description="판정 당시 감면금액")
    reason: str | None
    decided_by: str
    evidence_count: int = Field(ge=0)
    application_no: str | None = Field(description="이 판정이 쓰인 수강신청")


class ReductionHistoryPage(Page[ReductionHistoryRow]):
    pass
