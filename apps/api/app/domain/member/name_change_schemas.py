# 회원 이름 변경 요청·검토 API의 요청·응답 모델(ADR-090)
from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId


class NameChangeState(StrEnum):
    PENDING = "PENDING"  # 검토 중
    APPROVED = "APPROVED"  # 승인해 이름을 바꿈
    REJECTED = "REJECTED"  # 반려


class NameChangeFilter(StrEnum):
    PENDING = "PENDING"  # 검토 중인 요청
    DECIDED = "DECIDED"  # 승인하거나 반려해 처리를 마친 요청


class NameChangeCreate(ApiModel):
    new_name: str = Field(min_length=1, max_length=50, description="바꾸려는 이름")
    reason: str = Field(min_length=1, max_length=500, description="변경 사유. 증빙은 센터에서 직접 확인한다")
    password: str = Field(min_length=1, max_length=64, description="본인 확인용 현재 비밀번호")


class NameChangeDecide(ApiModel):
    note: str | None = Field(default=None, max_length=300, description="처리 메모. 회원에게도 보인다")


class MyNameChange(ApiModel):
    request_id: SerialId
    requested_name: str
    reason: str
    state: NameChangeState
    requested_at: AwareDatetime
    decided_at: AwareDatetime | None
    decision_note: str | None


class MyNameChangeList(ApiModel):
    items: list[MyNameChange] = Field(description="최근 순 20건까지")


class AdminNameChange(MyNameChange):
    member_id: SerialId
    login_id: str
    current_name_masked: str = Field(description="현재 이름. 가려서 준다")
    decided_by: str | None


class AdminNameChangeList(ApiModel):
    items: list[AdminNameChange]
