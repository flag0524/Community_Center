# 관리자 교육기수·강좌 관리 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId, Won
from app.domain.admin.education_types import CourseAdminStatus, CycleStatus
from app.domain.course.types import EducationState, ReceptionState


class CycleWrite(ApiModel):
    name: str = Field(min_length=1, max_length=50)
    year: int = Field(ge=2020, le=2100)
    order: int = Field(ge=1, le=20, description="차수. 양수(FN-047)")
    reception_start: date
    reception_end: date
    education_start: date
    education_end: date
    status: CycleStatus


class CycleUpdate(CycleWrite):
    version: int = Field(ge=1, description="화면이 읽은 RCRD_VER. 다르면 409(VERSION_CONFLICT)")


class Cycle(CycleWrite):
    cycle_id: SerialId
    version: int = Field(ge=1)
    course_count: int = Field(ge=0, description="연결 강좌 수. 기간을 바꿀 때 영향 경고에 쓴다.")


class CyclePage(Page[Cycle]):
    pass


class Option(ApiModel):
    id: SerialId
    name: str


class CourseOptions(ApiModel):
    """강좌 등록·수정과 목록 조건의 선택지. 같은 센터의 활성 값만 담는다."""

    cycles: list[Option]
    dongs: list[Option]
    classes: list[Option]
    instructors: list[Option] = Field(description="승인·활동 강사만이다(FN-051).")


class CourseWrite(ApiModel):
    """온라인·방문 정원 배분 입력은 없다(FN-048). 일정과 강의실은 일정 관리에서 따로 입력한다."""

    cycle_id: SerialId
    dong_id: SerialId
    class_id: SerialId
    name: str = Field(min_length=1, max_length=100)
    instructor_id: SerialId
    capacity: int = Field(ge=1, le=500)
    wait_capacity: int = Field(ge=0, le=500)
    tuition: Won
    reception_start: AwareDatetime
    reception_end: AwareDatetime
    outside_reception_start: AwareDatetime | None = Field(
        default=None, description="관외 접수 시작일시. 비우면 관외 접수 불가."
    )
    education_start: date
    education_end: date
    description: str = Field(default="", max_length=4000)


class CourseUpdate(CourseWrite):
    version: int = Field(ge=1)


class CourseActions(ApiModel):
    """서버가 상태와 권한으로 정한다. 화면은 값을 해석하지 않고 켜진 버튼만 보인다."""

    can_edit: bool
    can_publish: bool
    can_close_reception: bool
    can_cancel: bool


class AdminCourseSummary(ApiModel):
    course_id: SerialId
    name: str
    cycle_name: str
    class_name: str | None = Field(description="미분류 강좌는 null이다.")
    instructor_name: str
    reception_start: AwareDatetime
    reception_end: AwareDatetime
    capacity: int
    occupied: int = Field(ge=0, description="ES.HOLD + ES.CONFIRM 신청 수(ADR-028)")
    waiting: int = Field(ge=0)
    tuition: Won
    status: CourseAdminStatus
    reception_state: ReceptionState


class AdminCoursePage(Page[AdminCourseSummary]):
    pass


class AdminCourse(CourseWrite):
    course_id: SerialId
    status: CourseAdminStatus
    reception_state: ReceptionState
    education_state: EducationState
    official_capacity: int | None = Field(description="공고 모집정원. 공고에 없으면 null이다. 읽기 전용.")
    occupied: int = Field(ge=0)
    waiting: int = Field(ge=0)
    schedule_count: int = Field(ge=0)
    version: int = Field(ge=1)
    actions: CourseActions


class CancelPreview(ApiModel):
    """폐강 확인 모달에 보이는 영향 범위. 폐강은 환불 완료가 아니다(FN-057)."""

    application_count: int = Field(ge=0)
    paid_count: int = Field(ge=0)


class CancelCourseRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=500)
