# 결제대행(PG) 어댑터 규약. 승인 결과를 알 수 없을 때를 실패와 구분해 따로 둔다(ADR-006, ADR-009, ADR-040)
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

CURRENCY = "KRW"
# 외부 HTTP 호출의 시간 초과(ADR-007). 실제 어댑터는 이 값을 쓰고 시간 초과를 UNKNOWN으로 돌려준다
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 10.0


class ApproveOutcome(StrEnum):
    APPROVED = "APPROVED"  # 승인됐다. 주문·금액·가맹점·통화가 맞는지는 호출한 쪽이 다시 확인한다
    REJECTED = "REJECTED"  # 거절·실패가 확인됐다
    UNKNOWN = "UNKNOWN"  # 시간 초과·통신 오류처럼 결과를 알 수 없다. 재결제 없이 조회로 확인한다


@dataclass(frozen=True)
class ApproveResult:
    """승인 요청과 거래 조회가 함께 쓰는 결과. 공급자가 알려 준 값이라 그대로 믿지 않고 대조한다."""

    outcome: ApproveOutcome
    transaction_id: str | None = None
    approval_no: str | None = None
    approved_at: datetime | None = None  # 시간대 없는 UTC
    order_no: str | None = None  # 공급자가 승인한 주문번호
    amount: int | None = None  # 공급자가 승인한 금액
    merchant_id: str | None = None  # 공급자가 승인한 가맹점
    currency: str | None = None  # 공급자가 승인한 통화
    failure_code: str | None = None


@dataclass(frozen=True)
class WebhookEvent:
    """서명을 확인한 통보. 상태는 믿지 않고 주문번호로 거래를 다시 조회해 확인한다(TDD 5.4.2)."""

    event_id: str
    order_no: str
    digest: str  # 검증한 원문의 SHA-256. 같은 사건 번호에 다른 내용이 오면 충돌로 판정한다(TDD 5.4.2)


class WebhookRejected(Exception):
    """서명이 틀렸거나 형식을 읽을 수 없는 통보. 저장하지 않고 보안 로그에만 남긴다."""


class PaymentGateway(Protocol):
    provider_name: str
    merchant_id: str

    def prepare(self, *, order_no: str, amount: int, method: str) -> dict[str, str]:
        """결제창을 여는 데 필요한 값. 비밀값을 담지 않는다."""
        ...

    def approve(self, *, order_no: str, payment_key: str, amount: int) -> ApproveResult:
        """서버 대 서버 승인 요청. 구현체는 예외 대신 UNKNOWN을 돌려주는 것이 좋다."""
        ...

    def lookup(self, *, order_no: str) -> ApproveResult:
        """주문번호로 실제 거래 상태를 조회한다. 통보와 승인 결과 재확인이 쓴다."""
        ...

    def parse_webhook(self, *, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        """서명을 확인하고 통보를 읽는다. 서명이 틀리면 WebhookRejected를 던진다."""
        ...
