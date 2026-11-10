# 결제대행 어댑터 선택. PG사는 계약으로 정해지기 전이라 모의 어댑터만 있다(PRD Q1, ADR-010)
from functools import lru_cache

from app.adapters.pg.base import PaymentGateway
from app.adapters.pg.mock import MockPaymentGateway
from app.core.config import ConfigError, Settings


@lru_cache(maxsize=1)
def _mock() -> MockPaymentGateway:
    return MockPaymentGateway()


def build_gateway(settings: Settings) -> PaymentGateway:
    if settings.pg_provider == "mock":
        return _mock()
    raise ConfigError(f"지원하지 않는 결제대행사입니다: {settings.pg_provider}")
