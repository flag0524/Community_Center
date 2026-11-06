# 관리자 문의·답변 API의 요청·응답 모델. 답변은 원글당 한 단계이고 수정하면 이력을 남긴다(FN-053)
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.content_types import AnswerAction
from app.domain.admin.education_schemas import Option
from app.domain.board.types import InquiryStatus


class AdminInquirySummary(ApiModel):
    inquiry_id: SerialId
    title: str
    category_name: str
    author_name: str = Field(description="작성 회원 이름은 가려서 준다.")
    is_private: bool
    status: InquiryStatus
    received_on: date


class AdminInquiryPage(Page[AdminInquirySummary]):
    pass


class InquiryAnswer(ApiModel):
    content: str
    related_link: str | None
    answered_by: str
    answered_at: AwareDatetime
    version: int = Field(ge=1)


class AnswerHistoryEntry(ApiModel):
    at: AwareDatetime
    by: str
    action: AnswerAction


class AdminInquiry(AdminInquirySummary):
    """비공개 원글의 본문은 권한 범위 안의 관리자에게만 준다. 비공개 범위는 답변에도 그대로 적용된다."""

    content: str
    answer: InquiryAnswer | None
    history: list[AnswerHistoryEntry]
    can_answer: bool = Field(description="답변 권한이 있을 때만 true다.")


class AdminInquiryCategoryList(ApiModel):
    items: list[Option]


class InquiryAnswerWrite(ApiModel):
    content: str = Field(min_length=1, max_length=4000)
    related_link: str | None = Field(
        default=None, max_length=300, description="사이트 안 경로(/로 시작)이거나 https 주소"
    )
    version: int = Field(
        ge=0, description="답변이 없으면 0, 있으면 화면이 읽은 답변 버전. 다르면 409(VERSION_CONFLICT)"
    )
