# API 오류 코드 enum, 오류 응답 형식, 요청 ID 부여와 예외 처리기
import logging
import re
import uuid
from enum import StrEnum
from typing import NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.schema import ApiModel

logger = logging.getLogger("app.errors")
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ErrorCode(StrEnum):
    """오류 코드의 유일한 목록이다. 프런트는 이 값으로 분기한다(DV19)."""

    # 공통
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONFLICT_STATE = "CONFLICT_STATE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    RULE_REJECTED = "RULE_REJECTED"
    TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    # 인증
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    OTP_INVALID = "OTP_INVALID"
    OTP_EXPIRED = "OTP_EXPIRED"
    OTP_RESEND_TOO_SOON = "OTP_RESEND_TOO_SOON"
    JOIN_LOGIN_ID_TAKEN = "JOIN_LOGIN_ID_TAKEN"
    # 신청
    APLY_RCPT_CLOSED = "APLY_RCPT_CLOSED"
    APLY_PRIORITY_PERIOD = "APLY_PRIORITY_PERIOD"
    APLY_ALREADY_APPLIED = "APLY_ALREADY_APPLIED"
    APLY_FULL = "APLY_FULL"
    APLY_MEMBER_INACTIVE = "APLY_MEMBER_INACTIVE"
    APLY_CANCEL_NOT_ALLOWED = "APLY_CANCEL_NOT_ALLOWED"
    # 결제
    PAY_NOT_PAYABLE = "PAY_NOT_PAYABLE"
    PAY_DEADLINE_EXPIRED = "PAY_DEADLINE_EXPIRED"
    PAY_RESULT_PENDING = "PAY_RESULT_PENDING"
    PAY_AMOUNT_MISMATCH = "PAY_AMOUNT_MISMATCH"
    # 환불
    RFND_NOT_ALLOWED = "RFND_NOT_ALLOWED"
    RFND_LIMIT_EXCEEDED = "RFND_LIMIT_EXCEEDED"


# HTTP 규약은 TDD 10.1을 따른다. 400 검증, 401 미인증, 403 권한, 404 없음, 409 충돌, 422 업무 규칙, 429 제한.
ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_FAILED: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.CONFLICT_STATE: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.RULE_REJECTED: 422,
    ErrorCode.TOO_MANY_REQUESTS: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.LOGIN_FAILED: 401,
    ErrorCode.LOGIN_LOCKED: 429,
    ErrorCode.OTP_INVALID: 422,
    ErrorCode.OTP_EXPIRED: 422,
    ErrorCode.OTP_RESEND_TOO_SOON: 429,
    ErrorCode.JOIN_LOGIN_ID_TAKEN: 422,
    ErrorCode.APLY_RCPT_CLOSED: 422,
    ErrorCode.APLY_PRIORITY_PERIOD: 422,
    ErrorCode.APLY_ALREADY_APPLIED: 422,
    ErrorCode.APLY_FULL: 422,
    ErrorCode.APLY_MEMBER_INACTIVE: 422,
    ErrorCode.APLY_CANCEL_NOT_ALLOWED: 422,
    ErrorCode.PAY_NOT_PAYABLE: 422,
    ErrorCode.PAY_DEADLINE_EXPIRED: 422,
    ErrorCode.PAY_RESULT_PENDING: 422,
    ErrorCode.PAY_AMOUNT_MISMATCH: 422,
    ErrorCode.RFND_NOT_ALLOWED: 422,
    ErrorCode.RFND_LIMIT_EXCEEDED: 422,
}

DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_FAILED: "입력값을 확인해 주세요.",
    ErrorCode.UNAUTHENTICATED: "로그인이 필요합니다.",
    ErrorCode.FORBIDDEN: "이용 권한이 없습니다.",
    ErrorCode.NOT_FOUND: "요청한 정보를 찾을 수 없습니다.",
    ErrorCode.METHOD_NOT_ALLOWED: "허용되지 않는 요청 방식입니다.",
    ErrorCode.CONFLICT_STATE: "현재 상태에서는 처리할 수 없습니다.",
    ErrorCode.IDEMPOTENCY_CONFLICT: "같은 요청 키로 다른 내용이 전달되었습니다.",
    ErrorCode.VERSION_CONFLICT: "다른 곳에서 먼저 수정되었습니다. 새로 고친 뒤 다시 시도해 주세요.",
    ErrorCode.RULE_REJECTED: "처리할 수 없는 요청입니다.",
    ErrorCode.TOO_MANY_REQUESTS: "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    ErrorCode.INTERNAL_ERROR: "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    ErrorCode.NOT_IMPLEMENTED: "아직 구현되지 않은 기능입니다.",
    ErrorCode.LOGIN_FAILED: "아이디 또는 비밀번호를 확인해 주세요.",
    ErrorCode.LOGIN_LOCKED: "로그인 시도가 많아 잠시 이용할 수 없습니다.",
    ErrorCode.OTP_INVALID: "인증번호가 올바르지 않습니다.",
    ErrorCode.OTP_EXPIRED: "인증번호 유효시간이 지났습니다. 다시 요청해 주세요.",
    ErrorCode.OTP_RESEND_TOO_SOON: "인증번호는 잠시 후 다시 요청할 수 있습니다.",
    ErrorCode.JOIN_LOGIN_ID_TAKEN: "이미 사용 중인 아이디입니다.",
    ErrorCode.APLY_RCPT_CLOSED: "접수기간이 아닙니다.",
    ErrorCode.APLY_PRIORITY_PERIOD: "파주시 주민 우선접수 기간입니다.",
    ErrorCode.APLY_ALREADY_APPLIED: "이미 신청한 강좌입니다.",
    ErrorCode.APLY_FULL: "정원과 대기정원이 모두 찼습니다.",
    ErrorCode.APLY_MEMBER_INACTIVE: "현재 회원 상태로는 신청할 수 없습니다.",
    ErrorCode.APLY_CANCEL_NOT_ALLOWED: "현재 상태에서는 신청을 취소할 수 없습니다.",
    ErrorCode.PAY_NOT_PAYABLE: "결제할 수 없는 신청입니다.",
    ErrorCode.PAY_DEADLINE_EXPIRED: "결제기한이 지났습니다.",
    ErrorCode.PAY_RESULT_PENDING: "결제 결과를 확인 중입니다. 확인이 끝날 때까지 기다려 주세요.",
    ErrorCode.PAY_AMOUNT_MISMATCH: "결제 금액이 일치하지 않습니다.",
    ErrorCode.RFND_NOT_ALLOWED: "환불을 신청할 수 없는 상태입니다.",
    ErrorCode.RFND_LIMIT_EXCEEDED: "환불 가능 금액을 초과합니다.",
}


class ErrorResponse(ApiModel):
    """오류 응답 형식(TDD 10.1). 개인정보·SQL·스택트레이스는 넣지 않는다."""

    code: ErrorCode
    message: str
    fields: dict[str, str] | None = None
    request_id: str


class ApiError(Exception):
    def __init__(
        self, code: ErrorCode, message: str | None = None, fields: dict[str, str] | None = None
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.fields = fields


def not_implemented() -> NoReturn:
    """골격 단계의 엔드포인트가 호출한다. 본 구현이 들어오면 사라진다."""
    raise ApiError(ErrorCode.NOT_IMPLEMENTED)


class RequestIdMiddleware:
    """모든 요청에 요청 ID를 붙이고 응답 헤더로 돌려준다. 형식이 맞지 않는 값은 버리고 새로 만든다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = MutableHeaders(scope=scope).get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and _REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_id)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else uuid.uuid4().hex


def _error_response(
    request: Request, code: ErrorCode, message: str | None = None, fields: dict[str, str] | None = None
) -> JSONResponse:
    request_id = _request_id(request)
    body = ErrorResponse(
        code=code,
        message=message or DEFAULT_MESSAGES[code],
        fields=fields,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=ERROR_STATUS[code],
        content=body.model_dump(mode="json", by_alias=True),
        headers={REQUEST_ID_HEADER: request_id},
    )


_HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT_STATE,
    429: ErrorCode.TOO_MANY_REQUESTS,
}


def install_error_handlers(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(request, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 입력값은 되돌려 보내지 않는다. 어느 필드가 문제인지만 알려 준다.
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = [str(part) for part in error["loc"] if part not in ("body", "query", "path", "header")]
            fields[".".join(location) or "request"] = "입력 형식이 올바르지 않습니다."
        return _error_response(request, ErrorCode.VALIDATION_FAILED, fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.RULE_REJECTED)
        return _error_response(request, code)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 예외 메시지에는 SQL이나 개인정보가 들어 있을 수 있어 종류와 요청 ID만 남긴다(C10)
        logger.error("처리하지 못한 오류 type=%s request_id=%s", type(exc).__name__, _request_id(request))
        return _error_response(request, ErrorCode.INTERNAL_ERROR)
