# 처리하지 못한 오류의 예외 전문(SQL·입력값)이 응답과 서버 로그 어디에도 남지 않는지 확인하는 시험
import logging
import traceback
from collections.abc import Iterator

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from app.core.config import Settings
from app.db.session import create_db_engine
from app.main import create_app

SECRET = "개인정보표식홍길동"


def db_failure() -> ProgrammingError:
    """SQL 인자와 DB 서버의 원문 메시지 양쪽에 입력값이 실린 오류."""
    return ProgrammingError("SELECT * FROM TB_MBR WHERE MBR_NM = %(q)s", {"q": SECRET}, Exception(SECRET))


def test_처리하지_못한_오류는_서버로_올려_보내지_않고_종류와_위치만_남긴다(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise db_failure()

    # 예외가 앱 밖으로 나가면 서버가 전문을 로그에 남긴다. 시험 클라이언트는 그 예외를 그대로 던진다
    with caplog.at_level(logging.ERROR):
        response = TestClient(app).get("/boom", headers={"X-Request-ID": "probe-request-0001"})
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert response.headers["X-Request-ID"] == response.json()["requestId"]
    assert SECRET not in response.text and SECRET not in caplog.text
    assert "ProgrammingError" in caplog.text and response.json()["requestId"] in caplog.text
    assert "test_error_logging.py" in caplog.text  # 고칠 곳을 찾을 수 있게 호출 위치는 남긴다


def test_응답을_보내던_중의_오류도_전문_없이_끊는다(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app()

    def rows() -> Iterator[str]:
        yield "첫 줄\n"
        raise db_failure()

    @app.get("/stream-boom")
    def stream() -> StreamingResponse:
        return StreamingResponse(rows(), media_type="text/csv")

    with caplog.at_level(logging.ERROR), pytest.raises(Exception) as caught:
        TestClient(app).get("/stream-boom")
    printed = "".join(traceback.format_exception(caught.value))  # 서버가 로그에 남기는 모양
    assert SECRET not in printed and SECRET not in caplog.text
    assert "ProgrammingError" in caplog.text


def test_DB_엔진은_예외_문구에_SQL_인자를_싣지_않는다() -> None:
    settings = Settings(database_url="mysql+pymysql://u:p@127.0.0.1:1/x", site_id="test-site")
    assert create_db_engine(settings).hide_parameters is True
