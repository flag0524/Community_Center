# 관리자 홈·센터 콘텐츠 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.content_types import ContentType


class ContactFields(ApiModel):
    """연락처 유형의 구조 입력. 계약 뒤 확정되는 값이라 모두 비어 있을 수 있다(FN-011, FN-072)."""

    phone: str | None = Field(default=None, max_length=40, description="수강문의 번호")
    admin_office_phone: str | None = Field(default=None, max_length=40, description="행정복지센터 대표번호")
    postal_code: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=200)
    floor_info: str | None = Field(default=None, max_length=100)
    open_hours: str | None = Field(default=None, max_length=200)
    parking: str | None = Field(default=None, max_length=200)


class AdminContentSummary(ApiModel):
    content_id: SerialId
    content_type: ContentType
    title: str
    posted: bool
    period_start: AwareDatetime | None
    period_end: AwareDatetime | None
    sort_seq: int
    updated_on: date


class AdminContentPage(Page[AdminContentSummary]):
    can_create: bool = Field(description="연락처처럼 하나만 둘 수 있는 유형은 이미 있으면 false다.")


class AdminContentWrite(ApiModel):
    """이미지 업로드는 첨부 설계 뒤에 더한다. 링크는 사이트 안 경로(/로 시작)이거나 https 주소다."""

    content_type: ContentType
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=20000, description="연락처 유형은 본문 대신 구조 입력을 쓴다.")
    url: str | None = Field(default=None, max_length=2000)
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime | None = None
    posted: bool
    sort_seq: int = Field(ge=0, le=9999)
    contact: ContactFields | None = Field(default=None, description="연락처 유형일 때만 받는다.")


class AdminContentUpdate(AdminContentWrite):
    version: int = Field(ge=1)


class AdminContent(AdminContentSummary):
    body: str
    url: str | None
    contact: ContactFields | None
    version: int = Field(ge=1)
