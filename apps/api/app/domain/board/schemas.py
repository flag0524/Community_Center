# 게시판 목록·상세·첨부 API의 응답 모델
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.board.types import BoardKey


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
