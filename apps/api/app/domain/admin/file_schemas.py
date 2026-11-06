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
