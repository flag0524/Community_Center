# 회원의 감면 사전심사 신청·결과 API 모델. 심사 내용과 처리자는 담지 않고 신청자가 알아야 하는 결과만 준다
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.reduction_types import ReductionStatus, ReductionType


class MyReductionSummary(ApiModel):
    review_id: SerialId
    cycle_name: str
    reduction_type: ReductionType
    status: ReductionStatus
    applied_on: date
    evidence_count: int = Field(ge=0)


class MyReduction(MyReductionSummary):
    valid_until: date | None = Field(description="승인된 심사의 유효 종료일")
    reject_reason: str | None = Field(description="반려된 심사의 사유")
    can_add_evidence: bool = Field(description="접수 상태일 때만 증빙을 추가·제거할 수 있다")
    can_withdraw: bool = Field(description="접수 상태일 때만 신청을 철회할 수 있다")


class MyReductionList(ApiModel):
    items: list[MyReductionSummary]


class ReductionCycleOption(ApiModel):
    id: SerialId
    name: str


class MyReductionOptions(ApiModel):
    cycles: list[ReductionCycleOption] = Field(description="신청할 수 있는 교육기수")
    can_apply: bool = Field(description="조리읍 거주가 확인된 회원만 신청할 수 있다")
    block_reason: str | None = Field(description="신청할 수 없을 때의 이유")


class MyReductionCreate(ApiModel):
    """사전심사 신청. 금액·비율은 받지 않고 서버가 정한다. 같은 기수에 접수·승인 건이 있으면 거절한다."""

    cycle_id: SerialId
    reduction_type: ReductionType
