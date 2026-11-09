# 회원 전용(/me) 엔드포인트의 로그인 확인과 유휴 시간 연장 규칙을 실제 앱과 MariaDB로 확인하는 시험
import pytest
from sqlalchemy import text

from app.auth.sessions import issue_session
from app.routers.deps import SESSION_COOKIE_NAME
from tests.world import MEMBER, World, login, make_admin, make_member

pytestmark = pytest.mark.db

PATH = f"{MEMBER}/me/applications"


def sign_in(w: World, login_id: str = "me") -> None:
    make_member(w, login_id)
    assert login(w, MEMBER, login_id).status_code == 200


def test_로그인_없이는_401이다(world: World) -> None:
    for path in (PATH, f"{MEMBER}/me/applications/1", f"{MEMBER}/courses/1/apply-preview"):
        response = world.client.get(path)
        assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"


def test_로그인하면_열린다(world: World) -> None:
    sign_in(world)
    assert world.client.get(PATH).status_code == 200


def test_로그아웃하면_다시_401이다(world: World) -> None:
    sign_in(world)
    token = world.client.get(f"{MEMBER}/auth/session").json()["csrfToken"]
    assert world.client.post(f"{MEMBER}/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204
    assert world.client.get(PATH).status_code == 401


def test_계정이_잠기거나_탈퇴하면_세션이_살아_있어도_401이다(world: World) -> None:
    sign_in(world)
    for state in ("MS.LOCKED", "MS.WITHDRAW"):
        world.db.execute(text("UPDATE TB_MBR SET MBR_STTS_CD = :s"), {"s": state})
        assert world.client.get(PATH).status_code == 401


def test_관리자_세션_쿠키로는_회원_엔드포인트를_열_수_없다(world: World) -> None:
    make_admin(world, "boss")
    assert login(world, "/api/admin/v1", "boss").status_code == 200
    assert world.client.get(PATH).status_code == 401


def test_다른_운영묶음의_세션은_받지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    outsider = make_member(world, "outsider", OPER_BNDL_SN=other)
    token, _ = issue_session(
        world.db, bundle_sn=other, member_sn=outsider["MBR_SN"], admin_sn=None, now=world.clock.now
    )
    world.client.cookies.set(SESSION_COOKIE_NAME, token)
    assert world.client.get(PATH).status_code == 401


def test_유휴_30분이_지나면_401이다(world: World) -> None:
    sign_in(world)
    world.clock.advance(minutes=29, seconds=59)
    assert world.client.get(PATH).status_code == 200
    world.clock.advance(minutes=30, seconds=1)
    assert world.client.get(PATH).status_code == 401


def test_요청마다_유휴_시간을_처음부터_다시_센다(world: World) -> None:
    sign_in(world)
    for _ in range(3):
        world.clock.advance(minutes=20)
        assert world.client.get(PATH).status_code == 200  # 합치면 60분이지만 20분마다 활동했다


def test_백그라운드_요청은_유휴_시간을_늘리지_않는다(world: World) -> None:
    sign_in(world)
    world.clock.advance(minutes=20)
    assert world.client.get(PATH, headers={"X-Background": "1"}).status_code == 200
    world.clock.advance(minutes=11)  # 로그인에서 31분
    assert world.client.get(PATH).status_code == 401


def test_백그라운드_표시가_1이_아니면_활동으로_본다(world: World) -> None:
    sign_in(world)
    world.clock.advance(minutes=20)
    assert world.client.get(PATH, headers={"X-Background": "0"}).status_code == 200
    world.clock.advance(minutes=20)
    assert world.client.get(PATH).status_code == 200


def test_세션_조회는_연장하지_않는다(world: World) -> None:
    # 세션 조회(GET /auth/session)는 새로 고침용이라 유휴 시간을 늘리지 않는다(ADR-031)
    sign_in(world)
    world.clock.advance(minutes=20)
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is True
    world.clock.advance(minutes=11)
    assert world.client.get(PATH).status_code == 401
