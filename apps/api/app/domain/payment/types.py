# 결제 도메인의 열거형. 결제 상태(PS)와 결제수단(PM)
from enum import StrEnum


class PaymentStatus(StrEnum):
    """결제 상태. TB_STLM.STLM_STTS_CD(PS 코드집합)에 대응한다."""

    READY = "READY"  # PS.READY 결제창 파라미터 발급
    PENDING = "PENDING"  # PS.PENDING 승인 결과 대기·불명
    PAID = "PAID"  # PS.PAID
    FAILED = "FAILED"  # PS.FAIL
    CANCELLED = "CANCELLED"  # PS.CANCEL


class PaymentMethod(StrEnum):
    """허용 결제수단은 카드와 실시간 계좌이체뿐이다. 가상계좌는 제외한다(ADR-010)."""

    CARD = "CARD"  # PM.CARD
    TRANSFER = "TRANSFER"  # PM.TRANSFER
