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
    """휴강은 수업일과 사유만, 보강은 원수업일·시설·시간도 함께 받는다.

    휴강이면 `classDate`가 휴강일(원수업일)이고, 보강이면 `classDate`가 보강일이며 `originalDate`가
    대체되는 정규 수업일이다(스키마 SCH-01·SCH-02, 사용자 확정 2026-11-13).
    """

    class_date: date
    original_date: date | None = Field(
        default=None,
        description="보강에서 대체될 정규 수업일. 보강은 필수이고 휴강은 비우거나 수업일과 같다.",
    )
    kind: ScheduleChangeKind
    facility_id: SerialId | None = None
    start_time: ClockTime | None = None
    end_time: ClockTime | None = None
    reason: str = Field(min_length=1, max_length=200)


class ScheduleChange(ScheduleChangeWrite):
    original_date: date = Field(description="대체되는 정규 수업일. 휴강이면 수업일과 같다.")
    change_id: SerialId
    facility_name: str | None


class CourseSchedules(ApiModel):
    course_id: SerialId
    course_name: str
    schedules: list[Schedule]
    changes: list[ScheduleChange]
    can_edit: bool = Field(description="일정을 고칠 수 있는 권한과 강좌 상태일 때만 true다.")
