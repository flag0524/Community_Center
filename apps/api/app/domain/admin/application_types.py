# 관리자 신청·대기 조회 화면의 열거형. 멱등 재요청 결과와 문자 발송 결과
from enum import StrEnum


class ReplayOutcome(StrEnum):
    SAME_RESULT = "SAME_RESULT"  # 같은 키·같은 내용이라 이전 결과를 돌려줌
    CONFLICT = "CONFLICT"  # 같은 키에 다른 내용이라 409


class SmsResult(StrEnum):
    """자리 배정 안내 문자의 발송 결과. 아웃박스(TB_SMS_DMND)를 워커가 보낸 결과다."""

    PENDING = "PENDING"  # 발송 대기
    SENT = "SENT"  # 발송 완료
    FAILED = "FAILED"  # 발송 실패
