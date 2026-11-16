# 세션이 필요한 모든 쓰기 경로가 CSRF 토큰 없이는 403인지 경로 목록에서 자동으로 만들어 확인하는 시험(DV17)
import importlib
import pkgutil
import re
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from sqlalchemy import text

import app.routers.admin as admin_pkg
import app.routers.user as user_pkg
from tests.test_admin_refunds import staff, use
from tests.test_member_inquiries import as_member, person
from tests.world import ADMIN, MEMBER, World

pytestmark = pytest.mark.db

WRITE = {"POST", "PUT", "PATCH", "DELETE"}
ROUTER_NAMES = ("router", "member_router")
# 로그인 전 인증 경로는 세션이 없어 시드 쿠키로 스스로 검증한다. 세션 경로(logout·extend)도 스스로 검증한다
SELF_VERIFIED_ADMIN = {"/auth/login", "/auth/logout", "/auth/extend"}
SELF_VERIFIED_USER = {
    "/auth/find-id",
    "/auth/login",
    "/auth/logout",
    "/auth/otp",
    "/auth/otp/verify",
    "/auth/password-reset",
    "/join",
}


def write_routes(pkg: Any, skip: set[str]) -> list[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for info in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(f"{pkg.__name__}.{info.name}")
        for name in ROUTER_NAMES:
            router = getattr(module, name, None)
            if not isinstance(router, APIRouter):
                continue
            for route in router.routes:
                if isinstance(route, APIRoute) and route.path not in skip:
                    found.update((method, route.path) for method in (route.methods or set()) & WRITE)
    return sorted(found)


ADMIN_ROUTES = write_routes(admin_pkg, SELF_VERIFIED_ADMIN)
USER_ROUTES = write_routes(user_pkg, SELF_VERIFIED_USER)


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def test_점검_대상이_비어_있지_않다() -> None:
    assert (
        len(ADMIN_ROUTES) >= 55 and len(USER_ROUTES) >= 15
    )  # 경로 수집이 조용히 비면 아래 시험이 아무것도 안 본다


def send(w: World, base: str, method: str, path: str, **headers: str) -> Any:
    return w.client.request(method, f"{base}{concrete(path)}", headers=headers)


def test_관리자_쓰기_경로는_토큰이_없거나_틀리면_모두_403이다(world: World) -> None:
    use(world, staff(world, "csrf-admin", "AU.CORS_W"))
    leaked = [
        (method, path)
        for method, path in ADMIN_ROUTES
        if send(world, ADMIN, method, path).status_code != 403
        or send(world, ADMIN, method, path, **{"X-CSRF-Token": "wrong-token"}).status_code != 403
    ]
    assert leaked == []


def test_회원_쓰기_경로는_토큰이_없거나_틀리면_모두_403이다(world: World) -> None:
    as_member(world, person(world))
    leaked = [
        (method, path)
        for method, path in USER_ROUTES
        if send(world, MEMBER, method, path).status_code != 403
        or send(world, MEMBER, method, path, **{"X-CSRF-Token": "wrong-token"}).status_code != 403
    ]
    assert leaked == []


def test_맞는_토큰이면_CSRF로_거절하지_않는다(world: World) -> None:
    who = staff(world, "csrf-ok", "AU.CORS_W")
    use(world, who)
    res = world.client.post(f"{ADMIN}/facilities", headers={"X-CSRF-Token": who.csrf})
    assert res.status_code == 400  # 토큰을 통과해 본문 검증까지 갔다(토큰이 틀리면 위 시험대로 403이다)


def test_토큰이_틀린_요청은_유휴_시간을_늘리지_않는다(world: World) -> None:
    use(world, staff(world, "csrf-idle", "AU.CORS_W"))
    before = world.db.execute(text("SELECT LAST_ACT_DT FROM TB_LGN_SSN WHERE MNGR_SN IS NOT NULL")).scalar()
    world.clock.advance(minutes=5)
    assert send(world, ADMIN, "POST", "/facilities").status_code == 403
    world.db.commit()
    after = world.db.execute(text("SELECT LAST_ACT_DT FROM TB_LGN_SSN WHERE MNGR_SN IS NOT NULL")).scalar()
    assert before == after


def test_조회_요청은_토큰이_없어도_된다(world: World) -> None:
    use(world, staff(world, "csrf-read", "AU.CORS_R"))
    assert world.client.get(f"{ADMIN}/me/permissions").status_code == 200
