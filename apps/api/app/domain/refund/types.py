# 환불 도메인의 열거형. 환불 상태(RS)와 주민 화면 단계
from enum import StrEnum


class RefundStatus(StrEnum):
    """환불 상태. TB_RFND.RFND_STTS_CD(RS 코드집합)에 대응한다."""

    REQUESTED = "REQUESTED"  # RS.REQUEST
    ON_HOLD = "ON_HOLD"  # RS.HOLD
    REJECTED = "REJECTED"  # RS.REJECT
    APPROVED = "APPROVED"  # RS.APPROVE
    PENDING = "PENDING"  # RS.PENDING
    DONE = "DONE"  # RS.DONE
    FAILED = "FAILED"  # RS.FAIL


class RefundStage(StrEnum):
    """주민 화면 단계. 환불완료는 DONE에서만 표시한다(FN-044)."""

    RECEIVED = "RECEIVED"  # 접수
    PROCESSING = "PROCESSING"  # 처리 중 (APPROVE, PENDING, FAIL)
    ON_HOLD = "ON_HOLD"  # 보류 (사유 표시)
    DONE = "DONE"  # 완료
    REJECTED = "REJECTED"  # 반려 (사유 표시)


class RefundRule(StrEnum):
    """반환 기준액을 어떤 규칙으로 산정했는지(TDD 5.6)."""

    BEFORE_START = "BEFORE_START"  # 개강 전 전액
    AFTER_START = "AFTER_START"  # 개강 후 당월분 제외
