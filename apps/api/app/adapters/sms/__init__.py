# 문자 발송 어댑터 선택. 공급자가 계약으로 정해지기 전에는 모의 어댑터만 있다(ADR-009)
from functools import lru_cache

from app.adapters.sms.base import SmsSender
from app.adapters.sms.mock import MockSmsSender
from app.core.config import ConfigError, Settings


@lru_cache(maxsize=1)
def _mock() -> MockSmsSender:
    return MockSmsSender()


def build_sender(settings: Settings) -> SmsSender:
    if settings.sms_provider == "mock":
        return _mock()
    raise ConfigError(f"지원하지 않는 문자 공급자입니다: {settings.sms_provider}")
