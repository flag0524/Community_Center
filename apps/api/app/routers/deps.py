# 라우터가 공유하는 보안 스킴, 헤더 파라미터, 오류 응답 문서화 도우미
from typing import Annotated, Any

from fastapi import Header
from fastapi.security import APIKeyCookie

from app.core.errors import ERROR_STATUS, ErrorCode, ErrorResponse

SESSION_COOKIE_NAME = "jori_session"
ADMIN_SESSION_COOKIE_NAME = "jori_admin_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"

# 서버 세션 + HttpOnly 쿠키(ADR-008). 골격 단계에서는 문서화만 하고 검증은 P3에서 붙인다.
member_session = APIKeyCookie(
    name=SESSION_COOKIE_NAME,
    scheme_name="sessionCookie",
    auto_error=False,
    description="로그인 뒤 서버가 내려주는 HttpOnly 세션 쿠키",
)


# 관리자 앱은 주민 사이트와 도메인·쿠키를 분리한다(FN-056). 쿠키 이름도 다르다.
admin_session = APIKeyCookie(
    name=ADMIN_SESSION_COOKIE_NAME,
    scheme_name="adminSessionCookie",
    auto_error=False,
    description="관리자 로그인 뒤 서버가 내려주는 HttpOnly 세션 쿠키. 유휴 15분에 만료된다.",
)


def csrf_header(
    x_csrf_token: Annotated[
        str | None,
        Header(
            alias=CSRF_HEADER_NAME,
            description="세션의 csrfToken 값. 상태를 바꾸는 요청마다 서버가 검증한다(DV17).",
        ),
    ] = None,
) -> None:
    """상태 변경 요청이 보내야 하는 CSRF 헤더를 계약에 드러낸다. 검증은 P3에서 구현한다."""


IdempotencyKey = Annotated[
    str,
    Header(
        alias=IDEMPOTENCY_HEADER_NAME,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="버튼을 누른 시점에 만든 값. 재시도에도 같은 값을 쓴다. 같은 키에 다른 내용이면 409.",
    ),
]

ResponsesDoc = dict[int | str, dict[str, Any]]


def error_responses(*codes: ErrorCode) -> ResponsesDoc:
    """HTTP 상태별로 오류 응답을 묶어 OpenAPI에 문서화한다."""
    grouped: dict[int, list[str]] = {}
    for code in codes:
        grouped.setdefault(ERROR_STATUS[code], []).append(code.value)
    return {
        status: {"model": ErrorResponse, "description": "오류 코드: " + ", ".join(names)}
        for status, names in sorted(grouped.items())
    }


PUBLIC_ERRORS = error_responses(
    ErrorCode.VALIDATION_FAILED, ErrorCode.TOO_MANY_REQUESTS, ErrorCode.INTERNAL_ERROR
)
MEMBER_ERRORS = {
    **PUBLIC_ERRORS,
    **error_responses(
        ErrorCode.UNAUTHENTICATED,
        ErrorCode.FORBIDDEN,
        ErrorCode.NOT_FOUND,
        ErrorCode.CONFLICT_STATE,
        ErrorCode.RULE_REJECTED,
    ),
}
