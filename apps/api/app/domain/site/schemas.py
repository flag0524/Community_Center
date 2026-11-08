# 홈 화면과 센터 연락처 API의 응답 모델
from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, ServerTimed
from app.domain.course.schemas import CategoryRef, CycleInfo
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


class HomeImage(ApiModel):
    url: str = Field(description="공개 이미지 주소. 게시 중인 콘텐츠의 이미지만 받을 수 있다")
    alt: str = Field(description="이미지를 설명하는 대체 문구")


class HomeVisual(ApiModel):
    """홈 첫 화면의 대표 문구와 사진. 사용 범위가 확인된 사진만 담고 없으면 이미지는 null이다."""

    title: str
    body: str | None
    link_url: str | None = Field(description="사이트 안 경로(/로 시작)나 https 주소")
    image: HomeImage | None


class HomeBanner(ApiModel):
    content_id: SerialId
    title: str
    link_url: str | None
    image: HomeImage | None


class HomePopup(ApiModel):
    """게시기간 안의 팝업. `오늘 하루 보지 않기`는 화면이 콘텐츠 번호로 기억한다."""

    content_id: SerialId
    title: str
    body: str | None
    link_url: str | None
    image: HomeImage | None


class HomeResponse(ServerTimed):
    cycle: CycleInfo | None = None
    categories: list[CategoryOverview]
    notices: list[PostBrief]
    visual: HomeVisual | None = None
    banners: list[HomeBanner]
    popups: list[HomePopup]


class ContactResponse(ApiModel):
    """연락처는 계약 후 확정되는 값이라 모두 비어 있을 수 있다. 비어 있으면 화면은 '확인 필요'로 표시한다."""

    phone: str | None = None
    admin_office_phone: str | None = None
    postal_code: str | None = None
    address: str | None = None
    floor_info: str | None = None
    open_hours: str | None = None
    parking: str | None = None


class ContentSlug(StrEnum):
    """서버가 문서로 내려주는 안내·센터소개 글. 새 유형이 필요하면 스키마 개정을 먼저 요청한다."""

    GUIDE_APPLY = "guide-apply"
    GUIDE_REFUND = "guide-refund"
    CENTER_HISTORY = "center-history"
    CENTER_FACILITY = "center-facility"


class ContentLink(ApiModel):
    label: str
    url: str = Field(description="사이트 안 경로(/로 시작)이거나 외부 주소")


class ContentStep(ApiModel):
    title: str
    body: str


class ContentItem(ApiModel):
    """연혁처럼 '날짜 + 내용' 한 줄."""

    label: str | None = None
    text: str


class ContentTable(ApiModel):
    columns: list[str]
    rows: list[list[str]]


class ContentSection(ApiModel):
    """한 절. 화면은 문단, 단계, 항목, 표, 링크 순으로 그린다."""

    heading: str
    paragraphs: list[str]
    steps: list[ContentStep]
    items: list[ContentItem]
    table: ContentTable | None = None
    links: list[ContentLink]


class ContentDocument(ApiModel):
    slug: ContentSlug
    title: str
    subtitle: str | None = None
    sections: list[ContentSection]
    updated_on: date | None = None
