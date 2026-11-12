# 문자 발송 어댑터 규약. 공급자 접수와 최종 성공을 구분하고, 결과를 알 수 없을 때를 따로 둔다(SMS-04)
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SendOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"  # 공급자가 접수했다. 최종 성공은 나중에 조회로 확인한다(SS.SENDING)
    REJECTED = "REJECTED"  # 공급자가 거절했다. 확인된 실패다(SS.FAIL)
    UNKNOWN = "UNKNOWN"  # 시간 초과처럼 결과를 알 수 없다. 새로 보내지 않고 조회한다(SS.UNKNOWN)


@dataclass(frozen=True)
class SmsResult:
    outcome: SendOutcome
    message_id: str | None = None
    failure_code: str | None = None


class DeliveryState(StrEnum):
    DELIVERED = "DELIVERED"  # 공급자가 최종 전달을 확인했다(SS.SENT)
    FAILED = "FAILED"  # 전달 실패가 확인됐다(SS.FAIL)
    PENDING = "PENDING"  # 접수했지만 아직 전달 결과가 없다. 계속 기다린다
    UNKNOWN = "UNKNOWN"  # 조회로도 알 수 없다(공급자에 기록이 없거나 조회 실패). 새로 보내지 않는다


@dataclass(frozen=True)
class SmsLookup:
    state: DeliveryState
    failure_code: str | None = None


class SmsSender(Protocol):
    provider_name: str

    def send(self, *, to: str, text: str, sender: str, idempotency_key: str | None = None) -> SmsResult:
        """문안에는 인증번호 원문이 들어 있다. 구현체는 문안을 로그에 남기지 않는다.

        idempotency_key를 받는 공급자에는 같은 키로 한 번만 발송하게 하고, 조회에도 같은 키를 쓴다.
        """
        ...

    def lookup(self, *, idempotency_key: str, message_id: str | None) -> SmsLookup:
        """접수한 문자의 최종 전달 결과 또는 결과를 모르는 문자의 실제 발송 여부를 조회한다(SMS-04)."""
        ...
