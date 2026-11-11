# 반환 기준액 산정. 개강 전 전액, 개강 후에는 지난 달(당월 포함)의 수강료를 뺀다(TDD 5.6, PRD Q15 잠정 공식)
from dataclasses import dataclass
from datetime import date

from app.domain.refund.types import RefundRule


@dataclass(frozen=True)
class Reference:
    """반환 기준액과 그 근거. 근거는 기관 승인본이 나오면 공식과 함께 바뀔 수 있다."""

    amount: int
    rule: RefundRule
    reference_date: date
    education_months: int | None = None
    elapsed_months: int | None = None
    monthly_fee: int | None = None


def _ymd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def reference_amount(paid: int, education_begin: str, education_end: str, today: date) -> Reference:
    """paid는 원결제액이다. 교육일자는 YYYYMMDD이고 today는 한국 날짜다."""
    begin, end = _ymd(education_begin), _ymd(education_end)
    if today < begin:
        return Reference(paid, RefundRule.BEFORE_START, today)
    months = (end.year - begin.year) * 12 + (end.month - begin.month) + 1
    elapsed = (today.year - begin.year) * 12 + (today.month - begin.month) + 1  # 당월을 포함한다
    monthly = paid // months
    # 교육 기간을 모두 보낸 뒤에는 남는 것이 없다. 나눗셈의 나머지(원 단위)가 남지 않게 0으로 닫는다.
    amount = 0 if elapsed >= months else max(0, paid - monthly * elapsed)
    return Reference(amount, RefundRule.AFTER_START, today, months, elapsed, monthly)
