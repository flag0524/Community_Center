# 게시판 목록·상세·첨부 API의 응답 모델
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, CategoryCode, Page, SerialId
from app.domain.board.types import BoardKey, InquiryStatus


class PostFile(ApiModel):
    """게시물 첨부. 내려받기는 소유 게시물의 현재 상태로 판정하며 비공개가 되면 바로 막힌다(NF-SER-002)."""

    file_id: SerialId
    name: str
    size_bytes: int = Field(ge=0)
    content_type: str


class PostImage(ApiModel):
    file_id: SerialId
    alt: str


class PostSummary(ApiModel):
    post_id: SerialId
    board: BoardKey
    title: str
    published_at: AwareDatetime
    pinned: bool = Field(description="상단공지. 목록에서 날짜 대신 '공지'로 구분해 보인다.")
    body: str | None = Field(default=None, description="FAQ처럼 목록에서 본문을 바로 보이는 게시판만 채운다.")
    primary_file: PostFile | None = Field(default=None, description="자료실의 '자료 보기'가 여는 첫 첨부")
    thumbnail: PostImage | None = Field(default=None, description="갤러리 목록의 대표 이미지")


class PostFact(ApiModel):
    """공고의 핵심 항목 한 줄(교육기간, 접수기간 등)."""

    label: str
    value: str
    url: str | None = None


class PostDetail(ApiModel):
    post_id: SerialId
    board: BoardKey
    title: str
    published_at: AwareDatetime
    pinned: bool
    body: str = Field(description="문단은 빈 줄로 나눈다.")
    facts: list[PostFact]
    attachments: list[PostFile]
    images: list[PostImage]


class PostPage(Page[PostSummary]):
    pass


class InquiryCategory(ApiModel):
    """문의 분류. 값은 공통코드(IQ)에서 오며 화면에 고정하지 않는다(PRD Q26)."""

    category_id: CategoryCode
    name: str


class InquiryCategoryList(ApiModel):
    items: list[InquiryCategory]


class InquirySummary(ApiModel):
    """다른 회원의 비공개 문의는 서버가 제목과 작성자를 가려 내려준다."""

    post_id: SerialId
    category_name: str
    title: str
    author_name: str
    status: InquiryStatus
    is_private: bool
    is_mine: bool
    published_at: AwareDatetime


class InquiryPage(Page[InquirySummary]):
    pass


class InquiryAnswer(ApiModel):
    body: str
    answered_at: AwareDatetime


class InquiryDetail(ApiModel):
    post_id: SerialId
    category_id: CategoryCode
    category_name: str
    title: str
    body: str
    author_name: str
    status: InquiryStatus
    is_private: bool
    published_at: AwareDatetime
    answer: InquiryAnswer | None = Field(description="센터 답변. 원글의 비공개 범위가 답변에도 같다.")
    can_edit: bool = Field(description="답변 전의 본인 문의만 고칠 수 있다.")
    can_delete: bool


class InquiryWrite(ApiModel):
    category_id: CategoryCode
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=2000)
    is_private: bool


class ReviewSummary(ApiModel):
    post_id: SerialId
    title: str
    author_name: str
    course_name: str
    is_mine: bool
    published_at: AwareDatetime


class ReviewPage(Page[ReviewSummary]):
    pass


class ReviewDetail(ApiModel):
    post_id: SerialId
    course_id: SerialId
    course_name: str
    title: str
    body: str
    author_name: str
    published_at: AwareDatetime
    can_edit: bool
    can_delete: bool


class ReviewWrite(ApiModel):
    course_id: SerialId
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=2000)


class ReviewableCourse(ApiModel):
    course_id: SerialId
    name: str


class ReviewableCourseList(ApiModel):
    """후기를 쓸 수 있는 강좌. 수강확정인 신청의 강좌만이다(PRD Q19 가정)."""

    items: list[ReviewableCourse]
