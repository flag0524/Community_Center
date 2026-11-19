# 배정이 하나도 없는 관리자는 로그인은 되지만 업무 엔드포인트가 열리지 않는지(성공 응답 없음, 입력이 맞으면 403) 확인하는 시험
import re
from typing import Any

import pytest

from tests.test_admin_default_auth import METHODS, admin_operations
from tests.world import ADMIN, World, login, make_admin

pytestmark = pytest.mark.db

OPEN_TO_ANY_ADMIN = {
    ("GET", "/api/admin/v1/me/permissions")
}  # 자기 메뉴와 권한을 보는 응답이라 배정이 없으면 빈 목록이다


def sample(spec: dict[str, Any], schema: dict[str, Any]) -> Any:
    """OpenAPI 스키마를 통과하는 가장 단순한 값. 필수 입력이 모자라 검증에서 먼저 400이 나는 것을 피하려는 용도다."""
    if "$ref" in schema:
        node: Any = spec
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return sample(spec, node)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return sample(spec, options[0] if options else schema[key][0])
    if "allOf" in schema:
        return sample(spec, schema["allOf"][0])
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        required = schema.get("required", [])
        return {
            name: sample(spec, prop)
            for name, prop in schema.get("properties", {}).items()
            if name in required
        }
    if kind == "array":
        return [sample(spec, schema["items"])] * schema.get("minItems", 0) if "items" in schema else []
    if kind == "integer":
        return max(1, schema.get("minimum", 1))
    if kind == "number":
        return 1
    if kind == "boolean":
        return True
    if schema.get("format") == "date":
        return "2026-11-20"
    if schema.get("format") == "date-time":
        return "2026-11-20T00:00:00Z"
    pattern = schema.get("pattern")
    if pattern and re.search(pattern, "1"):
        return "1"
    return "가" * max(1, schema.get("minLength", 1))


def request_for(spec: dict[str, Any], method: str, template: str) -> dict[str, Any]:
    operation = spec["paths"][template][method.lower()]
    query = {}
    for parameter in operation.get("parameters", []):
        if parameter["in"] == "query" and parameter.get("required"):
            query[parameter["name"]] = sample(spec, parameter["schema"])
    content = operation.get("requestBody", {}).get("content", {})
    kwargs: dict[str, Any] = {"params": query}
    if "application/json" in content:
        kwargs["json"] = sample(spec, content["application/json"]["schema"])
    return kwargs


def test_배정이_없는_관리자는_업무_엔드포인트를_열_수_없다(world: World) -> None:
    make_admin(world, "nobody")
    response = login(world, ADMIN, "nobody")
    assert response.status_code == 200
    headers = {"X-CSRF-Token": response.json()["csrfToken"], "Idempotency-Key": "no-authority-0001"}
    spec: Any = world.client.app.openapi()  # type: ignore[attr-defined]
    templates = {
        (method.upper(), re.sub(r"\{[^}]+\}", "1", path)): path
        for path, item in spec["paths"].items()
        if path.startswith("/api/admin/v1") and "/auth/" not in path
        for method in METHODS & set(item)
    }
    operations = admin_operations(world)
    assert len(operations) > 100 and set(operations) == set(templates)
    opened, unchecked, forbidden = [], [], 0
    for method, path in operations:
        if (method, path) in OPEN_TO_ANY_ADMIN:
            continue
        result = world.client.request(
            method, path, headers=headers, **request_for(spec, method, templates[(method, path)])
        )
        if result.status_code < 300:
            opened.append((method, path, result.status_code))
        elif result.status_code == 403:
            forbidden += 1
        else:
            unchecked.append((method, path, result.status_code))
    print(f"권한 판정으로 막힌 것 {forbidden}건, 그 밖의 거절 {len(unchecked)}건")
    for item in unchecked:
        print(*item)
    assert opened == []
    assert forbidden >= 120  # 가짜 입력 생성이 어긋나 검증 거절만 늘면 이 시험이 아무것도 보지 못한다
