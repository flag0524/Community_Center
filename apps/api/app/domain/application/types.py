# 수강신청 도메인의 열거형. 신청 상태(ES)와 화면 표시 상태
from enum import StrEnum


class ApplicationStatus(StrEnum):
    """신청 상태. TB_ATNLC_APLY.APLY_STTS_CD(ES 코드집합)에 대응한다."""

    WAITING = "WAITING"  # ES.WAIT
    HOLD = "HOLD"  # ES.HOLD
    CONFIRMED = "CONFIRMED"  # ES.CONFIRM
    CANCELLED = "CANCELLED"  # ES.CANCEL
    EXPIRED = "EXPIRED"  # ES.EXPIRE
    COMPLETED = "COMPLETED"  # ES.COMPLETE


class ApplicationDisplayState(StrEnum):
    """화면에 보이는 신청 상태. 서버가 신청 상태와 결제 상태를 합쳐 판정한다(TDD 5.1)."""

    WAITING = "WAITING"  # 대기 N번
    PAYMENT_DUE = "PAYMENT_DUE"  # 결제대기
    PAYMENT_FAILED = "PAYMENT_FAILED"  # 결제실패, 기한 안에서는 다시 결제 가능
    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"  # 결제 결과 확인 중, ES.HOLD + PS.PENDING
    CONFIRMED = "CONFIRMED"  # 수강확정
    CONFIRMED_FREE = "CONFIRMED_FREE"  # 수강확정(결제 없음)
    EXPIRED = "EXPIRED"  # 결제기한 만료
    CANCELLED = "CANCELLED"  # 신청취소
    COURSE_CLOSED = "COURSE_CLOSED"  # 폐강
    COMPLETED = "COMPLETED"  # 수강종료
