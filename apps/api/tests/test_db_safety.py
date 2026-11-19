# 시험 DB 초기화가 개발·운영 DB를 가리키면 연결 전에 거부하는 보호장치를 확인한다
import pytest
from sqlalchemy.engine import make_url

from tests.conftest import assert_test_database


@pytest.mark.parametrize("name", ["jori_dev", "production", "jori_test_backup", "", "JORI_TEST"])
def test_시험_전용_이름이_아니면_접속을_거절한다(name: str) -> None:
    with pytest.raises(pytest.UsageError):
        assert_test_database(make_url(f"mysql+pymysql://test:secret@localhost/{name}"))


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_앱과_같은_DB는_시험_이름이어도_거절하고_비밀값은_숨긴다(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.setenv("JORI_DATABASE_URL", "mysql+pymysql://app:app-secret@LOCALHOST:3306/jori_test")
    with pytest.raises(pytest.UsageError) as caught:
        assert_test_database(make_url(f"mysql+pymysql://test:test-secret@{host}/jori_test"))
    assert "app-secret" not in str(caught.value) and "test-secret" not in str(caught.value)


def test_실제_접속_DB도_시험_이름인지_확인한다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JORI_DATABASE_URL", raising=False)
    url = make_url("mysql+pymysql://test:secret@localhost/jori_test")
    assert_test_database(url, actual_name="jori_test")
    with pytest.raises(pytest.UsageError):
        assert_test_database(url, actual_name="jori_dev")
