# 강사 출석 입력 API의 요청·응답 모델. 연락처·생년·결제정보는 담지 않는다(FN-064)
from datetime import date
from typing import Self

from pydantic import Field, model_validator

from app.core.schema import ApiModel, ClockTime, SerialId
from app.domain.attendance.types import AttendanceMark, TeachingSessionStatus

MAX_ROSTER = 1000  # 한 회차 명단의 상한. 강좌 정원보다 넉넉하다


class TeachingSession(ApiModel):
    class_date: date
    schedule_id: SerialId
    change_id: SerialId | None = Field(default=None, description="보강 회차면 일정변경 번호")
    session: int = Field(ge=1, description="같은 수업일의 회차")
    start_time: ClockTime
    end_time: ClockTime
    makeup: bool = Field(description="보강 회차인지")
    status: TeachingSessionStatus
    attendance_id: SerialId | None = None


class TeachingCourse(ApiModel):
    course_id: SerialId
    course_name: str
    sessions: list[TeachingSession] = Field(description="오늘까지의 수업 회차. 최근 것이 먼저다.")


class TeachingCourseList(ApiModel):
    items: list[TeachingCourse]


class TeachingRosterEntry(ApiModel):
    application_id: SerialId
    name: str = Field(description="이름은 가려서 준다.")
    mark: AttendanceMark


class TeachingSheet(TeachingSession):
    course_id: SerialId
    course_name: str
    version: int | None = Field(default=None, description="출석부 버전. 아직 없으면 null")
    roster: list[TeachingRosterEntry]
    present: int = Field(ge=0)
    absent: int = Field(ge=0)
    unchecked: int = Field(ge=0)


class TeachingMark(ApiModel):
    application_id: SerialId
    mark: AttendanceMark


class _TeachingMarks(ApiModel):
    confirmed: bool = Field(description="입력 내용을 확인했는지. 아니면 저장하지 않는다.")
    marks: list[TeachingMark] = Field(
        max_length=MAX_ROSTER, description="지금 명단의 모든 사람. 명단과 다르면 409다."
    )

    @model_validator(mode="after")
    def _once_each(self) -> Self:
        if len({m.application_id for m in self.marks}) != len(self.marks):
            raise ValueError("같은 신청이 두 번 들어 있습니다.")
        return self


class TeachingAttendanceCreate(_TeachingMarks):
    course_id: SerialId
    class_date: date
    schedule_id: SerialId
    change_id: SerialId | None = None


class TeachingAttendanceUpdate(_TeachingMarks):
    version: int = Field(ge=1, description="화면이 읽은 출석부 버전")
