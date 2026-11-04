# 관리자 강좌 일정·휴보강 API의 요청·응답 모델
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, ClockTime, SerialId
from app.domain.admin.education_types import ScheduleChangeKind
from app.domain.course.types import Weekday


class ScheduleWrite(ApiModel):
    weekday: Weekday
    start_time: ClockTime
    end_time: ClockTime
    facility_id: SerialId = Field(description="사용 중인 강의실만 고를 수 있다.")
    period_start: date
    period_end: date


class ScheduleUpdate(ScheduleWrite):
    version: int = Field(ge=1)


class Schedule(ScheduleWrite):
    schedule_id: SerialId
    facility_name: str
    version: int = Field(ge=1)


class ScheduleChangeWrite(ApiModel):
    """휴강은 수업일과 사유만, 보강은 시설과 시간도 함께 받는다."""

    class_date: date
    kind: ScheduleChangeKind
    facility_id: SerialId | None = None
    start_time: ClockTime | None = None
    end_time: ClockTime | None = None
    reason: str = Field(min_length=1, max_length=200)


class ScheduleChange(ScheduleChangeWrite):
    change_id: SerialId
    facility_name: str | None


class CourseSchedules(ApiModel):
    course_id: SerialId
    course_name: str
    schedules: list[Schedule]
    changes: list[ScheduleChange]
    can_edit: bool = Field(description="일정을 고칠 수 있는 권한과 강좌 상태일 때만 true다.")
