# 개인식별 명단 내보내기 요청 모델. 대상 목록의 조회 조건을 그대로 받고 파일은 서버에 남기지 않는다
from pydantic import Field

from app.core.schema import ApiModel
from app.domain.admin.export_types import PiiExportTarget


class PiiExportRequest(ApiModel):
    target: PiiExportTarget
    q: str | None = Field(default=None, max_length=100, description="목록의 검색어")
    status: str | None = Field(default=None, max_length=30, description="회원 상태 또는 신청 상태")
    cycle_id: str | None = Field(default=None, pattern=r"^[0-9]{1,22}$", description="수강신청만")
    course_id: str | None = Field(default=None, pattern=r"^[0-9]{1,22}$", description="수강신청만")
    payment_status: str | None = Field(default=None, max_length=30, description="수강신청만")
    from_date: str | None = Field(
        default=None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$", description="수강신청만"
    )
    to_date: str | None = Field(
        default=None, alias="to", pattern=r"^\d{4}-\d{2}-\d{2}$", description="수강신청만"
    )
