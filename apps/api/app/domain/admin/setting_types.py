# 관리자 운영 설정 화면의 열거형. 코드는 스키마 OR 코드집합에 대응한다
from enum import StrEnum


class OperRuleStatus(StrEnum):
    """운영 기준 검토 상태. 게시 여부나 실제 기능에 적용되었다는 뜻이 아니다(FN-069)."""

    REVIEW = "REVIEW"  # OR.REVIEW 검토중
    DECIDED = "DECIDED"  # OR.DECIDED 확정
    HOLD = "HOLD"  # OR.HOLD 보류
