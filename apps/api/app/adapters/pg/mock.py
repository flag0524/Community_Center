# 시험·개발용 모의 PG. 승인 결과와 돌려줄 값을 시험이 정하고, 받은 요청을 기록한다
from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from threading import Lock
from time import sleep

from app.adapters.pg.base import ApproveOutcome, ApproveResult


@dataclass(frozen=True)
class ApproveCall:
    order_no: str
    payment_key: str
    amount: int


@dataclass
class MockPaymentGateway:
    provider_name: str = "mock"
    merchant_id: str = "MOCK-MERCHANT"
    calls: list[ApproveCall] = field(default_factory=list)
    next_outcome: ApproveOutcome = ApproveOutcome.APPROVED
    # 승인 응답을 일부러 어긋나게 만들어 대조 검사를 시험한다
    answer_amount: int | None = None
    answer_order_no: str | None = None
    approved_at: datetime | None = None
    raises: bool = False
    delay_seconds: float = 0.0  # 응답이 늦는 상황을 만들어 동시 요청이 겹치는 구간을 넓힌다
    _ids: "count[int]" = field(default_factory=lambda: count(1))
    _lock: Lock = field(default_factory=Lock)

    def prepare(self, *, order_no: str, amount: int, method: str) -> dict[str, str]:
        return {"orderNo": order_no, "amount": str(amount), "method": method}

    def approve(self, *, order_no: str, payment_key: str, amount: int) -> ApproveResult:
        with self._lock:  # 여러 스레드에서 불러도 호출 기록이 섞이지 않게 한다
            self.calls.append(ApproveCall(order_no, payment_key, amount))
            number = next(self._ids)
            outcome, self.next_outcome = (
                self.next_outcome,
                ApproveOutcome.APPROVED,
            )  # 한 번 쓰고 평소로 돌아간다
        if self.delay_seconds:
            sleep(self.delay_seconds)
        if self.raises:
            raise TimeoutError("모의 통신 오류")
        if outcome is ApproveOutcome.REJECTED:
            return ApproveResult(outcome, failure_code="MOCK_REJECTED")
        if outcome is ApproveOutcome.UNKNOWN:
            return ApproveResult(outcome, failure_code="MOCK_TIMEOUT")
        return ApproveResult(
            outcome,
            transaction_id=f"mock-tx-{number}",
            approval_no=f"A{number:07d}",
            approved_at=self.approved_at,
            order_no=self.answer_order_no or order_no,
            amount=self.answer_amount if self.answer_amount is not None else amount,
        )
