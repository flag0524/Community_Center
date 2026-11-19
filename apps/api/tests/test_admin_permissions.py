# 관리자 권한·메뉴 응답(유효한 배정에서만, 역할 이름과 묶음 이름, 구조 권한만 가진 시스템 배정, 빈 묶음 숨김)을 실제 앱과 MariaDB로 확인하는 시험
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import assign, dong, role
from tests.test_admin_refunds import call, staff, use
from tests.world import START, World

pytestmark = pytest.mark.db


def me(w: World) -> dict[str, Any]:
    res = call(w, "GET", "/me/permissions")
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


def keys(out: dict[str, Any]) -> list[str]:
    return [i["key"] for g in out["menu"] for i in g["items"]]


def test_로그인이_없으면_401이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/me/permissions").status_code == 401


def test_유효한_배정의_권한과_역할_묶음_이름과_메뉴를_준다(world: World) -> None:
    use(world, staff(world, "p1", "AU.CORS_R", "AU.STAT_R"))
    out = me(world)
    label = world.db.execute(
        text("SELECT OPER_BNDL_NM FROM TB_OPER_BNDL WHERE OPER_BNDL_SN = :b"), {"b": world.bundle}
    ).scalar()
    assert out["roleNames"] == ["r-p1"] and out["scopeLabel"] == label
    assert out["authorities"] == ["AU.CORS_R", "AU.STAT_R"]
    assert [(g["key"], [i["key"] for i in g["items"]]) for g in out["menu"]] == [
        ("status", ["dashboard", "stats"]),
        ("edu", ["courses"]),
        ("system", ["classes"]),
    ]  # 보이는 항목이 없는 묶음은 뺀다
    assert out["menu"][0]["items"][0] == {"key": "dashboard", "label": "대시보드", "path": "/dashboard"}


def test_권한이_없는_역할이면_빈_메뉴를_준다(world: World) -> None:
    use(world, staff(world, "p2"))
    out = me(world)
    assert out["roleNames"] == ["r-p2"] and out["authorities"] == [] and out["menu"] == []


def test_만료된_예정된_사용_중지된_배정과_역할은_빼고_다른_행의_권한을_섞지_않는다(world: World) -> None:
    who = staff(world, "p3", "AU.CORS_R")
    ended = role(world, "ended", "AU.MBR_R")
    assign(world, who.row, ended, "SK.GROUP", VLD_END_DT=START - timedelta(hours=1))
    future = role(world, "future", "AU.POST_W")
    assign(world, who.row, future, "SK.GROUP", VLD_BGNG_DT=START + timedelta(days=1))
    off = role(world, "off", "AU.SITE_W")
    assign(world, who.row, off, "SK.GROUP", USE_YN="N")
    dead = role(world, "dead", "AU.BBS_W", USE_YN="N")
    assign(world, who.row, dead, "SK.GROUP")
    use(world, who)
    out = me(world)
    assert out["authorities"] == ["AU.CORS_R"] and out["roleNames"] == ["r-p3"]


def test_배정이_여러_개면_권한을_합치고_같은_역할_이름은_한_번만_보인다(world: World) -> None:
    who = staff(world, "p4", "AU.CORS_R")
    a, b = dong(world, "가동"), dong(world, "나동")
    shared = role(world, "shared", "AU.APLY_R")
    assign(world, who.row, shared, "SK.DONG", dong_sn=a["DONG_SN"])
    assign(world, who.row, shared, "SK.DONG", dong_sn=b["DONG_SN"])
    use(world, who)
    out = me(world)
    assert out["authorities"] == ["AU.CORS_R", "AU.APLY_R"]
    assert out["roleNames"] == ["r-p4", "shared"]


def test_다른_묶음의_배정은_보이지_않는다(world: World) -> None:
    who = staff(world, "p5", "AU.CORS_R")
    other = world.factory.make("TB_OPER_BNDL")
    assign(world, who.row, role(world, "foreign", "AU.MBR_R"), "SK.GROUP", OPER_BNDL_SN=other["OPER_BNDL_SN"])
    use(world, who)
    assert me(world)["authorities"] == ["AU.CORS_R"]


def test_시스템_배정은_구조_권한만_갖고_기능을_켜지_않는_코드는_내보내지_않는다(world: World) -> None:
    use(world, staff(world, "p6", "AU.GRANT_W", "AU.MBR_R", "AU.MBR_W", kind="SK.SYSTEM"))
    out = me(world)
    assert out["authorities"] == ["AU.GRANT_W"]  # 회원 조회는 업무 권한이라 빠지고 AU.MBR_W는 열려 있지 않다
    assert keys(out) == ["roles", "codes"]


def test_집계자료와_이름_변경_메뉴는_묶음_배정만_보고_시스템·동_배정에는_보이지_않는다(world: World) -> None:
    use(world, staff(world, "p7", "AU.CONF_W", "AU.GRANT_W"))
    assert {"stats-sources", "satisfaction-sources", "name-changes"} <= set(keys(me(world)))
    use(world, staff(world, "p8", "AU.GRANT_W", kind="SK.SYSTEM"))
    assert not {"stats-sources", "satisfaction-sources", "name-changes"} & set(keys(me(world)))
    use(
        world,
        staff(world, "p9", "AU.CONF_W", "AU.GRANT_W", kind="SK.DONG", dong_sn=dong(world, "가동")["DONG_SN"]),
    )
    assert not {"stats-sources", "satisfaction-sources", "name-changes"} & set(keys(me(world)))
