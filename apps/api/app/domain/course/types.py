# 강좌 도메인의 열거형. 접수 상태와 요일
from enum import StrEnum


class ReceptionState(StrEnum):
    """접수 상태. 목록·상세·쉬운 화면이 같은 값을 쓴다(RQ-QUR-NF-008)."""

    UPCOMING = "UPCOMING"  # 접수예정
    OPEN = "OPEN"  # 접수중
    CLOSED = "CLOSED"  # 접수마감


class EducationState(StrEnum):
    """교육 상태. 접수 상태와 따로 서버가 교육기간으로 판정한다. 화면은 날짜를 비교하지 않는다."""

    UPCOMING = "UPCOMING"  # 교육예정
    ONGOING = "ONGOING"  # 교육중
    ENDED = "ENDED"  # 교육종료


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"
