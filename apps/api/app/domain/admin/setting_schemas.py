# 관리자 운영 설정(읽기 전용)과 공통 코드 API의 요청·응답 모델
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.setting_types import OperRuleStatus


class SettingSummary(ApiModel):
    setting_id: SerialId
    name: str = Field(description="항목명")
    value: str = Field(description="현재 기준 요약")
    status: OperRuleStatus
    updated_on: date


class SettingPage(Page[SettingSummary]):
    pass


class SettingDetail(SettingSummary):
    body: str = Field(description="기준값·설명·근거")
    version: int = Field(ge=1, description="기준이 바뀔 때마다 새 버전이 쌓인다")


class CodeGroup(ApiModel):
    id: str = Field(max_length=20)
    name: str


class CodeGroupList(ApiModel):
    items: list[CodeGroup]


class CodeRow(ApiModel):
    code: str = Field(max_length=12, description="코드값. 읽기 전용")
    name: str = Field(max_length=100, description="표시명")
    sort_seq: int = Field(ge=0)
    use: bool
    ref_count: int | None = Field(
        description="이 코드를 쓰는 업무 건수. 확인하지 못하면 null이고 0과 구분한다"
    )


class CodeList(ApiModel):
    group: CodeGroup
    items: list[CodeRow]


class CodeRowUpdate(ApiModel):
    code: str = Field(max_length=12)
    name: str = Field(min_length=1, max_length=100)
    sort_seq: int = Field(ge=0)
    use: bool


class CodeUpdate(ApiModel):
    """한 그룹의 표시명·순서·사용 여부만 고친다. 코드값과 그룹은 바꾸지 않고 코드를 지우지 않는다."""

    group_id: str = Field(max_length=20)
    items: list[CodeRowUpdate] = Field(min_length=1)
