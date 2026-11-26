# 출석 표시와 출석부 입력 상태의 값 종류
from enum import StrEnum


class AttendanceInputStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"  # 입력중
    DONE = "DONE"  # 완료


class AttendanceMark(StrEnum):
    PRESENT = "PRESENT"  # 출석
    ABSENT = "ABSENT"  # 결석
    UNCHECKED = "UNCHECKED"  # 미체크


class TeachingSessionStatus(StrEnum):
    """강사가 보는 회차 상태. 아직 출석부가 없는 회차가 있어 관리자 상태보다 하나 많다."""

    NOT_STARTED = "NOT_STARTED"  # 미입력
    IN_PROGRESS = "IN_PROGRESS"  # 입력중
    DONE = "DONE"  # 완료


# DB 코드(AR)와 표시 값. 미체크를 결석으로 바꾸지 않는다
MARK_BY_CODE = {
    "AR.PRESENT": AttendanceMark.PRESENT,
    "AR.ABSENT": AttendanceMark.ABSENT,
    "AR.UNCHECKED": AttendanceMark.UNCHECKED,
}
CODE_BY_MARK = {mark: code for code, mark in MARK_BY_CODE.items()}
