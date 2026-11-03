# OpenAPI 계약이 TDD 규약(문자열 일련번호, camelCase, 오류 형식, 헤더)을 지키는지 검사하는 시험
import re
from typing import Any

import pytest

from app.core.errors import ERROR_STATUS, ErrorCode
from app.main import create_app

Schema = dict[str, Any]

EXPECTED_OPERATIONS = {
    ("get", "/api/v1/home"),
    ("get", "/api/v1/site/contact"),
    ("get", "/api/v1/terms/{term_type}"),
    ("get", "/api/v1/categories"),
    ("get", "/api/v1/courses"),
    ("get", "/api/v1/courses/{course_id}"),
    ("get", "/api/v1/courses/{course_id}/plan"),
    ("get", "/api/v1/courses/{course_id}/apply-preview"),
    ("post", "/api/v1/auth/otp"),
    ("post", "/api/v1/auth/otp/verify"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/logout"),
    ("get", "/api/v1/auth/session"),
    ("get", "/api/v1/join/check-id"),
    ("post", "/api/v1/join"),
    ("get", "/api/v1/me/profile"),
    ("post", "/api/v1/me/applications"),
    ("get", "/api/v1/me/applications"),
    ("get", "/api/v1/me/applications/{application_id}"),
    ("post", "/api/v1/me/applications/{application_id}/cancel"),
    ("post", "/api/v1/me/applications/{application_id}/payments"),
    ("post", "/api/v1/payments/confirm"),
    ("get", "/api/v1/me/payments/{payment_id}/receipt"),
    ("get", "/api/v1/me/applications/{application_id}/refund-preview"),
    ("post", "/api/v1/me/refunds"),
    ("get", "/api/v1/me/refunds"),
}
# 상태를 바꾸지만 CSRF 헤더 대상이 아닌 경로는 없다. GET 외 모든 요청이 대상이다.
IDEMPOTENT_POSTS = {
    ("post", "/api/v1/me/applications"),
    ("post", "/api/v1/me/applications/{application_id}/payments"),
    ("post", "/api/v1/me/refunds"),
}


@pytest.fixture(scope="module")
def spec() -> Schema:
    return create_app().openapi()


def operations(spec: Schema) -> dict[tuple[str, str], Schema]:
    return {
        (method, path): operation
        for path, item in spec["paths"].items()
        for method, operation in item.items()
    }


def walk_properties(spec: Schema) -> list[tuple[str, str, Schema]]:
    found = []
    for schema_name, schema in spec["components"]["schemas"].items():
        for prop_name, prop in schema.get("properties", {}).items():
            found.append((schema_name, prop_name, prop))
    return found


def type_names(prop: Schema) -> set[str]:
    """anyOf로 감싼 선택 필드까지 풀어 JSON 타입 이름을 모은다."""
    names: set[str] = set()
    if "type" in prop:
        names.add(prop["type"])
    for option in prop.get("anyOf", []):
        names |= type_names(option)
    return names


def test_기대한_엔드포인트가_정확히_있다(spec: Schema) -> None:
    assert set(operations(spec)) == EXPECTED_OPERATIONS


def test_모든_경로는_api_v1_아래에_있다(spec: Schema) -> None:
    assert all(path.startswith("/api/v1/") for path in spec["paths"])


def test_operationId는_유일하고_함수_이름이다(spec: Schema) -> None:
    ids = [operation["operationId"] for operation in operations(spec).values()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", operation_id) for operation_id in ids)


def test_일련번호_필드는_모두_숫자_문자열이다(spec: Schema) -> None:
    serial_props = [
        (s, n, p)
        for s, n, p in walk_properties(spec)
        if p.get("x-serial") or any(o.get("x-serial") for o in p.get("anyOf", []))
    ]
    assert serial_props, "일련번호 필드가 하나도 없다"
    for schema_name, prop_name, prop in serial_props:
        assert type_names(prop) - {"null"} == {"string"}, f"{schema_name}.{prop_name}"


def test_이름이_Id로_끝나는_필드는_정수가_아니다(spec: Schema) -> None:
    for schema_name, prop_name, prop in walk_properties(spec):
        if prop_name.endswith("Id") and prop_name != "loginId":
            assert "integer" not in type_names(prop), f"{schema_name}.{prop_name}"


def test_경로_일련번호_파라미터도_문자열이다(spec: Schema) -> None:
    for (method, path), operation in operations(spec).items():
        for parameter in operation.get("parameters", []):
            if parameter["in"] == "path" and parameter["name"].endswith("_id"):
                assert parameter["schema"]["type"] == "string", f"{method} {path}"
                assert parameter["schema"]["pattern"] == "^[0-9]{1,22}$"


def test_JSON_필드는_모두_camelCase다(spec: Schema) -> None:
    for schema_name, prop_name, _ in walk_properties(spec):
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", prop_name), f"{schema_name}.{prop_name}"


def test_FastAPI_기본_422_검증_스키마는_없다(spec: Schema) -> None:
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert "ValidationError" not in spec["components"]["schemas"]


def test_문서화된_오류_응답은_모두_ErrorResponse다(spec: Schema) -> None:
    for (method, path), operation in operations(spec).items():
        for status, response in operation["responses"].items():
            if status.startswith(("4", "5")):
                reference = response["content"]["application/json"]["schema"]["$ref"]
                assert reference.endswith("/ErrorResponse"), f"{method} {path} {status}"


def test_모든_엔드포인트가_400을_문서화한다(spec: Schema) -> None:
    for (method, path), operation in operations(spec).items():
        assert "400" in operation["responses"], f"{method} {path}"


def test_ErrorResponse_code는_ErrorCode_전체를_열거한다(spec: Schema) -> None:
    error_code_schema = spec["components"]["schemas"]["ErrorCode"]
    assert set(error_code_schema["enum"]) == {code.value for code in ErrorCode}


def test_모든_오류_코드는_HTTP_상태가_정의되어_있다() -> None:
    assert set(ERROR_STATUS) == set(ErrorCode)


def test_회원_전용_엔드포인트는_세션_쿠키_보안을_요구한다(spec: Schema) -> None:
    member_prefixes = ("/api/v1/me/", "/api/v1/courses/{course_id}/apply-preview", "/api/v1/payments/confirm")
    for (method, path), operation in operations(spec).items():
        if path.startswith(member_prefixes):
            assert operation.get("security") == [{"sessionCookie": []}], f"{method} {path}"
    assert spec["components"]["securitySchemes"]["sessionCookie"]["in"] == "cookie"


def test_GET이_아닌_요청은_CSRF_헤더를_계약에_가진다(spec: Schema) -> None:
    for (method, path), operation in operations(spec).items():
        if method != "get":
            names = {p["name"] for p in operation.get("parameters", []) if p["in"] == "header"}
            assert "X-CSRF-Token" in names, f"{method} {path}"


def test_신청_결제_환불_생성은_Idempotency_Key를_필수로_받는다(spec: Schema) -> None:
    ops = operations(spec)
    for key in IDEMPOTENT_POSTS:
        headers = {p["name"]: p for p in ops[key].get("parameters", []) if p["in"] == "header"}
        assert headers["Idempotency-Key"]["required"] is True, key


def test_신청_요청_모델에는_금액_필드가_없다(spec: Schema) -> None:
    properties = spec["components"]["schemas"]["ApplicationCreate"]["properties"]
    assert set(properties) == {"courseId"}


def test_결제_진행_엔드포인트에_금액_입력은_승인_확인뿐이다(spec: Schema) -> None:
    create = spec["components"]["schemas"]["PaymentRequestCreate"]["properties"]
    confirm = spec["components"]["schemas"]["PaymentConfirmRequest"]["properties"]
    assert set(create) == {"method"}
    assert "amount" in confirm


def test_홈_응답은_교육기수를_선택_필드로_가진다(spec: Schema) -> None:
    home = spec["components"]["schemas"]["HomeResponse"]
    assert "cycle" in home["properties"]
    assert "cycle" not in home.get("required", []) or "null" in type_names(home["properties"]["cycle"])
    cycle = spec["components"]["schemas"]["CycleInfo"]
    assert set(cycle["properties"]) == {
        "name",
        "educationStart",
        "educationEnd",
        "receptionStart",
        "receptionEnd",
        "receptionState",
    }


def test_강좌는_요일별_시간이_달라도_일정_행_목록으로_표현한다(spec: Schema) -> None:
    summary = spec["components"]["schemas"]["CourseSummary"]["properties"]
    # 요일 목록 하나와 시각 하나로는 한국무용(요일마다 시간이 다름)이나 반이 나뉜 강좌를 담을 수 없다.
    assert "schedules" in summary
    assert not {"days", "startTime", "endTime"} & set(summary)
    slot = spec["components"]["schemas"]["ScheduleSlot"]["properties"]
    assert set(slot) == {"days", "startTime", "endTime", "label"}


def test_강좌는_서버가_판정한_교육_상태를_가진다(spec: Schema) -> None:
    summary = spec["components"]["schemas"]["CourseSummary"]["properties"]
    assert "educationState" in summary
    states = spec["components"]["schemas"]["EducationState"]["enum"]
    assert states == ["UPCOMING", "ONGOING", "ENDED"]


def test_분야_목록_응답은_분야_참조_배열이다(spec: Schema) -> None:
    categories = spec["components"]["schemas"]["CategoryList"]["properties"]
    assert set(categories) == {"items"}
    assert categories["items"]["items"]["$ref"].endswith("/CategoryRef")


def test_강좌_목록_기준에는_교육기수를_담고_상세에는_기수명을_담는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert "cycle" in schemas["CourseListCriteria"]["properties"]
    assert "basisAt" in schemas["CourseListCriteria"]["properties"]
    assert schemas["CoursePage"]["properties"]["criteria"]["$ref"].endswith("/CourseListCriteria")
    assert "cycleName" in schemas["CourseDetail"]["properties"]


def test_환불_접수_모델에는_금액_필드가_없다(spec: Schema) -> None:
    assert set(spec["components"]["schemas"]["RefundCreate"]["properties"]) == {"applicationId", "reason"}


def test_신청은_영수증_조회에_쓸_결제_일련번호를_가진다(spec: Schema) -> None:
    summary = spec["components"]["schemas"]["ApplicationSummary"]["properties"]
    # 영수증 API는 결제 번호로 조회한다. 신청 응답에 없으면 화면이 영수증 링크를 만들 수 없다.
    assert "paymentId" in summary
    assert "x-serial" in str(summary["paymentId"])
