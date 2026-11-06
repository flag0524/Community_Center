# 관리자 대시보드와 통계 화면의 열거형
from enum import StrEnum


class DashboardTaskKind(StrEnum):
    """대시보드의 "확인할 업무" 종류. 서버는 담당자가 볼 권한이 있는 종류만 내려준다."""

    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"  # 승인 결과 확인
    REFUND_REVIEW = "REFUND_REVIEW"  # 환불 검토 대기
    INSTRUCTOR_REVIEW = "INSTRUCTOR_REVIEW"  # 강사 심사 대기
    INQUIRY_ANSWER = "INQUIRY_ANSWER"  # 문의 답변 대기
    SMS_FAILED = "SMS_FAILED"  # 문자 발송 실패
