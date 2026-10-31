# 홈 화면과 센터 연락처 API의 응답 모델
from datetime import date

from pydantic import AwareDatetime

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


class HomeResponse(ServerTimed):
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
