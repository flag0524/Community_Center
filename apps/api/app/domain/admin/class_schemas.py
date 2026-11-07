# 관리자 강좌분류 API의 요청·응답 모델. 이름 정규화는 서버가 하고 연결 강좌 수 확인 실패는 0과 구분한다
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.class_types import ClassHistoryAction


class CourseClass(ApiModel):
    class_id: SerialId
    name: str
    sort_seq: int = Field(ge=0)
    active: bool
    course_count: int | None = Field(
        description="연결 강좌 수. 확인하지 못하면 null이고 0과 구분한다(CLSF-02)"
    )
    version: int = Field(ge=1)
    can_deactivate: bool = Field(description="활성이고 연결 강좌가 없음을 확인했을 때만 true")
    can_delete: bool = Field(description="연결 강좌가 없음을 확인했을 때만 true")


class CourseClassList(ApiModel):
    items: list[CourseClass]
    can_edit: bool = Field(description="분류를 만들고 고칠 수 있는지")
    uncategorized_count: int | None = Field(description="분류가 없는 기존 강좌 수. 자동으로 옮기지 않는다")


class CourseClassWrite(ApiModel):
    name: str = Field(min_length=1, description="128자를 넘으면 절단하지 않고 거절한다(CLSF-01)")
    sort_seq: int = Field(ge=0)


class CourseClassUpdate(CourseClassWrite):
    version: int = Field(ge=1)


class CourseClassAction(ApiModel):
    version: int = Field(ge=1)


class ClassHistoryEntry(ApiModel):
    at: AwareDatetime
    by: str
    action: ClassHistoryAction
    before: str | None = Field(description="바뀌기 전 값. 등록이면 null")
    after: str | None = Field(description="바뀐 뒤 값. 삭제면 null")


class ClassHistoryList(ApiModel):
    items: list[ClassHistoryEntry]
