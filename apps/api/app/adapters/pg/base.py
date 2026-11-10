# 결제대행(PG) 어댑터 규약. 승인 결과를 알 수 없을 때를 실패와 구분해 따로 둔다(ADR-006, ADR-010)
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ApproveOutcome(StrEnum):
    APPROVED = "APPROVED"  # 승인됐다. 금액·주문번호가 우리 값과 맞는지는 호출한 쪽이 다시 확인한다
    REJECTED = "REJECTED"  # 거절·실패가 확인됐다
    UNKNOWN = "UNKNOWN"  # 시간 초과·통신 오류처럼 결과를 알 수 없다. 재결제 없이 조회로 확인한다


@dataclass(frozen=True)
class ApproveResult:
    outcome: ApproveOutcome
    transaction_id: str | None = None
    approval_no: str | None = None
    approved_at: datetime | None = None  # 시간대 없는 UTC
    order_no: str | None = None  # 공급자가 승인한 주문번호
    amount: int | None = None  # 공급자가 승인한 금액
    failure_code: str | None = None


class PaymentGateway(Protocol):
    provider_name: str
    merchant_id: str

    def prepare(self, *, order_no: str, amount: int, method: str) -> dict[str, str]:
        """결제창을 여는 데 필요한 값. 비밀값을 담지 않는다."""
        ...

    def approve(self, *, order_no: str, payment_key: str, amount: int) -> ApproveResult:
        """서버 대 서버 승인 요청. 구현체는 예외 대신 UNKNOWN을 돌려주는 것이 좋다."""
        ...
