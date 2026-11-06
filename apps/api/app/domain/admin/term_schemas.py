# 관리자 약관·동의문 버전 관리 API의 요청·응답 모델
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.term_types import TermStatus
from app.domain.member.types import TermType


class TermVersionSummary(ApiModel):
    version_id: SerialId
    term_type: TermType
    version_name: str
    effective_on: date = Field(description="시행일")
    essential: bool = Field(description="필수 동의 여부")
    status: TermStatus
    posted_on: date | None
    agreed_count: int = Field(ge=0, description="이 버전에 동의한 회원 수")


class TermVersionPage(Page[TermVersionSummary]):
    pass


class TermVersion(TermVersionSummary):
    body: str
    content_hash: str | None = Field(
        description="확정되면 SHA-256 문안 해시가 고정된다. 검토 중이면 null이다."
    )
    version: int = Field(ge=1)
    can_edit: bool = Field(description="검토 상태일 때만 true다. 확정·게시된 문안은 고칠 수 없다.")
    can_fix: bool
    can_publish: bool


class TermVersionCreate(ApiModel):
    """새 버전은 검토 상태로 만든다. 복제 원본을 주고 본문을 비우면 원본 본문을 복사한다."""

    version_name: str = Field(min_length=1, max_length=40)
    effective_on: date
    essential: bool
    body: str | None = Field(default=None, max_length=50000)
    base_version_id: SerialId | None = Field(default=None, description="복제할 이전 버전")


class TermVersionUpdate(ApiModel):
    version_name: str = Field(min_length=1, max_length=40)
    effective_on: date
    essential: bool
    body: str = Field(min_length=1, max_length=50000)
    version: int = Field(ge=1)


class TermVersionAction(ApiModel):
    """확정·게시 요청. 읽은 버전이 다르면 409다."""

    version: int = Field(ge=1)
