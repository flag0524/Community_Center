# 관리자 보존·파기 검토 API의 요청·응답 모델. 정산자료는 법정 보존 대상이라 목록에서 제외하고 그 사실을 알린다
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.retention_types import RetentionState, RetentionTarget


class RetentionItem(ApiModel):
    item_id: SerialId
    target: RetentionTarget
    count: int = Field(ge=0, description="처리 대상 건수")
    base_date: date | None = Field(description="보존기간을 세는 기준일")
    due_on: date | None = Field(description="예정일. 보존기간이 정해지지 않았으면 null")
    state: RetentionState


class RetentionExclusion(ApiModel):
    label: str
    reason: str


class RetentionList(ApiModel):
    items: list[RetentionItem]
    exclusions: list[RetentionExclusion] = Field(description="이 목록에서 제외하는 자료와 이유")


class RetentionExecution(ApiModel):
    at: AwareDatetime
    by: str = Field(description="실행한 담당자. 자동 작업은 SYSTEM")
    processed: int = Field(ge=0)


class RetentionDetail(RetentionItem):
    rule: str = Field(description="보존 규칙 설명")
    fields: list[str] = Field(description="파기 또는 비식별로 처리하는 항목")
    executions: list[RetentionExecution] = Field(description="실행 결과 감사기록")
    can_execute: bool = Field(description="예정일이 지났고 대상이 있으며 실행 권한이 있을 때만 true")


class RetentionExecute(ApiModel):
    """사용자가 확인한 대상 건수. 서버가 다시 세어 다르면 409다."""

    expected_count: int = Field(ge=1)
