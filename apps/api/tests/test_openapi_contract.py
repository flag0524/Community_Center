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
}
ADMIN_PREFIX = "/api/admin/v1/"
# 상태를 바꾸지만 CSRF 헤더 대상이 아닌 경로는 없다. GET 외 모든 요청이 대상이다.
IDEMPOTENT_POSTS = {
    ("post", "/api/v1/me/applications"),
    ("post", "/api/v1/me/applications/{application_id}/payments"),
    ("post", "/api/v1/me/refunds"),
    ("post", "/api/admin/v1/cycles"),
    ("post", "/api/admin/v1/courses"),
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


def test_환불_접수_모델에는_금액_필드가_없다(spec: Schema) -> None:
    assert set(spec["components"]["schemas"]["RefundCreate"]["properties"]) == {"applicationId", "reason"}


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
