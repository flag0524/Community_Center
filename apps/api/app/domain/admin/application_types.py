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


class NoticeHandling(StrEnum):
    """PG 통보를 처리한 결과."""

    DONE = "DONE"  # 처리 완료
    DUPLICATE = "DUPLICATE"  # 중복 통보라 기존 결과를 돌려줌
    CONFLICT = "CONFLICT"  # 기존 결과와 충돌해 격리(보안 사건)


class ActionKind(StrEnum):
    RECHECK = "RECHECK"  # PG 재조회
    MANUAL_RECONCILE = "MANUAL_RECONCILE"  # 수동 대사


class ReconcileOutcome(StrEnum):
    """수동 대사로 정하는 결과. PG 관리자 화면에서 확인한 사실만 입력한다(FN-042)."""

    PAID = "PAID"  # 성공
    FAILED = "FAILED"  # 실패


class RefundRequester(StrEnum):
    MEMBER = "MEMBER"  # 본인 온라인 요청
    ADMIN = "ADMIN"  # 담당자가 방문·유선으로 대리 접수


class ExecutionMethod(StrEnum):
    CANCEL_PAYMENT = "CANCEL_PAYMENT"  # 원결제 취소(PG)
    MANUAL_TRANSFER = "MANUAL_TRANSFER"  # 수동 계좌환불
