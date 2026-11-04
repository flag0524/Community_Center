# 강사 도메인의 열거형. 모집 상태와 지원 심사 상태
from enum import StrEnum


class RecruitmentStatus(StrEnum):
    """모집공고 상태. 서버가 모집기간으로 판정하며 화면은 날짜를 비교하지 않는다."""

    UPCOMING = "UPCOMING"  # 모집예정
    OPEN = "OPEN"  # 모집중
    CLOSED = "CLOSED"  # 모집마감


class InstructorApplyStatus(StrEnum):
    """강사 지원 심사 상태. TB_INSTR_APLY의 심사 단계에 대응한다."""

    REVIEWING = "REVIEWING"  # 서류 검토중
    SUPPLEMENT = "SUPPLEMENT"  # 보완요청
    INTERVIEW = "INTERVIEW"  # 심사중
    SELECTED = "SELECTED"  # 선정
    REJECTED = "REJECTED"  # 미선정
