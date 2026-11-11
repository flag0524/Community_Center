# 로그인 전용 경로를 뺀 모든 관리자 엔드포인트가 로그인하지 않으면 401인지, 회원 세션으로는 열리지 않는지 확인하는 시험
import re
from typing import Any

import pytest

from tests.test_applications_read import RESIDENT, sign_in
from tests.world import World

pytestmark = pytest.mark.db

METHODS = {"get", "post", "put", "patch", "delete"}


def admin_operations(world: World) -> list[tuple[str, str]]:
    """OpenAPI에 실린 관리자 경로 전부(로그인 전용 /auth/ 제외). 경로 변수는 임의 값으로 채운다."""
    app: Any = world.client.app
    found = []
    for path, item in app.openapi()["paths"].items():
        if path.startswith("/api/admin/v1") and "/auth/" not in path:
            for method in sorted(METHODS & set(item)):
                found.append((method.upper(), re.sub(r"\{[^}]+\}", "1", path)))
    return found


def test_로그인하지_않으면_모든_관리자_엔드포인트가_401이다(world: World) -> None:
    operations = admin_operations(world)
    assert len(operations) > 100  # 경로를 못 찾아 빈 시험이 되는 것을 막는다
    failures = []
    for method, path in operations:
        response = world.client.request(method, path)
        if response.status_code != 401:
            failures.append((method, path, response.status_code))
    assert failures == []


def test_회원_세션으로는_관리자_엔드포인트가_열리지_않는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    for method, path in admin_operations(world)[:40]:
        assert world.client.request(method, path).status_code == 401, (method, path)
