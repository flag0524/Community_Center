# 시험·개발용 모의 문자 발송기. 보낸 문자를 메모리에만 두고 결과를 시험이 정할 수 있다
from dataclasses import dataclass, field
from itertools import count

from app.adapters.sms.base import SendOutcome, SmsResult


@dataclass(frozen=True)
class SentMessage:
    to: str
    text: str
    sender: str


@dataclass
class MockSmsSender:
    provider_name: str = "mock"
    outbox: list[SentMessage] = field(default_factory=list)
    next_outcome: SendOutcome = SendOutcome.ACCEPTED
    _ids: "count[int]" = field(default_factory=lambda: count(1))

    def send(self, *, to: str, text: str, sender: str) -> SmsResult:
        outcome = self.next_outcome
        self.next_outcome = SendOutcome.ACCEPTED  # 한 번 쓰고 평소 상태로 돌아간다
        if outcome is SendOutcome.REJECTED:
            return SmsResult(outcome, failure_code="MOCK_REJECTED")
        self.outbox.append(SentMessage(to, text, sender))
        if outcome is SendOutcome.UNKNOWN:
            return SmsResult(outcome, failure_code="MOCK_TIMEOUT")
        return SmsResult(outcome, message_id=f"mock-{next(self._ids)}")
