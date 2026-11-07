# 관리자 첨부파일 조회 API의 응답 모델. 조회 전용이며 파일 올리기·내려받기는 소유 업무 화면에서 한다
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.term_types import FileOwnerKind, FilePurpose, FileStatus


class AdminFileSummary(ApiModel):
    file_id: SerialId
    file_name: str
    owner_kind: FileOwnerKind
    owner_label: str = Field(description="소유 업무의 제목")
    size_bytes: int = Field(ge=0)
    status: FileStatus
    registered_on: date


class AdminFilePage(Page[AdminFileSummary]):
    pass


class DownloadRecord(ApiModel):
    at: AwareDatetime
    by: str = Field(description="내려받은 사람. 회원 이름은 가려서 준다.")
    by_admin: bool


class AdminFile(AdminFileSummary):
    purpose: FilePurpose
    mime_type: str
    hash_prefix: str = Field(description="파일 해시의 앞부분")
    block_reason: str | None = Field(description="차단된 파일의 사유")
    downloads: list[DownloadRecord] = Field(description="내려받기 감사기록(NF-SER-002)")


class OwnerFile(ApiModel):
    """소유 업무 화면에 보이는 첨부. 저장 위치와 해시는 담지 않는다."""

    file_id: SerialId
    file_name: str
    size_bytes: int = Field(ge=0)
    status: FileStatus
    registered_on: date
    block_reason: str | None = Field(description="차단된 파일의 사유. 탐지 이름은 노출하지 않는다")


class OwnerFileList(ApiModel):
    """한도는 서버가 정해 알려 주고 화면은 이 값으로 안내한다."""

    items: list[OwnerFile]
    can_edit: bool = Field(description="지금 파일을 추가·제거할 수 있는지. 소유 업무가 잠겼으면 false")
    max_files: int = Field(ge=1, description="소유 업무당 파일 개수 한도")
    max_bytes: int = Field(ge=1, description="파일당 크기 한도")
    allowed_extensions: list[str] = Field(description="허용 확장자(점 없이 소문자)")
