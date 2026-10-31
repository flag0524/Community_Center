# OpenAPI 문서를 우리 오류 규약(400 + ErrorResponse)에 맞게 다듬는다
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """FastAPI가 붙이는 422 HTTPValidationError를 걷어낸다. 검증 오류는 400 ErrorResponse다(TDD 10.1)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description="조리읍 주민자치센터 수강시스템 API. 일련번호는 모두 숫자 문자열이다.",
        routes=app.routes,
    )
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            response_422 = operation.get("responses", {}).get("422")
            reference = response_422 and response_422.get("content", {}).get("application/json", {}).get(
                "schema", {}
            ).get("$ref", "")
            if reference and reference.endswith("/HTTPValidationError"):
                del operation["responses"]["422"]
    components = schema.get("components", {}).get("schemas", {})
    for name in _FASTAPI_VALIDATION_SCHEMAS:
        components.pop(name, None)
    app.openapi_schema = schema
    return schema


def install_openapi(app: FastAPI) -> None:
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
