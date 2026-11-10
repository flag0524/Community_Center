# 오류 응답 형식, 요청 ID, 입력값 비반환, 골격 엔드포인트의 응답을 확인하는 시험
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.main import create_app

KEY = {"Idempotency-Key": "test-key-12345678"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    # 이 시험들은 입력 검증과 오류 형식만 본다. 환경변수와 DB 없이 돌도록 둘 다 시험용으로 바꾼다.
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="unused", site_id="test")
    app.dependency_overrides[get_db] = lambda: (
        None
    )  # 검증이 실패하면 핸들러는 호출되지 않아 세션을 쓰지 않는다
    return TestClient(app, raise_server_exceptions=False)


def assert_error_shape(body: dict[str, object], code: ErrorCode) -> None:
    assert set(body) <= {"code", "message", "fields", "requestId"}
    assert body["code"] == code.value
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["requestId"], str) and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", body["requestId"])


def test_골격_엔드포인트는_501_NOT_IMPLEMENTED_형식으로_답한다(client: TestClient) -> None:
    response = client.get("/api/admin/v1/dashboard")
    assert response.status_code == 501
    assert_error_shape(response.json(), ErrorCode.NOT_IMPLEMENTED)


def test_없는_경로는_404_NOT_FOUND다(client: TestClient) -> None:
    response = client.get("/api/v1/없는경로")
    assert response.status_code == 404
    assert_error_shape(response.json(), ErrorCode.NOT_FOUND)


def test_허용되지_않는_메서드는_405다(client: TestClient) -> None:
    response = client.delete("/api/v1/courses")
    assert response.status_code == 405
    assert_error_shape(response.json(), ErrorCode.METHOD_NOT_ALLOWED)


def test_올바른_요청_ID는_그대로_돌려준다(client: TestClient) -> None:
    response = client.get("/api/v1/courses", headers={"X-Request-ID": "req-abcdef-123456"})
    assert response.headers["X-Request-ID"] == "req-abcdef-123456"
    assert response.json()["requestId"] == "req-abcdef-123456"


@pytest.mark.parametrize(
    "bad_id",
    [
        "short",
        "has space inside",
        "x" * 65,
        "line=break;injected",
        "<script>alert(1)</script>",
        "slash/slash/slash",
    ],
)
def test_형식이_틀린_요청_ID는_버리고_새로_만든다(client: TestClient, bad_id: str) -> None:
    response = client.get("/api/v1/courses", headers={"X-Request-ID": bad_id})
    new_id = response.headers["X-Request-ID"]
    assert new_id != bad_id
    assert re.fullmatch(r"[A-Za-z0-9_-]{8,64}", new_id)
    assert response.json()["requestId"] == new_id


def test_검증_오류는_400이고_입력값을_되돌려_주지_않는다(client: TestClient) -> None:
    secret = "SECRET-VALUE-9988"
    response = client.post("/api/v1/auth/otp", json={"purpose": "JOIN", "phone": secret})
    assert response.status_code == 400
    body = response.json()
    assert_error_shape(body, ErrorCode.VALIDATION_FAILED)
    assert "phone" in body["fields"]
    assert secret not in response.text


def test_로그인하지_않은_신청_요청은_본문을_검증하기_전에_401이다(client: TestClient) -> None:
    response = client.post("/api/v1/me/applications", json={"courseId": "1", "payableAmount": 0}, headers=KEY)
    assert response.status_code == 401
    assert_error_shape(response.json(), ErrorCode.UNAUTHENTICATED)


def test_일련번호_경로_파라미터가_숫자가_아니면_400이다(client: TestClient) -> None:
    response = client.get("/api/v1/courses/abc")
    assert response.status_code == 400
    assert_error_shape(response.json(), ErrorCode.VALIDATION_FAILED)


def test_예상하지_못한_예외는_500이고_상세를_숨긴다() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("DB password is hunter2")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert_error_shape(response.json(), ErrorCode.INTERNAL_ERROR)
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


def test_문서_화면과_스키마_URL은_열려_있지_않다(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json", "/api/v1/openapi.json"):
        assert client.get(path).status_code == 404, path
