# 첨부파일 응답 모델(회원 업무의 첨부, 관리자 소유 업무 화면의 첨부). 저장 위치와 해시는 담지 않는다
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, SerialId
from app.domain.file.types import FileStatus


class MyFile(ApiModel):
    file_id: SerialId
    file_name: str
    size_bytes: int = Field(ge=0)
    status: FileStatus
    registered_on: date
    block_reason: str | None = Field(description="차단된 파일의 사유. 탐지 이름은 노출하지 않는다")


class MyFileList(ApiModel):
    """한도는 서버가 정해 알려 주고 화면은 이 값으로 안내한다."""

    items: list[MyFile]
    can_edit: bool = Field(description="지금 파일을 추가·제거할 수 있는지. 업무가 잠겼으면 false")
    max_files: int = Field(ge=1)
    max_bytes: int = Field(ge=1)
    allowed_extensions: list[str] = Field(description="허용 확장자(점 없이 소문자)")


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
