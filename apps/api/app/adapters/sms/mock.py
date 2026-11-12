# 시험·개발용 모의 문자 발송기. 보낸 문자를 메모리에만 두고 결과를 시험이 정할 수 있다
from dataclasses import dataclass, field
from itertools import count

from app.adapters.sms.base import DeliveryState, SendOutcome, SmsLookup, SmsResult


@dataclass(frozen=True)
class SentMessage:
    to: str
    text: str
    sender: str
    idempotency_key: str | None = None


@dataclass
class MockSmsSender:
    provider_name: str = "mock"
    outbox: list[SentMessage] = field(default_factory=list)
    next_outcome: SendOutcome = SendOutcome.ACCEPTED
    raises: bool = False
    # 전달 결과는 시험이 멱등키(또는 메시지 ID)별로 정한다. 정하지 않으면 공급자에 기록이 없는 것이다
    deliveries: dict[str, SmsLookup] = field(default_factory=dict)
    lookups: list[str] = field(default_factory=list)
    lookup_raises: bool = False
    _ids: "count[int]" = field(default_factory=lambda: count(1))

    def send(self, *, to: str, text: str, sender: str, idempotency_key: str | None = None) -> SmsResult:
        if self.raises:
            raise TimeoutError("모의 통신 오류")
        outcome = self.next_outcome
        self.next_outcome = SendOutcome.ACCEPTED  # 한 번 쓰고 평소 상태로 돌아간다
        if outcome is SendOutcome.REJECTED:
            return SmsResult(outcome, failure_code="MOCK_REJECTED")
        self.outbox.append(SentMessage(to, text, sender, idempotency_key))
        if outcome is SendOutcome.UNKNOWN:
            return SmsResult(outcome, failure_code="MOCK_TIMEOUT")
        return SmsResult(outcome, message_id=f"mock-{next(self._ids)}")

    def lookup(self, *, idempotency_key: str, message_id: str | None) -> SmsLookup:
        self.lookups.append(idempotency_key)
        if self.lookup_raises:
            raise TimeoutError("모의 통신 오류")
        found = self.deliveries.get(idempotency_key) or (
            self.deliveries.get(message_id) if message_id else None
        )
        return found or SmsLookup(DeliveryState.UNKNOWN)
