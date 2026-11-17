# 관리자 대시보드와 통계 화면의 열거형
from enum import StrEnum


class DashboardTaskKind(StrEnum):
    """대시보드의 "확인할 업무" 종류. 서버는 담당자가 볼 권한이 있는 종류만 내려준다."""

    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"  # 승인 결과 확인
    REFUND_REVIEW = "REFUND_REVIEW"  # 환불 검토 대기
    INSTRUCTOR_REVIEW = "INSTRUCTOR_REVIEW"  # 강사 심사 대기
    INQUIRY_ANSWER = "INQUIRY_ANSWER"  # 문의 답변 대기
    SMS_FAILED = "SMS_FAILED"  # 문자 발송 실패
    REFUND_STUCK = "REFUND_STUCK"  # 환불 처리 중이 오래 확정되지 않음
    SMS_UNKNOWN = "SMS_UNKNOWN"  # 문자 결과 불명이 오래감
    FILE_SCAN_DELAYED = "FILE_SCAN_DELAYED"  # 첨부 파일 검사가 오래 끝나지 않음
