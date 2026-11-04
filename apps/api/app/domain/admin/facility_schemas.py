# 관리자 센터·강의실 관리 API의 요청·응답 모델
from pydantic import Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.education_types import FacilityKind


class FacilityWrite(ApiModel):
    kind: FacilityKind
    parent_id: SerialId | None = Field(description="강의실이면 상위 센터다. 센터이면 null이다.")
    name: str = Field(min_length=1, max_length=100)
    floor: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=200, description="센터만 입력한다.")
    is_public: bool
    in_use: bool = Field(description="사용 중지하면 기존 일정은 유지되고 새 일정에는 배정할 수 없다(FN-050).")


class FacilityUpdate(FacilityWrite):
    version: int = Field(ge=1)


class Facility(FacilityWrite):
    facility_id: SerialId
    version: int = Field(ge=1)
    schedule_count: int = Field(ge=0, description="이 시설을 쓰는 일정 수")


class FacilityList(ApiModel):
    """센터와 강의실 전체다. 화면이 트리로 묶는다."""

    items: list[Facility]
