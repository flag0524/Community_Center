# 관리자 게시판 설정과 게시물 관리 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.board.types import BoardKey


class BoardSetting(ApiModel):
    """게시판별 정책. 이름과 키는 바꾸지 않고, 이력이 있는 게시판은 삭제 대신 사용중지한다."""

    board_key: BoardKey
    name: str
    member_write: bool = Field(description="회원이 글을 쓸 수 있는지(MBR_WRT_YN)")
    answer_enabled: bool = Field(description="답변을 쓸 수 있는지(ANS_USE_YN)")
    attach_enabled: bool = Field(description="첨부를 받을 수 있는지(ATCH_USE_YN)")
    allow_private: bool = Field(
        description="회원이 비공개 글을 쓸 수 있는지(스키마 개정 요청 R11의 추가 정책)"
    )
    in_use: bool = Field(description="사용 여부(USE_YN)")
    post_count: int = Field(ge=0)
    version: int = Field(ge=1)


class BoardSettingList(ApiModel):
    items: list[BoardSetting]


class BoardSettingUpdate(ApiModel):
    member_write: bool
    answer_enabled: bool
    attach_enabled: bool
    allow_private: bool
    in_use: bool
    version: int = Field(ge=1)


class AdminPostSummary(ApiModel):
    post_id: SerialId
    board_key: BoardKey
    title: str
    author_name: str = Field(description="회원 작성자는 가려서 준다.")
    pinned: bool
    registered_on: date


class AdminPostPage(Page[AdminPostSummary]):
    pass


class AdminPostWrite(ApiModel):
    """본문은 허용된 태그만 서버가 정리해 저장한다. 첨부 업로드는 첨부 설계 뒤에 더한다."""

    board_key: BoardKey
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=20000)
    pinned: bool = Field(description="상단공지(NTC_YN)")
    period_start: AwareDatetime | None = Field(default=None, description="게시 시작. 비우면 바로 게시")
    period_end: AwareDatetime | None = Field(default=None, description="게시 종료. 비우면 계속 게시")


class AdminPostUpdate(AdminPostWrite):
    version: int = Field(ge=1)


class AdminPost(AdminPostSummary):
    content: str
    period_start: AwareDatetime | None
    period_end: AwareDatetime | None
    member_authored: bool
    can_edit_content: bool = Field(description="관리자가 쓴 글만 내용을 고칠 수 있다.")
    version: int = Field(ge=1)
