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


class SmsSender(Protocol):
    provider_name: str

    def send(self, *, to: str, text: str, sender: str) -> SmsResult:
        """문안에는 인증번호 원문이 들어 있다. 구현체는 문안을 로그에 남기지 않는다."""
        ...
