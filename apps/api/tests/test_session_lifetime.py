# 세션 절대 만료(회원 12시간·관리자 8시간)와 30초 안 연속 요청의 갱신 생략을 실제 앱과 MariaDB로 확인하는 시험
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_admin_refunds import staff, use
from tests.world import ADMIN, MEMBER, World, login, make_member

pytestmark = pytest.mark.db

MEMBER_PATH = f"{MEMBER}/me/applications"
ADMIN_PATH = (
    f"{ADMIN}/facilities"  # 시설 관리 권한이 있으면 200이다(오류 응답은 갱신을 되돌리므로 성공해야 한다)
)


def member_alive(w: World) -> bool:
    return w.client.get(MEMBER_PATH).status_code == 200


def admin_alive(w: World) -> bool:
    return w.client.get(ADMIN_PATH).status_code == 200


def sign_in_member(w: World) -> None:
    make_member(w, "me")
    assert login(w, MEMBER, "me").status_code == 200


def sign_in_admin(w: World) -> dict[str, str]:
    who = staff(w, "boss", "AU.FCLT_W")
    use(w, who)
    return {"X-CSRF-Token": who.csrf}


def last_activity(w: World, column: str) -> object:
    return w.db.execute(text(f"SELECT LAST_ACT_DT FROM TB_LGN_SSN WHERE {column} IS NOT NULL")).scalar()


# --- 절대 만료 -------------------------------------------------------------------------------


def test_회원_세션은_계속_써도_발급_12시간에_끝난다(world: World) -> None:
    sign_in_member(world)
    for _ in range(35):  # 20분마다 활동해 유휴 만료는 피한다(11시간 40분)
        world.clock.advance(minutes=20)
        assert member_alive(world)
    world.clock.advance(minutes=19, seconds=59)  # 11시간 59분 59초
    assert member_alive(world)
    world.clock.advance(seconds=1)  # 정확히 12시간
    assert member_alive(world) is False


def test_관리자_세션은_계속_써도_발급_8시간에_끝난다(world: World) -> None:
    sign_in_admin(world)
    for _ in range(34):  # 14분마다 활동한다(7시간 56분)
        world.clock.advance(minutes=14)
        assert admin_alive(world)
    world.clock.advance(minutes=3, seconds=59)  # 7시간 59분 59초
    assert admin_alive(world)
    world.clock.advance(seconds=1)
    assert admin_alive(world) is False


def test_연장해도_절대_상한을_넘지_못한다(world: World) -> None:
    headers = sign_in_admin(world)
    issued = world.clock.now
    for _ in range(34):
        world.clock.advance(minutes=14)
        assert world.client.post(f"{ADMIN}/auth/extend", headers=headers).status_code == 200
    world.clock.advance(minutes=3, seconds=59)
    extended = world.client.post(f"{ADMIN}/auth/extend", headers=headers)
    assert extended.status_code == 200
    expires = datetime.fromisoformat(extended.json()["expiresAt"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert expires == issued + timedelta(hours=8)  # 유휴 15분을 더해도 발급 8시간에서 잘린다
    world.clock.advance(seconds=1)
    assert world.client.post(f"{ADMIN}/auth/extend", headers=headers).status_code == 401


def test_만료_시각_안내는_상한에_맞춰_줄어든다(world: World) -> None:
    sign_in_member(world)
    for _ in range(35):
        world.clock.advance(minutes=20)
        assert member_alive(world)
    # 11시간 40분 + 유휴 30분이면 12시간 10분이지만 발급 12시간에서 잘린다
    seconds_left = world.db.execute(
        text("SELECT TIMESTAMPDIFF(SECOND, ISSU_DT, EXPRY_DT) FROM TB_LGN_SSN WHERE MBR_SN IS NOT NULL")
    ).scalar()
    assert seconds_left == 12 * 3600


def test_발급이_상한보다_오래된_세션은_유휴_전이어도_거절한다(world: World) -> None:
    sign_in_member(world)
    world.db.execute(text("UPDATE TB_LGN_SSN SET ISSU_DT = DATE_SUB(ISSU_DT, INTERVAL 13 HOUR)"))
    world.db.execute(text("UPDATE TB_LGN_SSN SET EXPRY_DT = DATE_ADD(EXPRY_DT, INTERVAL 1 HOUR)"))
    assert member_alive(world) is False


@pytest.mark.parametrize("seconds,alive", [(0, False), (1, True)])
def test_발급이_정확히_12시간_전이면_거절하고_1초_덜_됐으면_받는다(
    world: World, seconds: int, alive: bool
) -> None:
    sign_in_member(world)
    issued = world.clock.now - timedelta(hours=12) + timedelta(seconds=seconds)
    world.db.execute(
        text("UPDATE TB_LGN_SSN SET ISSU_DT = :issued, EXPRY_DT = :expiry"),
        {"issued": issued, "expiry": world.clock.now + timedelta(hours=1)},  # 유휴로는 아직 살아 있다
    )
    assert member_alive(world) is alive


def test_절대_상한은_로그인할_때마다_새로_센다(world: World) -> None:
    make_member(world, "me")
    assert login(world, MEMBER, "me").status_code == 200
    world.clock.advance(minutes=20)
    assert member_alive(world)
    world.clock.advance(hours=11)  # 유휴로 끊긴 뒤 새로 로그인하면 다시 12시간이다
    assert member_alive(world) is False
    assert login(world, MEMBER, "me").status_code == 200
    for _ in range(3):
        world.clock.advance(minutes=20)
        assert member_alive(world)


# --- 30초 안의 연속 요청은 세션 행을 갱신하지 않는다 -----------------------------------------------


def test_30초_안의_연속_요청은_세션_행을_갱신하지_않는다(world: World) -> None:
    sign_in_member(world)
    first = last_activity(world, "MBR_SN")
    world.clock.advance(seconds=29)
    assert member_alive(world)
    assert last_activity(world, "MBR_SN") == first
    world.clock.advance(seconds=1)  # 마지막 갱신에서 정확히 30초
    assert member_alive(world)
    assert last_activity(world, "MBR_SN") != first


def test_30초_안의_관리자_요청도_갱신하지_않지만_연장_요청은_항상_갱신한다(world: World) -> None:
    headers = sign_in_admin(world)
    first = last_activity(world, "MNGR_SN")
    world.clock.advance(seconds=10)
    assert admin_alive(world)
    assert last_activity(world, "MNGR_SN") == first
    assert world.client.post(f"{ADMIN}/auth/extend", headers=headers).status_code == 200
    assert last_activity(world, "MNGR_SN") != first


def test_갱신을_건너뛰어도_유휴_만료는_마지막_갱신_기준_그대로다(world: World) -> None:
    sign_in_member(world)
    world.clock.advance(seconds=20)
    assert member_alive(world)  # 갱신 생략. 만료는 로그인 기준 30분
    world.clock.advance(minutes=29, seconds=39)  # 로그인 후 29분 59초
    assert member_alive(world)
    world.clock.advance(minutes=30)
    assert member_alive(world) is False
