# 홈 화면과 센터 연락처 API의 응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, ServerTimed
from app.domain.course.schemas import CategoryRef
from app.domain.course.types import ReceptionState


class PostBrief(ApiModel):
    post_id: SerialId
    title: str
    published_at: AwareDatetime
    pinned: bool


class CategoryOverview(ApiModel):
    category: CategoryRef
    reception_state: ReceptionState
    reception_start: AwareDatetime | None
    reception_end: AwareDatetime | None
    education_start: date | None
    education_end: date | None
    course_names: list[str]


class CycleInfo(ApiModel):
    """홈 배너에 보이는 현재 교육기수. 시안의 '2026년 4분기 교육프로그램'에 해당한다."""

    name: str
    education_start: date
    education_end: date
    reception_start: AwareDatetime | None
    reception_end: AwareDatetime | None
    reception_state: ReceptionState = Field(
        description="서버가 판정한 접수 상태. 화면은 날짜를 비교하지 않는다."
    )


class HomeResponse(ServerTimed):
    cycle: CycleInfo | None = None
    categories: list[CategoryOverview]
    notices: list[PostBrief]


class ContactResponse(ApiModel):
    """연락처는 계약 후 확정되는 값이라 모두 비어 있을 수 있다. 비어 있으면 화면은 '확인 필요'로 표시한다."""

    phone: str | None = None
    admin_office_phone: str | None = None
    postal_code: str | None = None
    address: str | None = None
    floor_info: str | None = None
    open_hours: str | None = None
    parking: str | None = None
