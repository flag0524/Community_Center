# 회원이 자기 업무(강사 지원서·문의)에 올리는 첨부의 응답 모델. 저장 위치와 해시는 담지 않는다
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.term_types import FileStatus


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
