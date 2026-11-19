# 운영 환경이 모의 외부 연동이나 안전하지 않은 쿠키 설정으로 시작하지 못하는지 검증한다
import pytest
from fastapi import FastAPI

from app.core.config import ConfigError, get_settings, load_settings
from app.main import _lifespan

BASE = {
    "JORI_DATABASE_URL": "mysql+pymysql://unused/unused",
    "JORI_SITE_ID": "test",
    "JORI_SECRET_KEY": "s" * 32,
}
REAL = {
    **BASE,
    "JORI_ENVIRONMENT": "production",
    "JORI_PG_PROVIDER": "contract-pg",
    "JORI_SMS_PROVIDER": "contract-sms",
    "JORI_FILE_SCANNER": "clamd",
}


def test_개발에서는_모의_연동을_계속_사용한다() -> None:
    settings = load_settings(BASE)
    assert settings.environment == "development" and settings.pg_provider == "mock"


@pytest.mark.parametrize("setting", ["JORI_PG_PROVIDER", "JORI_SMS_PROVIDER", "JORI_FILE_SCANNER"])
def test_운영에서는_하나라도_모의_연동이면_거절한다(setting: str) -> None:
    with pytest.raises(ConfigError, match="mock"):
        load_settings({**REAL, setting: "mock"})


def test_운영에서는_보안_쿠키를_꺼도_거절한다() -> None:
    with pytest.raises(ConfigError, match="쿠키"):
        load_settings({**REAL, "JORI_COOKIE_SECURE": "0"})


def test_환경_이름의_오타를_개발_환경으로_취급하지_않는다() -> None:
    with pytest.raises(ConfigError):
        load_settings({**BASE, "JORI_ENVIRONMENT": "prodution"})


def test_운영_앱은_잘못된_설정을_첫_요청까지_미루지_않고_기동을_거절한다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {**BASE, "JORI_ENVIRONMENT": "production"}.items():
        monkeypatch.setenv(name, value)
    for name in ("JORI_PG_PROVIDER", "JORI_SMS_PROVIDER", "JORI_FILE_SCANNER"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    # 설정 오류는 첫 await 전에 발생한다. Windows 이벤트 루프의 소켓 생성 없이 기동 검사를 실행한다.
    starting = _lifespan(FastAPI()).__aenter__()
    try:
        with pytest.raises(ConfigError, match="mock"):
            starting.send(None)
    finally:
        starting.close()
        get_settings.cache_clear()
