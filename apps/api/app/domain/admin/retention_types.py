# 관리자 보존·파기 검토 화면의 열거형. 보존기간은 TRD 5.1을 따르고 정해지지 않은 자료는 값을 가정하지 않는다
from enum import StrEnum


class RetentionTarget(StrEnum):
    WITHDRAWN_MEMBER = "WITHDRAWN_MEMBER"  # 탈퇴 회원 일반 개인정보 (탈퇴 후 30일)
    AUTH_RECORDS = "AUTH_RECORDS"  # 만료된 OTP 요청·세션·로그인 실패 이력
    AUDIT_HISTORY = "AUDIT_HISTORY"  # 업무 감사이력 (3년)
    REFUND_ACCOUNT = "REFUND_ACCOUNT"  # 수동환불 계좌정보 (보존기간 TBD)
    SMS_RECORDS = "SMS_RECORDS"  # 문자 문안·수신명단 (보존기간 TBD)


class RetentionState(StrEnum):
    DUE = "DUE"  # 예정일이 지나 실행할 수 있다
    WAITING = "WAITING"  # 예정일 전
    REVIEW_ONLY = "REVIEW_ONLY"  # 검토만 하고 이 화면에서 실행하지 않는다
    PERIOD_TBD = "PERIOD_TBD"  # 보존기간이 정해지지 않았다
