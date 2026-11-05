# 관리자 출석 현황 조회 API의 응답 모델. 조회 전용이고 연락처·생년·결제정보는 담지 않는다(FN-064)
from datetime import date

from pydantic import Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.education_types import AttendanceInputStatus, AttendanceMark


class AttendanceSummary(ApiModel):
    attendance_id: SerialId
    course_id: SerialId
    course_name: str
    class_date: date
    session: int = Field(ge=1, description="회차")
    instructor_name: str
    present: int = Field(ge=0)
    absent: int = Field(ge=0)
    unchecked: int = Field(ge=0)
    input_status: AttendanceInputStatus


class AttendancePage(Page[AttendanceSummary]):
    pass


class AttendanceRow(ApiModel):
    name: str = Field(description="이름은 가려서 준다.")
    application_no: str
    member_status: str = Field(description="회원 상태 표시 이름. 서버가 정한다.")
    mark: AttendanceMark


class AttendanceDetail(AttendanceSummary):
    sheet_no: str = Field(description="출석부 번호")
    roster: list[AttendanceRow]
