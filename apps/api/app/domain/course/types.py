# 강좌 도메인의 열거형. 접수 상태와 요일
from enum import StrEnum


class ReceptionState(StrEnum):
    """접수 상태. 목록·상세·쉬운 화면이 같은 값을 쓴다(RQ-QUR-NF-008)."""

    UPCOMING = "UPCOMING"  # 접수예정
    OPEN = "OPEN"  # 접수중
    CLOSED = "CLOSED"  # 접수마감


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"
