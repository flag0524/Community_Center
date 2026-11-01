# 강좌 조회 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, ClockTime, Page, PageCriteria, SerialId, ServerTimed, Won
from app.domain.course.types import EducationState, ReceptionState, Weekday


class CategoryRef(ApiModel):
    category_id: SerialId
    name: str


class CategoryList(ApiModel):
    items: list[CategoryRef]


class CycleInfo(ApiModel):
    """현재 교육기수. 홈 배너와 강좌 목록의 '2026년 4분기 · 교육 10.01 — 12.31'에 쓴다."""

    name: str
    education_start: date
    education_end: date
    reception_start: AwareDatetime | None
    reception_end: AwareDatetime | None
    reception_state: ReceptionState = Field(
        description="서버가 판정한 접수 상태. 화면은 날짜를 비교하지 않는다."
    )


class ScheduleSlot(ApiModel):
    """정규 일정 한 행(TB_CORS_SCHDL). 요일마다 시간이 다르거나 반이 나뉜 강좌는 여러 행이 된다."""

    days: list[Weekday] = Field(min_length=1)
    start_time: ClockTime
    end_time: ClockTime
    label: str | None = Field(default=None, max_length=20, description="반 구분. 예를 들어 초급, 중급")


class CourseSummary(ApiModel):
    course_id: SerialId
    name: str
    # 미매핑 분류와 미확인 강사는 추정하지 않고 비운다(스키마 1.2).
    category: CategoryRef | None
    instructor_name: str | None
    schedules: list[ScheduleSlot]
    room: str | None
    education_start: date
    education_end: date
    reception_start: AwareDatetime
    reception_end: AwareDatetime
    reception_state: ReceptionState
    education_state: EducationState
    fee: Won
    capacity: int = Field(ge=1, description="모집 정원")
    remaining_seats: int | None = Field(default=None, ge=0, description="잔여석. 목록에 숫자를 노출한다(S4).")
    waiting_count: int = Field(ge=0)


class CourseListCriteria(PageCriteria):
    """목록이 어느 기수 기준인지(FN-012). 기수가 없으면 비어 있다."""

    cycle: CycleInfo | None = None


class CoursePage(Page[CourseSummary]):
    criteria: CourseListCriteria


class CourseDetail(CourseSummary, ServerTimed):
    cycle_name: str | None = Field(default=None, description="이 강좌가 속한 교육기수 이름")
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
