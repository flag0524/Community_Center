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
    ("get", "/api/v1/contents/{slug}"),
    ("get", "/api/v1/boards/{board}/posts"),
    ("get", "/api/v1/posts/{post_id}"),
    ("get", "/api/v1/files/{file_id}"),
    ("get", "/api/v1/inquiry-categories"),
    ("get", "/api/v1/inquiries"),
    ("get", "/api/v1/inquiries/{post_id}"),
    ("get", "/api/v1/me/inquiries"),
    ("post", "/api/v1/me/inquiries"),
    ("put", "/api/v1/me/inquiries/{post_id}"),
    ("delete", "/api/v1/me/inquiries/{post_id}"),
    ("get", "/api/v1/reviews"),
    ("get", "/api/v1/reviews/{post_id}"),
    ("get", "/api/v1/me/reviews"),
    ("get", "/api/v1/me/reviewable-courses"),
    ("post", "/api/v1/me/reviews"),
    ("put", "/api/v1/me/reviews/{post_id}"),
    ("delete", "/api/v1/me/reviews/{post_id}"),
    ("get", "/api/v1/instructors"),
    ("get", "/api/v1/instructors/{instructor_id}"),
    ("get", "/api/v1/instructor-recruitments"),
    ("get", "/api/v1/instructor-recruitments/{recruitment_id}"),
    ("get", "/api/v1/me/instructor-applications"),
    ("post", "/api/v1/me/instructor-applications"),
    ("get", "/api/v1/me/instructor-applications/{application_id}"),
    ("put", "/api/v1/me/instructor-applications/{application_id}"),
    ("get", "/api/v1/me/instructor-applications/{application_id}/files"),
    ("post", "/api/v1/me/instructor-applications/{application_id}/files"),
    ("get", "/api/v1/me/inquiries/{post_id}/files"),
    ("post", "/api/v1/me/inquiries/{post_id}/files"),
    ("delete", "/api/v1/me/files/{file_id}"),
    ("get", "/api/v1/me/files/{file_id}"),
    ("get", "/api/v1/me/reduction-options"),
    ("get", "/api/v1/me/reduction-reviews"),
    ("post", "/api/v1/me/reduction-reviews"),
    ("get", "/api/v1/me/reduction-reviews/{review_id}"),
    ("post", "/api/v1/me/reduction-reviews/{review_id}/withdraw"),
    ("get", "/api/v1/me/reduction-reviews/{review_id}/files"),
    ("post", "/api/v1/me/reduction-reviews/{review_id}/files"),
    ("put", "/api/v1/me/profile"),
    ("put", "/api/v1/me/password"),
    ("post", "/api/v1/me/withdraw"),
    ("post", "/api/v1/auth/find-id"),
    ("post", "/api/v1/auth/password-reset"),
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
ADMIN_OPERATIONS = {
    ("post", "/api/admin/v1/auth/login"),
    ("post", "/api/admin/v1/auth/logout"),
    ("get", "/api/admin/v1/auth/session"),
    ("post", "/api/admin/v1/auth/extend"),
    ("get", "/api/admin/v1/me/permissions"),
    ("get", "/api/admin/v1/cycles"),
    ("post", "/api/admin/v1/cycles"),
    ("get", "/api/admin/v1/cycles/{cycle_id}"),
    ("put", "/api/admin/v1/cycles/{cycle_id}"),
    ("get", "/api/admin/v1/course-options"),
    ("get", "/api/admin/v1/courses"),
    ("post", "/api/admin/v1/courses"),
    ("get", "/api/admin/v1/courses/{course_id}"),
    ("put", "/api/admin/v1/courses/{course_id}"),
    ("post", "/api/admin/v1/courses/{course_id}/publish"),
    ("post", "/api/admin/v1/courses/{course_id}/close-reception"),
    ("get", "/api/admin/v1/courses/{course_id}/cancel-preview"),
    ("post", "/api/admin/v1/courses/{course_id}/cancel-course"),
    ("get", "/api/admin/v1/facilities"),
    ("post", "/api/admin/v1/facilities"),
    ("get", "/api/admin/v1/facilities/{facility_id}"),
    ("put", "/api/admin/v1/facilities/{facility_id}"),
    ("get", "/api/admin/v1/courses/{course_id}/schedules"),
    ("post", "/api/admin/v1/courses/{course_id}/schedules"),
    ("put", "/api/admin/v1/courses/{course_id}/schedules/{schedule_id}"),
    ("delete", "/api/admin/v1/courses/{course_id}/schedules/{schedule_id}"),
    ("post", "/api/admin/v1/courses/{course_id}/schedule-changes"),
    ("delete", "/api/admin/v1/courses/{course_id}/schedule-changes/{change_id}"),
    ("get", "/api/admin/v1/instructor-applications"),
    ("post", "/api/admin/v1/instructor-applications"),
    ("get", "/api/admin/v1/instructor-applications/{application_id}"),
    ("put", "/api/admin/v1/instructor-applications/{application_id}"),
    ("get", "/api/admin/v1/attendance"),
    ("get", "/api/admin/v1/attendance/{attendance_id}"),
    ("get", "/api/admin/v1/applications"),
    ("get", "/api/admin/v1/applications/{application_id}"),
    ("get", "/api/admin/v1/waitlist"),
    ("get", "/api/admin/v1/waitlist/{course_id}"),
    ("get", "/api/admin/v1/transactions"),
    ("get", "/api/admin/v1/transactions/{transaction_id}"),
    ("post", "/api/admin/v1/transactions/{transaction_id}/recheck"),
    ("post", "/api/admin/v1/transactions/{transaction_id}/manual-reconcile"),
    ("get", "/api/admin/v1/refunds"),
    ("post", "/api/admin/v1/refunds"),
    ("get", "/api/admin/v1/refunds/{refund_id}"),
    ("put", "/api/admin/v1/refunds/{refund_id}/hold"),
    ("post", "/api/admin/v1/refunds/{refund_id}/release-hold"),
    ("put", "/api/admin/v1/refunds/{refund_id}/approve"),
    ("put", "/api/admin/v1/refunds/{refund_id}/reject"),
    ("post", "/api/admin/v1/refunds/{refund_id}/execute"),
    ("post", "/api/admin/v1/refunds/{refund_id}/confirm-done"),
    ("get", "/api/admin/v1/members"),
    ("get", "/api/admin/v1/members/{member_id}"),
    ("post", "/api/admin/v1/members/{member_id}/reveal"),
    ("post", "/api/admin/v1/members/{member_id}/reviews"),
    ("post", "/api/admin/v1/members/{member_id}/reviews/{review_id}/close"),
    ("post", "/api/admin/v1/members/{member_id}/residence"),
    ("get", "/api/admin/v1/boards"),
    ("put", "/api/admin/v1/boards/{board_key}"),
    ("get", "/api/admin/v1/posts"),
    ("post", "/api/admin/v1/posts"),
    ("get", "/api/admin/v1/posts/{post_id}"),
    ("put", "/api/admin/v1/posts/{post_id}"),
    ("delete", "/api/admin/v1/posts/{post_id}"),
    ("get", "/api/admin/v1/inquiry-categories"),
    ("get", "/api/admin/v1/inquiries"),
    ("get", "/api/admin/v1/inquiries/{inquiry_id}"),
    ("put", "/api/admin/v1/inquiries/{inquiry_id}/answer"),
    ("get", "/api/admin/v1/contents"),
    ("post", "/api/admin/v1/contents"),
    ("get", "/api/admin/v1/contents/{content_id}"),
    ("put", "/api/admin/v1/contents/{content_id}"),
    ("get", "/api/admin/v1/terms"),
    ("get", "/api/admin/v1/terms/versions/{version_id}"),
    ("post", "/api/admin/v1/terms/{term_type}/versions"),
    ("put", "/api/admin/v1/terms/versions/{version_id}"),
    ("post", "/api/admin/v1/terms/versions/{version_id}/fix"),
    ("post", "/api/admin/v1/terms/versions/{version_id}/publish"),
    ("get", "/api/admin/v1/files"),
    ("get", "/api/admin/v1/files/{file_id}"),
    ("get", "/api/admin/v1/dashboard"),
    ("get", "/api/admin/v1/stats/demand"),
    ("get", "/api/admin/v1/stats/settlement"),
    ("get", "/api/admin/v1/stats/attendance"),
    ("get", "/api/admin/v1/stats/age-gender"),
    ("get", "/api/admin/v1/stats/satisfaction"),
    ("get", "/api/admin/v1/sms"),
    ("get", "/api/admin/v1/sms/{sms_id}"),
    ("post", "/api/admin/v1/sms/preview"),
    ("post", "/api/admin/v1/sms"),
    ("get", "/api/admin/v1/role-assignment-options"),
    ("get", "/api/admin/v1/role-assignments"),
    ("get", "/api/admin/v1/role-assignments/{assignment_id}"),
    ("post", "/api/admin/v1/role-assignments"),
    ("post", "/api/admin/v1/role-assignments/{assignment_id}/revoke"),
    ("get", "/api/admin/v1/reductions"),
    ("get", "/api/admin/v1/reductions/{review_id}"),
    ("post", "/api/admin/v1/reductions/{review_id}/decision"),
    ("post", "/api/admin/v1/reductions/{review_id}/re-review"),
    ("get", "/api/admin/v1/reduction-history"),
    ("get", "/api/admin/v1/settings"),
    ("get", "/api/admin/v1/settings/{setting_id}"),
    ("get", "/api/admin/v1/code-groups"),
    ("get", "/api/admin/v1/codes"),
    ("put", "/api/admin/v1/codes"),
    ("get", "/api/admin/v1/course-classes"),
    ("post", "/api/admin/v1/course-classes"),
    ("put", "/api/admin/v1/course-classes/{class_id}"),
    ("post", "/api/admin/v1/course-classes/{class_id}/deactivate"),
    ("post", "/api/admin/v1/course-classes/{class_id}/activate"),
    ("delete", "/api/admin/v1/course-classes/{class_id}"),
    ("get", "/api/admin/v1/course-classes/{class_id}/history"),
    ("get", "/api/admin/v1/retention"),
    ("get", "/api/admin/v1/retention/{item_id}"),
    ("post", "/api/admin/v1/retention/{item_id}/execute"),
    ("get", "/api/admin/v1/posts/{post_id}/files"),
    ("post", "/api/admin/v1/posts/{post_id}/files"),
    ("get", "/api/admin/v1/courses/{course_id}/files"),
    ("post", "/api/admin/v1/courses/{course_id}/files"),
    ("get", "/api/admin/v1/refunds/{refund_id}/files"),
    ("post", "/api/admin/v1/refunds/{refund_id}/files"),
    ("get", "/api/admin/v1/instructor-applications/{application_id}/files"),
    ("post", "/api/admin/v1/instructor-applications/{application_id}/files"),
    ("get", "/api/admin/v1/contents/{content_id}/files"),
    ("post", "/api/admin/v1/contents/{content_id}/files"),
    ("get", "/api/admin/v1/applications/export.csv"),
    ("get", "/api/admin/v1/transactions/export.csv"),
    ("get", "/api/admin/v1/refunds/export.csv"),
    ("get", "/api/admin/v1/stats/demand/export.csv"),
    ("get", "/api/admin/v1/stats/settlement/export.csv"),
    ("get", "/api/admin/v1/stats/age-gender/export.csv"),
    ("get", "/api/admin/v1/posts/export.csv"),
    ("get", "/api/admin/v1/inquiries/export.csv"),
    ("get", "/api/admin/v1/courses/export.csv"),
    ("get", "/api/admin/v1/cycles/export.csv"),
    ("post", "/api/admin/v1/exports/pii"),
    ("delete", "/api/admin/v1/files/{file_id}"),
    ("get", "/api/admin/v1/files/{file_id}/download"),
}
ADMIN_PREFIX = "/api/admin/v1/"
# 상태를 바꾸지만 CSRF 헤더 대상이 아닌 경로는 없다. GET 외 모든 요청이 대상이다.
IDEMPOTENT_POSTS = {
    ("post", "/api/v1/me/applications"),
    ("post", "/api/v1/me/applications/{application_id}/payments"),
    ("post", "/api/v1/me/refunds"),
    ("post", "/api/v1/me/instructor-applications/{application_id}/files"),
    ("post", "/api/v1/me/inquiries/{post_id}/files"),
    ("post", "/api/v1/me/reduction-reviews"),
    ("post", "/api/v1/me/reduction-reviews/{review_id}/files"),
    ("post", "/api/admin/v1/cycles"),
    ("post", "/api/admin/v1/courses"),
    ("post", "/api/admin/v1/facilities"),
    ("post", "/api/admin/v1/courses/{course_id}/schedules"),
    ("post", "/api/admin/v1/courses/{course_id}/schedule-changes"),
    ("post", "/api/admin/v1/instructor-applications"),
    ("post", "/api/admin/v1/refunds"),
    ("post", "/api/admin/v1/members/{member_id}/reviews"),
    ("post", "/api/admin/v1/posts"),
    ("post", "/api/admin/v1/contents"),
    ("post", "/api/admin/v1/terms/{term_type}/versions"),
    ("post", "/api/admin/v1/sms"),
    ("post", "/api/admin/v1/role-assignments"),
    ("post", "/api/admin/v1/reductions/{review_id}/re-review"),
    ("post", "/api/admin/v1/course-classes"),
    ("post", "/api/admin/v1/retention/{item_id}/execute"),
    ("post", "/api/admin/v1/posts/{post_id}/files"),
    ("post", "/api/admin/v1/courses/{course_id}/files"),
    ("post", "/api/admin/v1/refunds/{refund_id}/files"),
    ("post", "/api/admin/v1/instructor-applications/{application_id}/files"),
    ("post", "/api/admin/v1/contents/{content_id}/files"),
    ("post", "/api/admin/v1/exports/pii"),
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
    assert set(operations(spec)) == EXPECTED_OPERATIONS | ADMIN_OPERATIONS


def test_모든_경로는_주민_또는_관리자_api_아래에_있다(spec: Schema) -> None:
    assert all(path.startswith(("/api/v1/", ADMIN_PREFIX)) for path in spec["paths"])


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


def test_관리자_세션이_필요한_엔드포인트는_관리자_쿠키만_요구한다(spec: Schema) -> None:
    # 로그인과 세션 조회만 세션 없이 부른다. 나머지는 모두 관리자 세션 쿠키가 필요하다.
    open_operations = {("post", "/api/admin/v1/auth/login"), ("get", "/api/admin/v1/auth/session")}
    for (method, path), operation in operations(spec).items():
        if path.startswith(ADMIN_PREFIX):
            expected: list[dict[str, list[str]]] | None = (
                None if (method, path) in open_operations else [{"adminSessionCookie": []}]
            )
            assert operation.get("security") == expected, f"{method} {path}"
    scheme = spec["components"]["securitySchemes"]["adminSessionCookie"]
    assert scheme["in"] == "cookie"
    assert scheme["name"] != spec["components"]["securitySchemes"]["sessionCookie"]["name"]


def test_권한_응답은_서버가_만든_메뉴와_기능권한_코드를_담는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    permission_fields = set(schemas["AdminPermissions"]["properties"])
    assert permission_fields == {"roleNames", "scopeLabel", "authorities", "menu"}
    codes = set(schemas["AdminAuthority"]["enum"])
    assert "AU.RFND_A" in codes and "AU.RFND_X" in codes
    assert "AU.MBR_W" not in codes  # 회원 수정은 비활성(FN-065)
    assert all(code.startswith("AU.") for code in codes)


def test_관리자_세션_응답은_만료_시각과_서버_시각을_담는다(spec: Schema) -> None:
    properties = spec["components"]["schemas"]["AdminSession"]["properties"]
    assert {"serverNow", "expiresAt", "idleTimeoutSeconds", "csrfToken", "admin"} <= set(properties)


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


def test_환불_접수_모델에는_금액_필드가_없고_계좌는_선택이다(spec: Schema) -> None:
    model = spec["components"]["schemas"]["RefundCreate"]
    assert set(model["properties"]) == {
        "applicationId",
        "reason",
        "bankCode",
        "accountHolder",
        "accountNumber",
    }
    assert model["required"] == ["applicationId"]


def test_신청은_영수증_조회에_쓸_결제_일련번호를_가진다(spec: Schema) -> None:
    summary = spec["components"]["schemas"]["ApplicationSummary"]["properties"]
    # 영수증 API는 결제 번호로 조회한다. 신청 응답에 없으면 화면이 영수증 링크를 만들 수 없다.
    assert "paymentId" in summary
    assert "x-serial" in str(summary["paymentId"])


def test_신청은_목록의_환불상태_칸에_쓸_최근_환불_단계를_가진다(spec: Schema) -> None:
    summary = spec["components"]["schemas"]["ApplicationSummary"]["properties"]
    # 내 신청 내역 표에 환불상태 칸이 있다. 서버가 정한 값이 없으면 화면이 환불 여부를 알 수 없다.
    assert "refundStage" in summary


def test_안내_콘텐츠는_이름_붙은_문서로_절_단위로_내려준다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    # 화면은 서버가 준 문서를 그리기만 한다. 안내·센터소개 글을 화면 코드에 두지 않는다.
    assert schemas["ContentSlug"]["enum"] == [
        "guide-apply",
        "guide-refund",
        "center-history",
        "center-facility",
    ]
    document = schemas["ContentDocument"]["properties"]
    assert {"slug", "title", "subtitle", "sections", "updatedOn"} <= set(document)
    section = schemas["ContentSection"]["properties"]
    assert {"heading", "paragraphs", "steps", "items", "table", "links"} <= set(section)
    operation = spec["paths"]["/api/v1/contents/{slug}"]["get"]
    assert "404" in operation["responses"]


def test_거주지는_본인_입력과_센터_확인_상태를_구분한다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    profile = schemas["MemberProfile"]["properties"]
    # 스키마 설계안은 확인된 거주구분(HAB_RGN_CD)과 회원의 자가 입력을 구분한다.
    # 자가 입력만으로 우선접수를 판정하지 않는다.
    assert {"residenceDeclared", "residenceStatus"} <= set(profile)
    assert set(schemas["ProfileUpdate"]["properties"]) == {"email", "residenceDeclared"}
    assert schemas["ResidenceStatus"]["enum"] == ["UNVERIFIED", "VERIFIED"]


def test_아이디_찾기_결과는_마스킹된_값만_내려준다(spec: Schema) -> None:
    result = spec["components"]["schemas"]["FindIdResult"]["properties"]
    assert set(result) == {"maskedLoginId"}
    assert "loginId" not in result


def test_비밀번호_변경_재설정_탈퇴_요청은_새_비밀번호_길이를_제한한다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    for name, field in [("PasswordChange", "newPassword"), ("PasswordResetRequest", "newPassword")]:
        prop = schemas[name]["properties"][field]
        assert (prop["minLength"], prop["maxLength"]) == (10, 64), name
    assert set(schemas["WithdrawalRequest"]["properties"]) == {"password", "reason"}
    assert schemas["WithdrawalReason"]["enum"] == ["NO_COURSE", "DIFFICULT", "OTHER"]


def test_게시판은_7개_키로_조회하고_게시물은_목록과_상세로_나눈다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert schemas["BoardKey"]["enum"] == ["notice", "news", "resources", "gallery", "faq", "qna", "review"]
    summary = schemas["PostSummary"]["properties"]
    # 상단공지 구분(pinned), 자료실의 '자료 보기'(primaryFile), 갤러리 썸네일, FAQ 본문(body)을
    # 목록이 바로 담는다.
    assert {"postId", "board", "title", "publishedAt", "pinned", "body", "primaryFile", "thumbnail"} <= set(
        summary
    )
    detail = schemas["PostDetail"]["properties"]
    assert {"body", "facts", "attachments", "images"} <= set(detail)
    list_params = {p["name"] for p in spec["paths"]["/api/v1/boards/{board}/posts"]["get"]["parameters"]}
    assert {"q", "page", "size"} <= list_params


def test_첨부_다운로드는_이진_응답이고_없는_파일은_404다(spec: Schema) -> None:
    operation = spec["paths"]["/api/v1/files/{file_id}"]["get"]
    assert "application/octet-stream" in operation["responses"]["200"]["content"]
    assert "404" in operation["responses"]


def test_문의는_비공개_가림과_본인_여부_수정_가능_여부를_서버가_정해_내려준다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    summary = schemas["InquirySummary"]["properties"]
    # 다른 회원의 비공개 문의는 서버가 제목·작성자를 가려 내려준다. 화면은 그대로 그린다.
    assert {
        "postId",
        "categoryName",
        "title",
        "authorName",
        "status",
        "isPrivate",
        "isMine",
        "publishedAt",
    } <= set(summary)
    assert schemas["InquiryStatus"]["enum"] == ["RECEIVED", "ANSWERED"]
    detail = schemas["InquiryDetail"]["properties"]
    assert {"body", "answer", "canEdit", "canDelete", "categoryId"} <= set(detail)
    # 답변은 한 단계다(FN-053).
    assert "$ref" in detail["answer"] or "anyOf" in detail["answer"]


def test_문의와_후기_작성_요청은_분류와_자격을_서버_값으로만_받는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    inquiry = schemas["InquiryWrite"]["properties"]
    assert set(inquiry) == {"categoryId", "title", "body", "isPrivate"}
    assert (inquiry["title"]["maxLength"], inquiry["body"]["maxLength"]) == (100, 2000)
    review = schemas["ReviewWrite"]["properties"]
    assert set(review) == {"courseId", "title", "body"}
    assert (review["title"]["maxLength"], review["body"]["maxLength"]) == (100, 2000)
    # 문의 분류 값은 공통코드(IQ)에서 서버가 내려준다. 화면에 고정하지 않는다(PRD Q26).
    assert "InquiryCategoryList" in schemas
    assert "ReviewableCourseList" in schemas


def test_공개_강사는_심사_증빙_없이_소개용_값만_내려준다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    summary = schemas["InstructorSummary"]["properties"]
    assert set(summary) == {"instructorId", "name", "categoryName", "courseNames"}
    detail = schemas["InstructorDetail"]["properties"]
    # 경력·자격은 공식 자료에 없으면 null이다. 지원 심사 증빙은 어떤 공개 응답에도 없다(FN-018).
    assert {"career", "courseNames", "categoryName"} <= set(detail)
    assert not any("evidence" in name.lower() or "proof" in name.lower() for name in detail)
    list_params = {p["name"] for p in spec["paths"]["/api/v1/instructors"]["get"]["parameters"]}
    assert {"q", "page", "size"} <= list_params


def test_모집공고는_지원_가능_여부를_서버가_정한다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert schemas["RecruitmentStatus"]["enum"] == ["UPCOMING", "OPEN", "CLOSED"]
    summary = schemas["RecruitmentSummary"]["properties"]
    assert {"recruitmentId", "title", "status", "periodStart", "periodEnd", "headcount"} <= set(summary)
    # 모집중인 공고에만 지원하기를 보인다(FN-019). 화면은 날짜를 비교하지 않고 이 값을 따른다.
    assert "canApply" in schemas["RecruitmentDetail"]["properties"]


def test_강사_지원서는_텍스트_항목만_받고_심사_상태를_서버가_정한다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    create = schemas["InstructorApplyWrite"]["properties"]
    assert set(create) == {"recruitmentId", "desiredCourse", "categoryId", "career"}
    assert create["desiredCourse"]["maxLength"] == 100 and create["career"]["maxLength"] == 2000
    assert schemas["InstructorApplyStatus"]["enum"] == [
        "REVIEWING",
        "SUPPLEMENT",
        "INTERVIEW",
        "SELECTED",
        "REJECTED",
    ]
    application = schemas["InstructorApplication"]["properties"]
    assert {"applicationId", "recruitmentTitle", "desiredCourse", "status", "canEdit", "appliedAt"} <= set(
        application
    )


def test_수정_요청은_읽은_버전을_함께_보낸다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    for name in ("CycleUpdate", "CourseUpdate"):
        assert "version" in schemas[name]["required"], name
    for name in ("CycleWrite", "CourseWrite"):
        assert "version" not in schemas[name]["properties"], name


def test_강좌_응답은_서버가_정한_버튼_가능_여부를_담고_정원_배분_입력은_없다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["CourseActions"]["properties"]) == {
        "canEdit",
        "canPublish",
        "canCloseReception",
        "canCancel",
    }
    write_fields = set(schemas["CourseWrite"]["properties"])
    assert not {"onlineCapacity", "visitCapacity"} & write_fields  # FN-048
    assert "version" in schemas["AdminCourse"]["required"]


def test_폐강은_영향_범위_조회_뒤_사유와_함께_요청한다(spec: Schema) -> None:
    ops = operations(spec)
    preview = ops[("get", "/api/admin/v1/courses/{course_id}/cancel-preview")]
    reference = preview["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert reference.endswith("/CancelPreview")
    assert set(spec["components"]["schemas"]["CancelCourseRequest"]["properties"]) == {"reason"}
    publish = ops[("post", "/api/admin/v1/courses/{course_id}/publish")]
    assert "requestBody" not in publish


def test_시설과_일정_수정_요청은_읽은_버전을_함께_보낸다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    for name in ("FacilityUpdate", "ScheduleUpdate"):
        assert "version" in schemas[name]["required"], name
    for name in ("FacilityWrite", "ScheduleWrite", "ScheduleChangeWrite"):
        assert "version" not in schemas[name]["properties"], name


def test_일정과_휴보강은_시각을_HH_MM_문자열로_받는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    for name in ("ScheduleWrite", "ScheduleChangeWrite"):
        for field in ("startTime", "endTime"):
            options = schemas[name]["properties"][field]
            patterns = [options.get("pattern")] + [
                option.get("pattern") for option in options.get("anyOf", [])
            ]
            assert any(pattern and "2[0-3]" in pattern for pattern in patterns), f"{name}.{field}"


def test_강의실_선택지는_강좌_옵션에_있고_시설_조회는_시설_권한_전용이다(spec: Schema) -> None:
    assert "rooms" in spec["components"]["schemas"]["CourseOptions"]["properties"]
    facility_paths = [path for path in spec["paths"] if path.startswith("/api/admin/v1/facilities")]
    assert len(facility_paths) == 2


def test_강사_심사_수정은_읽은_버전을_보내고_승인해도_권한을_주지_않는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert "version" in schemas["InstructorReviewWrite"]["required"]
    assert set(schemas["ReviewStatus"]["enum"]) == {"PENDING", "APPROVED", "REJECTED", "SUSPENDED"}
    # 심사 요청에는 강좌 배정이나 관리자 권한을 부여하는 필드가 없다(FN-051).
    assert set(schemas["InstructorReviewWrite"]["properties"]) == {
        "status",
        "reason",
        "isPublic",
        "memo",
        "version",
    }


def test_출석_응답은_조회_전용이고_연락처_생년_결제정보를_담지_않는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["AttendanceRow"]["properties"]) == {"name", "applicationNo", "memberStatus", "mark"}
    forbidden = {"phone", "birth", "birthDate", "amount", "payment", "email"}
    for name in ("AttendanceSummary", "AttendanceDetail", "AttendanceRow"):
        assert not forbidden & set(schemas[name]["properties"]), name
    attendance_ops = {key for key in operations(spec) if key[1].startswith("/api/admin/v1/attendance")}
    assert {method for method, _ in attendance_ops} == {"get"}


def test_강좌_선택지는_범위_안의_강좌를_담는다(spec: Schema) -> None:
    assert "courses" in spec["components"]["schemas"]["CourseOptions"]["properties"]


def test_신청과_대기_조회는_조회_전용이다(spec: Schema) -> None:
    paths = ("/api/admin/v1/applications", "/api/admin/v1/waitlist")
    methods = {method for (method, path) in operations(spec) if path.startswith(paths)}
    assert methods == {"get"}  # 관리자의 신청 상태 직접 변경·수동 승격은 없다(FN-035)


def test_신청_응답은_가려진_이름과_서버가_정한_표시_상태를_담는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    summary = schemas["AdminApplicationSummary"]["properties"]
    assert {"applicantName", "displayState", "status", "paymentStatus", "refundStatus"} <= set(summary)
    forbidden = {"phone", "birth", "birthDate", "email", "address"}
    for name in ("AdminApplicationSummary", "AdminApplication", "Waiter"):
        assert not forbidden & set(schemas[name]["properties"]), name


def test_신청_상세는_원장_이력과_연결_결제_환불_멱등_재요청을_담는다(spec: Schema) -> None:
    detail = spec["components"]["schemas"]["AdminApplication"]["properties"]
    assert {"history", "payment", "refund", "replays", "seatAllottedAt", "paymentDeadlineAt"} <= set(detail)
    assert set(spec["components"]["schemas"]["ReplayOutcome"]["enum"]) == {"SAME_RESULT", "CONFLICT"}


def test_수동_대사는_근거를_필수로_받고_결과는_성공과_실패뿐이다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    request = schemas["ReconcileRequest"]
    assert {"outcome", "evidence", "version"} <= set(request["required"])
    assert set(schemas["ReconcileOutcome"]["enum"]) == {"PAID", "FAILED"}
    assert request["properties"]["evidence"]["minLength"] >= 5


def test_거래_응답은_서버가_정한_조치_가능_여부와_통보_이력을_담고_통보_원문은_없다(spec: Schema) -> None:
    properties = spec["components"]["schemas"]["Transaction"]["properties"]
    assert {"canRecheck", "canReconcile", "notices", "actions", "recheckCount", "recheckMax"} <= set(
        properties
    )
    notice = spec["components"]["schemas"]["PgNotice"]["properties"]
    assert set(notice) == {"at", "hashPrefix", "handling"}
    assert set(spec["components"]["schemas"]["NoticeHandling"]["enum"]) == {"DONE", "DUPLICATE", "CONFLICT"}


def test_결제_조치는_거래_번호_아래_두_개뿐이고_취소나_실패_강제_엔드포인트는_없다(spec: Schema) -> None:
    posts = {path for (method, path) in operations(spec) if method == "post" and "/transactions/" in path}
    assert posts == {
        "/api/admin/v1/transactions/{transaction_id}/recheck",
        "/api/admin/v1/transactions/{transaction_id}/manual-reconcile",
    }


def test_환불_결정과_집행_요청은_읽은_버전을_함께_보낸다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    for name in ("RefundHoldRequest", "RefundApproveRequest", "RefundRejectRequest", "RefundVersionRequest"):
        assert "version" in schemas[name]["required"], name
    assert "version" not in schemas["AdminRefundCreate"]["properties"]


def test_환불_응답은_서버가_정한_가능_여부와_계산값을_담고_계좌는_가려서_준다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    properties = schemas["AdminRefund"]["properties"]
    flags = {"canReview", "canExecute", "canConfirmTransfer", "executeNote"}
    assert flags <= set(properties)
    assert {"paidAmount", "reservedAmount", "remainingAmount", "baselineAmount", "baselineRule"} <= set(
        properties
    )
    assert set(schemas["ManualAccount"]["properties"]) == {"bankName", "holderMasked", "accountMasked"}


def test_승인과_집행은_별도_엔드포인트이고_원결제액을_바꾸는_필드는_없다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["RefundApproveRequest"]["properties"]) == {"amount", "version"}
    paths = {path for (_, path) in operations(spec) if "/refunds/" in path}
    assert "/api/admin/v1/refunds/{refund_id}/approve" in paths
    assert "/api/admin/v1/refunds/{refund_id}/execute" in paths
    for name in ("AdminRefundCreate", "RefundApproveRequest"):
        assert "paidAmount" not in schemas[name]["properties"], name


def test_회원_API에는_회원_정보를_수정하는_요청이_없다(spec: Schema) -> None:
    member_ops = {
        (method, path) for (method, path) in operations(spec) if path.startswith("/api/admin/v1/members")
    }
    assert not {key for key in member_ops if key[0] in ("put", "patch", "delete")}  # FN-065
    schemas = spec["components"]["schemas"]
    for name in ("AdminMember", "AdminMemberSummary"):
        assert not {"birthDate", "age", "ageBand", "address"} & set(schemas[name]["properties"]), name
    assert set(schemas["MemberStatus"]["enum"]) == {"ACTIVE", "LOCKED", "WITHDRAWN"}


def test_회원_응답은_이름과_연락처를_가려서_주고_원문은_사유와_함께_따로_받는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert {"nameMasked"} <= set(schemas["AdminMemberSummary"]["properties"])
    assert {"phoneMasked", "emailMasked"} <= set(schemas["AdminMember"]["properties"])
    assert "phone" not in schemas["AdminMember"]["properties"]
    assert schemas["RevealRequest"]["properties"]["reason"]["minLength"] >= 5
    assert set(schemas["MemberContact"]["properties"]) == {"phone", "email"}


def test_게시판_설정은_다섯_정책만_담고_이름과_키는_바꾸지_않는다(spec: Schema) -> None:
    update = spec["components"]["schemas"]["BoardSettingUpdate"]
    assert set(update["properties"]) == {
        "memberWrite",
        "answerEnabled",
        "attachEnabled",
        "allowPrivate",
        "inUse",
        "version",
    }
    assert "version" in update["required"]


def test_게시물_수정은_읽은_버전을_보내고_삭제는_논리_삭제_하나다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert "version" in schemas["AdminPostUpdate"]["required"]
    assert "version" not in schemas["AdminPostWrite"]["properties"]
    assert {"canEditContent", "memberAuthored"} <= set(schemas["AdminPost"]["properties"])
    delete = operations(spec)[("delete", "/api/admin/v1/posts/{post_id}")]
    assert "204" in delete["responses"]


def test_문의_답변은_한_단계로_쓰고_고치며_읽은_버전을_보낸다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    write = schemas["InquiryAnswerWrite"]
    assert set(write["properties"]) == {"content", "relatedLink", "version"}
    assert write["properties"]["version"]["minimum"] == 0  # 0은 아직 답변이 없다는 뜻
    answer_ops = {key for key in operations(spec) if "/answer" in key[1]}
    assert answer_ops == {("put", "/api/admin/v1/inquiries/{inquiry_id}/answer")}  # 답변 삭제·다단계 없음


def test_문의_응답은_가려진_작성자와_수정_이력을_담는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert {"authorName", "isPrivate", "status"} <= set(schemas["AdminInquirySummary"]["properties"])
    assert {"answer", "history", "canAnswer", "content"} <= set(schemas["AdminInquiry"]["properties"])
    assert set(schemas["AnswerAction"]["enum"]) == {"CREATED", "EDITED"}
    assert not {"phone", "email", "memberId"} & set(schemas["AdminInquiry"]["properties"])


def test_콘텐츠_유형은_여덟_가지이고_연락처만_구조_입력을_가진다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["ContentType"]["enum"]) == {
        "VISUAL",
        "BANNER",
        "POPUP",
        "HISTORY",
        "INTRO",
        "CONTACT",
        "GUIDE",
        "FACILITY",
    }
    assert "contact" in schemas["AdminContentWrite"]["properties"]
    assert "canCreate" in schemas["AdminContentPage"]["properties"]
    content_ops = {method for (method, path) in operations(spec) if path.startswith("/api/admin/v1/contents")}
    assert "delete" not in content_ops  # 이력이 있는 콘텐츠는 삭제 대신 게시 여부로 끈다


def test_약관_버전은_검토_확정_게시_순서로만_나아가고_수정은_검토_상태만_받는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["TermStatus"]["enum"]) == {"REVIEW", "FIXED", "PUBLISHED", "ENDED"}
    for name in ("TermVersionUpdate", "TermVersionAction"):
        assert "version" in schemas[name]["required"], name
    assert {"canEdit", "canFix", "canPublish", "contentHash"} <= set(schemas["TermVersion"]["properties"])
    term_ops = {key for key in operations(spec) if "/terms" in key[1]}
    assert not {
        key for key in term_ops if key[0] == "delete"
    }  # 게시된 문안은 지우거나 덮어쓰지 않는다(FN-055)


def test_약관_새_버전은_복제_원본을_받고_본문은_선택이다(spec: Schema) -> None:
    create = spec["components"]["schemas"]["TermVersionCreate"]
    assert {"baseVersionId", "body"} <= set(create["properties"])
    assert "body" not in create["required"]
    assert "version" not in create["properties"]


def test_첨부파일_조회는_조회_전용이고_차단_사유와_내려받기_감사기록을_담는다(spec: Schema) -> None:
    for path in (
        "/api/admin/v1/files",
        "/api/admin/v1/files/{file_id}",
        "/api/admin/v1/files/{file_id}/download",
    ):
        assert "get" in spec["paths"][path], path
    assert "post" not in spec["paths"]["/api/admin/v1/files"]  # 올리기는 소유 업무 경로로만 한다
    schemas = spec["components"]["schemas"]
    assert {"blockReason", "downloads", "hashPrefix"} <= set(schemas["AdminFile"]["properties"])
    assert set(schemas["FileStatus"]["enum"]) == {"PENDING", "SAFE", "BLOCK", "DELETE"}
    forbidden = {"storageKey", "strgKey", "path", "url"}
    assert not forbidden & set(schemas["AdminFile"]["properties"])  # 저장소 키·경로는 내보내지 않는다


def test_통계는_조회_전용이고_집계_기준과_자료_없음을_구분해_싣는다(spec: Schema) -> None:
    stat_ops = {
        key
        for key in operations(spec)
        if key[1].startswith(("/api/admin/v1/stats", "/api/admin/v1/dashboard"))
    }
    assert {method for method, _ in stat_ops} == {"get"}
    schemas = spec["components"]["schemas"]
    for name in (
        "Dashboard",
        "DemandStats",
        "SettlementStats",
        "AttendanceStatsReport",
        "AgeGenderStats",
        "SatisfactionStats",
    ):
        assert "basis" in schemas[name]["required"], name
    for name in ("AgeGenderStats", "SatisfactionStats"):
        assert "source" in schemas[name]["required"], name  # 승인 자료가 없으면 null로 구분한다
    assert "unknownAmount" in schemas["SettlementStats"]["properties"]  # 확인 중 금액은 순수납과 따로 둔다
    assert set(schemas["DashboardTaskKind"]["enum"]) == {
        "PAYMENT_UNKNOWN",
        "REFUND_REVIEW",
        "INSTRUCTOR_REVIEW",
        "INQUIRY_ANSWER",
        "SMS_FAILED",
    }


def test_문자_발송은_최종_확인과_예상_수신자_수를_받고_멱등키를_요구한다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert {"confirmed", "expectedRecipientCount"} <= set(schemas["SmsSendRequest"]["required"])
    assert {"scope", "statuses", "content"} <= set(schemas["SmsAudience"]["required"])
    assert "idempotency-key" in {
        param["name"].lower() for param in spec["paths"]["/api/admin/v1/sms"]["post"]["parameters"]
    }
    assert "/api/admin/v1/sms/{sms_id}" in spec["paths"]
    assert {method for method in spec["paths"]["/api/admin/v1/sms/{sms_id}"]} == {"get"}  # 수정·삭제 없음


def test_문자_이력은_수신번호와_이름을_가려서_주고_원문_번호를_담지_않는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    forbidden = {"rawPhone", "phoneNumber", "telno", "encryptedPhone"}
    for name in ("SmsTargetRow", "SmsRecipient"):
        assert not forbidden & set(schemas[name]["properties"]), name
    assert set(schemas["SmsTargetState"]["enum"]) == {"WAIT", "SENDING", "SENT", "FAIL", "UNKNOWN", "SKIP"}
    assert set(schemas["SmsKind"]["enum"]) == {"AUTO", "MANUAL"}


def test_권한_배정은_수정과_삭제_없이_새로_배정하거나_회수만_한다(spec: Schema) -> None:
    role_ops = {key for key in operations(spec) if "/role-assignment" in key[1]}
    assert not {key for key in role_ops if key[0] in {"put", "patch", "delete"}}
    schemas = spec["components"]["schemas"]
    assert "version" in schemas["AssignmentRevoke"]["required"]
    assert {"canRevoke", "authorities", "version"} <= set(schemas["RoleAssignment"]["properties"])
    assert set(schemas["AssignmentStatus"]["enum"]) == {"ACTIVE", "SCHEDULED", "EXPIRED", "REVOKED"}


def test_배정_요청은_역할_범위_유효기간을_한_행으로_받고_동은_선택이다(spec: Schema) -> None:
    create = spec["components"]["schemas"]["AssignmentCreate"]
    assert {"adminId", "roleId", "scope", "validFrom"} <= set(create["required"])
    assert "dongId" not in create["required"]
    assert "validTo" not in create["required"]


def test_감면_심사는_결정에_버전과_결과를_받고_삭제_수정_없이_재심사로_새_건을_만든다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert {"decision", "version"} <= set(schemas["ReductionDecisionRequest"]["required"])
    assert set(schemas["ReductionDecision"]["enum"]) == {"APPROVE", "REJECT"}
    assert set(schemas["ReductionStatus"]["enum"]) == {"RECEIVED", "APPROVED", "REJECTED", "REVOKED"}
    assert {"canDecide", "canReReview", "residenceConfirmed", "evidenceViews"} <= set(
        schemas["ReductionReview"]["properties"]
    )
    reduction_ops = {key for key in operations(spec) if "/reduction" in key[1]}
    assert not {key for key in reduction_ops if key[0] in {"put", "patch", "delete"}}


def test_감면_이력은_조회_전용이고_증빙_파일의_저장_위치를_담지_않는다(spec: Schema) -> None:
    history_ops = {method for (method, path) in operations(spec) if path == "/api/admin/v1/reduction-history"}
    assert history_ops == {"get"}
    forbidden = {"storageKey", "strgKey", "path", "url"}
    for name in ("ReductionEvidence", "ReductionHistoryRow", "ReductionReview"):
        assert not forbidden & set(spec["components"]["schemas"][name]["properties"]), name


def test_운영_설정은_조회_전용이고_검토_상태를_게시와_구분해_싣는다(spec: Schema) -> None:
    setting_ops = {method for (method, path) in operations(spec) if path.startswith("/api/admin/v1/settings")}
    assert setting_ops == {"get"}
    schemas = spec["components"]["schemas"]
    assert set(schemas["OperRuleStatus"]["enum"]) == {"REVIEW", "DECIDED", "HOLD"}
    assert {"body", "version"} <= set(schemas["SettingDetail"]["properties"])


def test_공통_코드는_표시명_순서_사용만_고치고_추가_삭제_없이_참조_건수를_알린다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["CodeRowUpdate"]["properties"]) == {"code", "name", "sortSeq", "use"}
    assert "refCount" in schemas["CodeRow"]["required"]  # 확인 실패는 null로 구분한다
    code_ops = {method for (method, path) in operations(spec) if path == "/api/admin/v1/codes"}
    assert code_ops == {"get", "put"}  # 코드 추가·삭제 API가 없다


def test_강좌분류는_연결_강좌_수_확인_실패를_null로_구분하고_중지_삭제_가능_여부를_서버가_알린다(
    spec: Schema,
) -> None:
    schemas = spec["components"]["schemas"]
    assert {"courseCount", "canDeactivate", "canDelete", "version"} <= set(schemas["CourseClass"]["required"])
    count = schemas["CourseClass"]["properties"]["courseCount"]
    assert any(option.get("type") == "null" for option in count["anyOf"])  # 0이 아니라 null이 확인 실패다
    assert set(schemas["ClassHistoryAction"]["enum"]) == {
        "CREATE",
        "RENAME",
        "REORDER",
        "DEACTIVATE",
        "ACTIVATE",
        "DELETE",
    }


def test_강좌분류_삭제는_읽은_버전을_받고_이력은_조회_전용이다(spec: Schema) -> None:
    delete_params = {
        param["name"]
        for param in spec["paths"]["/api/admin/v1/course-classes/{class_id}"]["delete"]["parameters"]
    }
    assert "version" in delete_params
    history_ops = {method for method in spec["paths"]["/api/admin/v1/course-classes/{class_id}/history"]}
    assert history_ops == {"get"}


def test_보존_파기는_실행에_확인한_건수와_멱등키를_요구하고_삭제_API는_없다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert "expectedCount" in schemas["RetentionExecute"]["required"]
    assert {"canExecute", "executions", "fields", "rule"} <= set(schemas["RetentionDetail"]["required"])
    assert {"exclusions", "items"} <= set(schemas["RetentionList"]["required"])
    retention_ops = {key for key in operations(spec) if "/retention" in key[1]}
    assert not {key for key in retention_ops if key[0] in {"put", "patch", "delete"}}
    assert set(schemas["RetentionState"]["enum"]) == {"DUE", "WAITING", "REVIEW_ONLY", "PERIOD_TBD"}


def test_보존기간이_정해지지_않은_자료는_예정일을_null로_구분한다(spec: Schema) -> None:
    due = spec["components"]["schemas"]["RetentionItem"]["properties"]["dueOn"]
    assert any(option.get("type") == "null" for option in due["anyOf"])


def test_파일_올리기는_multipart로_한_개씩_받고_한도는_응답이_알려_준다(spec: Schema) -> None:
    for path in (
        "/api/admin/v1/posts/{post_id}/files",
        "/api/admin/v1/courses/{course_id}/files",
        "/api/admin/v1/refunds/{refund_id}/files",
        "/api/admin/v1/instructor-applications/{application_id}/files",
        "/api/admin/v1/contents/{content_id}/files",
    ):
        body = spec["paths"][path]["post"]["requestBody"]["content"]
        assert set(body) == {"multipart/form-data"}, path
    schemas = spec["components"]["schemas"]
    assert {"canEdit", "maxFiles", "maxBytes", "allowedExtensions"} <= set(
        schemas["OwnerFileList"]["required"]
    )
    assert {"REDUCTION", "SATISFACTION_SOURCE"} <= set(schemas["FileOwnerKind"]["enum"])


def test_내려받기는_바이너리로_답하고_제거는_논리삭제_삭제_응답만_둔다(spec: Schema) -> None:
    download = spec["paths"]["/api/admin/v1/files/{file_id}/download"]["get"]["responses"]["200"]["content"]
    assert set(download) == {"application/octet-stream"}
    assert "204" in spec["paths"]["/api/admin/v1/files/{file_id}"]["delete"]["responses"]
    forbidden = {"storageKey", "strgKey", "path", "url", "hash"}
    assert not forbidden & set(spec["components"]["schemas"]["OwnerFile"]["properties"])


def test_감면_증빙은_열람_전용_API_없이_내려받기가_감사기록을_남긴다(spec: Schema) -> None:
    reduction_paths = [path for path in spec["paths"] if "/reductions/" in path]
    assert not [path for path in reduction_paths if path.endswith("/evidence-views")]
    assert "evidenceViews" in spec["components"]["schemas"]["ReductionReview"]["properties"]
    assert "EvidenceViewRequest" not in spec["components"]["schemas"]


def test_회원_첨부는_자기_지원서와_문의에만_올리고_내려받기는_바이너리로_답한다(spec: Schema) -> None:
    for path in (
        "/api/v1/me/instructor-applications/{application_id}/files",
        "/api/v1/me/inquiries/{post_id}/files",
    ):
        assert set(spec["paths"][path]["post"]["requestBody"]["content"]) == {"multipart/form-data"}, path
    download = spec["paths"]["/api/v1/me/files/{file_id}"]["get"]["responses"]["200"]["content"]
    assert set(download) == {"application/octet-stream"}
    schemas = spec["components"]["schemas"]
    assert {"canEdit", "maxFiles", "maxBytes", "allowedExtensions"} <= set(schemas["MyFileList"]["required"])
    forbidden = {"storageKey", "strgKey", "path", "url", "hash", "hashPrefix"}
    assert not forbidden & set(schemas["MyFile"]["properties"])


def test_회원_감면_신청은_금액과_비율을_받지_않고_기수와_유형만_받는다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    assert set(schemas["MyReductionCreate"]["properties"]) == {"cycleId", "reductionType"}
    assert {"canApply", "blockReason", "cycles"} <= set(schemas["MyReductionOptions"]["required"])
    assert {"canAddEvidence", "canWithdraw", "validUntil", "rejectReason"} <= set(
        schemas["MyReduction"]["properties"]
    )
    forbidden = {"reviewedBy", "reviewNote", "residenceConfirmed", "amount", "memberName"}
    for name in ("MyReduction", "MyReductionSummary"):
        assert not forbidden & set(schemas[name]["properties"]), (
            name
        )  # 심사 내용·처리자·금액은 신청자에게 주지 않는다
    reduction_ops = {key for key in operations(spec) if key[1].startswith("/api/v1/me/reduction-reviews")}
    assert not {
        key for key in reduction_ops if key[0] in {"put", "patch", "delete"}
    }  # 결정된 신청은 고치거나 지우지 않는다


def test_홈_응답은_비주얼_배너_팝업을_담고_이미지는_공개_주소와_대체_문구만_가진다(spec: Schema) -> None:
    schemas = spec["components"]["schemas"]
    home = schemas["HomeResponse"]
    assert {"visual", "banners", "popups"} <= set(home["properties"])
    assert {"banners", "popups"} <= set(home["required"])  # 없으면 빈 목록이다
    assert "visual" not in home.get("required", []) or "null" in type_names(home["properties"]["visual"])
    assert set(schemas["HomeImage"]["properties"]) == {"url", "alt"}
    for name in ("HomeBanner", "HomePopup"):
        assert {"contentId", "title", "linkUrl", "image"} <= set(schemas[name]["properties"]), name
    forbidden = {"storageKey", "hash", "fileId", "periodStart", "periodEnd", "posted"}
    for name in ("HomeVisual", "HomeBanner", "HomePopup", "HomeImage"):
        assert not forbidden & set(schemas[name]["properties"]), (
            name
        )  # 게시 판정은 서버가 하고 값은 내려주지 않는다


CSV_EXPORTS = {
    "/api/admin/v1/applications": "/api/admin/v1/applications/export.csv",
    "/api/admin/v1/transactions": "/api/admin/v1/transactions/export.csv",
    "/api/admin/v1/refunds": "/api/admin/v1/refunds/export.csv",
    "/api/admin/v1/stats/demand": "/api/admin/v1/stats/demand/export.csv",
    "/api/admin/v1/stats/settlement": "/api/admin/v1/stats/settlement/export.csv",
    "/api/admin/v1/posts": "/api/admin/v1/posts/export.csv",
    "/api/admin/v1/inquiries": "/api/admin/v1/inquiries/export.csv",
    "/api/admin/v1/courses": "/api/admin/v1/courses/export.csv",
    "/api/admin/v1/cycles": "/api/admin/v1/cycles/export.csv",
}


def test_CSV는_목록과_같은_조건을_받고_페이지_제한만_없으며_텍스트로_답한다(spec: Schema) -> None:
    for list_path, export_path in CSV_EXPORTS.items():
        listed = {p["name"] for p in spec["paths"][list_path]["get"].get("parameters", [])}
        exported = {p["name"] for p in spec["paths"][export_path]["get"].get("parameters", [])}
        assert exported == listed - {"page", "size"}, export_path
    for export_path in (*CSV_EXPORTS.values(), "/api/admin/v1/stats/age-gender/export.csv"):
        responses = spec["paths"][export_path]["get"]["responses"]
        assert set(responses["200"]["content"]) == {"text/csv"}, export_path
        assert "422" in responses, export_path  # 5만 행을 넘으면 거절한다


def test_출석과_만족도와_회원_명단은_CSV로_내보내지_않는다(spec: Schema) -> None:
    exports = [path for path in spec["paths"] if path.endswith("/export.csv")]
    forbidden = (
        "attendance",
        "satisfaction",
        "members",
    )  # 출석·만족도는 금지, 개인식별 명단은 별도 권한의 암호 ZIP(첨부-5)
    assert not [path for path in exports if any(word in path for word in forbidden)]


def test_개인식별_명단은_암호_ZIP을_한_번만_주고_멱등키를_요구하며_대상은_회원과_신청뿐이다(
    spec: Schema,
) -> None:
    post = spec["paths"]["/api/admin/v1/exports/pii"]["post"]
    ok = post["responses"]["200"]
    assert set(ok["content"]) == {"application/zip"}
    assert "X-Export-Password" in ok["headers"]
    assert {"422", "409"} <= set(post["responses"])
    body = post["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    assert spec["components"]["schemas"][body]["required"] == ["target"]
    assert spec["components"]["schemas"]["PiiExportTarget"]["enum"] == ["MEMBERS", "APPLICATIONS"]
    assert "Idempotency-Key" in {p["name"] for p in post["parameters"]}
