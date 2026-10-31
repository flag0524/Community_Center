# 강좌 조회 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, ClockTime, Page, SerialId, ServerTimed, Won
from app.domain.course.types import ReceptionState, Weekday


class CategoryRef(ApiModel):
    category_id: SerialId
    name: str


class CourseSummary(ApiModel):
    course_id: SerialId
    name: str
    # 미매핑 분류와 미확인 강사는 추정하지 않고 비운다(스키마 1.2).
    category: CategoryRef | None
    instructor_name: str | None
    days: list[Weekday]
    start_time: ClockTime
    end_time: ClockTime
    room: str | None
    education_start: date
    education_end: date
    reception_start: AwareDatetime
    reception_end: AwareDatetime
    reception_state: ReceptionState
    fee: Won
    capacity: int = Field(ge=1, description="모집 정원")
    remaining_seats: int | None = Field(default=None, ge=0, description="잔여석. 목록에 숫자를 노출한다(S4).")
    waiting_count: int = Field(ge=0)


class CoursePage(Page[CourseSummary]):
    pass


class CourseDetail(CourseSummary, ServerTimed):
    wait_capacity: int = Field(ge=0)
    out_of_area_reception_start: AwareDatetime | None = Field(
        default=None, description="관외 신청자 접수 시작. 비어 있으면 관외 개방이 없다(G04)."
    )
    description: str | None = None
    has_plan: bool


class FileRef(ApiModel):
    file_id: SerialId
    name: str
    size_bytes: int = Field(ge=0)


class CoursePlan(ApiModel):
    course_id: SerialId
    plan_text: str | None = None
    plan_file: FileRef | None = None
