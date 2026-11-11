# 관리자 기능권한·범위·유효기간 판정(같은 배정 행에서 함께 검사, 곱집합 금지)을 실제 MariaDB로 확인하는 시험
from datetime import timedelta
from typing import Any

import pytest

from app.auth.admin_access import Admin, Scope, permit, permit_any, scope_for
from app.auth.sessions import SessionRecord
from app.core.errors import ApiError
from app.domain.admin.types import AdminAuthority as AU
from tests.world import START, World, make_admin

pytestmark = pytest.mark.db


def who(w: World, admin: dict[str, Any]) -> Admin:
    record = SessionRecord(1, None, None, int(admin["MNGR_SN"]), "h", START, START)
    return Admin(int(admin["MNGR_SN"]), w.bundle, record)


def role(w: World, name: str, *codes: str, **values: Any) -> dict[str, Any]:
    made = w.factory.make("TB_MNGR_ROLE", ROLE_ID=name, ROLE_NM=name, **values)
    for code in codes:
        w.factory.make("TB_ROLE_AUTHRT", ROLE_SN=made["ROLE_SN"], AUTHRT_CD=code)
    return made


def dong(w: World, name: str) -> dict[str, Any]:
    return w.factory.make("TB_DONG", DONG_NM=name)


def assign(
    w: World, admin: dict[str, Any], r: dict[str, Any], kind: str, *, dong_sn: Any = None, **values: Any
) -> dict[str, Any]:
    scope: dict[str, Any] = {"SCP_TYPE_CD": kind}
    if kind != "SK.SYSTEM":
        scope["OPER_BNDL_SN"] = w.bundle
    if kind == "SK.DONG":
        scope["DONG_SN"] = dong_sn
    defaults = {"VLD_BGNG_DT": START - timedelta(days=1), "GRNT_MNGR_SN": admin["MNGR_SN"]}
    return w.factory.make(
        "TB_MNGR_SCP", MNGR_SN=admin["MNGR_SN"], ROLE_SN=r["ROLE_SN"], **{**defaults, **scope, **values}
    )


def test_묶음_배정은_묶음_전체를_본다(world: World) -> None:
    admin = make_admin(world)
    assign(world, admin, role(world, "g", "AU.RFND_A"), "SK.GROUP")
    scope = scope_for(world.db, who(world, admin), AU.RFND_A, START)
    assert scope.whole and scope.covers(None) and scope.covers(999)


def test_동_배정은_그_동만_보고_동이_없는_대상은_못_본다(world: World) -> None:
    admin, a, b = make_admin(world), dong(world, "가동"), dong(world, "나동")
    assign(world, admin, role(world, "d", "AU.RFND_A"), "SK.DONG", dong_sn=a["DONG_SN"])
    scope = scope_for(world.db, who(world, admin), AU.RFND_A, START)
    assert not scope.whole
    assert scope.covers(int(a["DONG_SN"])) and not scope.covers(int(b["DONG_SN"])) and not scope.covers(None)


def test_역할에_없는_권한은_범위가_비어_거절한다(world: World) -> None:
    admin = make_admin(world)
    assign(world, admin, role(world, "g", "AU.RFND_A"), "SK.GROUP")
    assert scope_for(world.db, who(world, admin), AU.RFND_X, START).empty()
    with pytest.raises(ApiError) as caught:
        permit(world.db, who(world, admin), AU.RFND_X, START)
    assert caught.value.code.value == "FORBIDDEN"


def test_서로_다른_배정_행의_역할과_동을_곱집합으로_섞지_않는다(world: World) -> None:
    admin, a, b = make_admin(world), dong(world, "가동"), dong(world, "나동")
    # 가동에서는 환불승인만, 나동에서는 환불집행만 받았다. 가동의 집행·나동의 승인은 없다.
    assign(world, admin, role(world, "ra", "AU.RFND_A"), "SK.DONG", dong_sn=a["DONG_SN"])
    assign(world, admin, role(world, "rx", "AU.RFND_X"), "SK.DONG", dong_sn=b["DONG_SN"])
    approve = scope_for(world.db, who(world, admin), AU.RFND_A, START)
    execute = scope_for(world.db, who(world, admin), AU.RFND_X, START)
    assert approve.dongs == {int(a["DONG_SN"])} and execute.dongs == {int(b["DONG_SN"])}


def test_같은_권한의_여러_배정은_범위를_합친다(world: World) -> None:
    admin, a, b = make_admin(world), dong(world, "가동"), dong(world, "나동")
    r = role(world, "d", "AU.RFND_A")
    assign(world, admin, r, "SK.DONG", dong_sn=a["DONG_SN"])
    assign(world, admin, r, "SK.DONG", dong_sn=b["DONG_SN"])
    assert scope_for(world.db, who(world, admin), AU.RFND_A, START).dongs == {
        int(a["DONG_SN"]),
        int(b["DONG_SN"]),
    }


@pytest.mark.parametrize(
    ("begin", "end", "allowed"),
    [
        (timedelta(seconds=-1), None, True),
        (timedelta(0), None, True),  # 시작 시각 정각부터 유효
        (timedelta(seconds=1), None, False),  # 아직 시작 전
        (timedelta(days=-2), timedelta(seconds=1), True),
        (timedelta(days=-2), timedelta(0), False),  # 종료 시각 정각에는 이미 끝남
        (timedelta(days=-2), timedelta(seconds=-1), False),
    ],
    ids=["시작후", "시작정각", "시작전", "종료전", "종료정각", "종료후"],
)
def test_유효기간_경계(world: World, begin: timedelta, end: timedelta | None, allowed: bool) -> None:
    admin = make_admin(world)
    values: dict[str, Any] = {"VLD_BGNG_DT": START + begin}
    if end is not None:
        values["VLD_END_DT"] = START + end
    assign(world, admin, role(world, "g", "AU.RFND_A"), "SK.GROUP", **values)
    assert (not scope_for(world.db, who(world, admin), AU.RFND_A, START).empty()) is allowed


def test_사용중지된_배정과_역할은_효력이_없다(world: World) -> None:
    off_row, off_role = make_admin(world, "a1"), make_admin(world, "a2")
    assign(world, off_row, role(world, "g1", "AU.RFND_A"), "SK.GROUP", USE_YN="N")
    assign(world, off_role, role(world, "g2", "AU.RFND_A", USE_YN="N"), "SK.GROUP")
    assert scope_for(world.db, who(world, off_row), AU.RFND_A, START).empty()
    assert scope_for(world.db, who(world, off_role), AU.RFND_A, START).empty()


def test_시스템_배정은_운영구조_권한만_갖고_업무_권한은_없다(world: World) -> None:
    admin = make_admin(world)
    assign(world, admin, role(world, "s", "AU.GRANT_W", "AU.RFND_A"), "SK.SYSTEM")
    assert scope_for(world.db, who(world, admin), AU.GRANT_W, START).whole
    assert scope_for(world.db, who(world, admin), AU.RFND_A, START).empty()


def test_다른_운영묶음의_배정은_효력이_없다(world: World) -> None:
    admin = make_admin(world)
    assign(world, admin, role(world, "g", "AU.RFND_A"), "SK.GROUP")
    other = world.factory.make("TB_OPER_BNDL")
    foreign = Admin(int(admin["MNGR_SN"]), int(other["OPER_BNDL_SN"]), who(world, admin).record)
    assert scope_for(world.db, foreign, AU.RFND_A, START).empty()


def test_다른_관리자의_배정은_보지_않는다(world: World) -> None:
    mine, theirs = make_admin(world, "a1"), make_admin(world, "a2")
    assign(world, theirs, role(world, "g", "AU.RFND_A"), "SK.GROUP")
    assert scope_for(world.db, who(world, mine), AU.RFND_A, START).empty()


def test_여러_권한_중_하나만_있어도_통과하고_범위를_합친다(world: World) -> None:
    admin, a = make_admin(world), dong(world, "가동")
    assign(world, admin, role(world, "x", "AU.RFND_X"), "SK.DONG", dong_sn=a["DONG_SN"])
    scope = permit_any(world.db, who(world, admin), (AU.RFND_A, AU.RFND_X), START)
    assert scope.dongs == {int(a["DONG_SN"])}
    with pytest.raises(ApiError):
        permit_any(world.db, who(world, admin), (AU.RFND_A, AU.STLM_R), START)


def test_범위의_빈_값과_포함_판정() -> None:
    assert Scope().empty() and not Scope().covers(1)
    assert Scope(whole=True).covers(None)
