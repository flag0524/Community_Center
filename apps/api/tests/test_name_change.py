# 회원 이름 변경 요청과 관리자 검토·반영(권한, 승인·반려, 멱등, 상태 제한)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin.refund_service import mask_name
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_member_inquiries import as_member, csrf, person
from tests.world import MEMBER, PASSWORD, World

pytestmark = pytest.mark.db

_n = itertools.count(1)
ADMIN = "/name-change-requests"
MINE = f"{MEMBER}/me/name-change-requests"


def member(w: World, name: str = "김회원", **values: Any) -> dict[str, Any]:
    who = person(w, name, MBL_TELNO="01012345678", **values)
    as_member(w, who)
    return who


def ask(
    w: World,
    new_name: str = "이새이름",
    reason: str = "개명했습니다",
    password: str = PASSWORD,
    key: str | None = None,
    **extra: Any,
) -> Any:
    headers = {**csrf(w), "Idempotency-Key": key or f"name-key-{next(_n):06d}"}
    body = {"newName": new_name, "reason": reason, "password": password, **extra}
    return w.client.post(MINE, json=body, headers=headers)


def boss(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"nc{next(_n)}", *(codes or ("AU.GRANT_W",)), **kw)
    use(w, who)
    return who


def profile_name(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/me/profile").json()["name"])


def jobs(w: World, code: str) -> list[Any]:
    return list(
        w.db.execute(
            text(
                "SELECT ACTR_TYPE_CD a, MBR_SN m, MNGR_SN g, TRGT_KEY_VL k, CHG_CN c "
                "FROM TB_JOB_HSTRY WHERE JOB_CD=:c ORDER BY JOB_HSTRY_SN"
            ),
            {"c": code},
        ).mappings()
    )


# --- 회원 요청 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이다(world: World) -> None:
    world.db.commit()
    assert world.client.get(MINE).status_code == 401
    assert world.client.post(MINE, json={}).status_code == 401


def test_요청하면_검토_중으로_남기고_이름은_바뀌지_않으며_이력에_평문이_없다(world: World) -> None:
    who = member(world)
    res = ask(world, "이새이름", "개명 판결문 확인 필요")
    assert res.status_code == 201, res.text
    out = res.json()
    assert (out["requestedName"], out["reason"], out["state"]) == (
        "이새이름",
        "개명 판결문 확인 필요",
        "PENDING",
    )
    assert out["decidedAt"] is None and out["decisionNote"] is None
    assert profile_name(world) == "김회원"  # 승인 전에는 바뀌지 않는다
    [job] = jobs(world, "NAME_CHANGE_REQUEST")
    assert (job["a"], int(job["m"]), job["k"]) == ("AK.MEMBER", int(who["MBR_SN"]), str(who["MBR_SN"]))
    assert "이새이름" not in job["c"] and "개명" not in job["c"] and PASSWORD not in job["c"]


def test_비밀번호가_틀리면_400이고_저장하지_않는다(world: World) -> None:
    member(world)
    res = ask(world, password="Wrong-Password-1")
    assert res.status_code == 400 and "password" in res.json()["fields"]
    assert jobs(world, "NAME_CHANGE_REQUEST") == []


@pytest.mark.parametrize(
    ("name", "status"),
    [("김회원", 422), ("탈퇴회원", 422), ("  ", 400), ("이\n름", 400), ("", 400), ("가" * 51, 400)],
)
def test_현재_이름과_같거나_쓸_수_없거나_형식이_틀리면_거절한다(world: World, name: str, status: int) -> None:
    member(world)
    assert ask(world, name).status_code == status
    assert jobs(world, "NAME_CHANGE_REQUEST") == []


def test_이름_앞뒤_공백은_자르고_저장한다(world: World) -> None:
    member(world)
    assert ask(world, "  이새이름  ").json()["requestedName"] == "이새이름"


def test_검토_중인_요청이_있으면_새_요청은_409이다(world: World) -> None:
    member(world)
    assert ask(world).status_code == 201
    again = ask(world, "다른이름")
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"
    assert len(jobs(world, "NAME_CHANGE_REQUEST")) == 1


def test_같은_키로_다시_보내면_같은_요청이고_내용이_다르면_409이며_키가_없으면_400이다(world: World) -> None:
    member(world)
    first = ask(world, key="same-key-0001")
    again = ask(world, key="same-key-0001")
    assert again.status_code == 201 and again.json()["requestId"] == first.json()["requestId"]
    assert len(jobs(world, "NAME_CHANGE_REQUEST")) == 1
    other = ask(world, "다른이름", key="same-key-0001")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    body = {"newName": "이새이름", "reason": "x", "password": PASSWORD}
    assert world.client.post(MINE, json=body, headers=csrf(world)).status_code == 400


def test_다른_회원이_같은_키를_써도_따로_요청한다(world: World) -> None:
    member(world)
    first = ask(world, key="shared-key-01")
    member(world, "박다른")
    second = ask(world, key="shared-key-01")
    assert second.status_code == 201 and second.json()["requestId"] != first.json()["requestId"]


def test_CSRF_토큰이_없으면_403이다(world: World) -> None:
    member(world)
    body = {"newName": "이새이름", "reason": "x", "password": PASSWORD}
    assert world.client.post(MINE, json=body, headers={"Idempotency-Key": "csrf-key-0001"}).status_code == 403


def test_내_요청만_보이고_최근_순이다(world: World) -> None:
    member(world)
    first = ask(world, "첫이름").json()["requestId"]
    boss(world)
    pending = call(world, "GET", f"{ADMIN}").json()["items"]
    call(world, "POST", f"{ADMIN}/{first}/reject", {})
    as_member(world, person(world, "박다른", MBL_TELNO="01099998888"))
    assert world.client.get(MINE).json()["items"] == []  # 다른 회원의 요청은 보이지 않는다
    assert [p["requestId"] for p in pending] == [first]


# --- 관리자 검토 --------------------------------------------------------------------------------


def test_관리자_권한이_없거나_동_범위뿐이면_403이다(world: World) -> None:
    member(world)
    sn = ask(world).json()["requestId"]
    for kw in ({"codes": ("AU.MBR_R",), "kind": "SK.GROUP"}, {"codes": ("AU.GRANT_W",), "kind": "SK.DONG"}):
        extra = {"dong_sn": dong(world, f"동{next(_n)}")["DONG_SN"]} if kw["kind"] == "SK.DONG" else {}
        boss(world, *kw["codes"], kind=kw["kind"], **extra)
        assert call(world, "GET", ADMIN).status_code == 403
        assert call(world, "POST", f"{ADMIN}/{sn}/approve", {}).status_code == 403
        assert call(world, "POST", f"{ADMIN}/{sn}/reject", {}).status_code == 403
    assert profile_name(world) == "김회원"


def test_검토_중_목록은_오래된_것부터_이름은_가려서_주고_새_이름과_사유는_그대로_준다(world: World) -> None:
    first = member(world, "김회원")
    one = ask(world, "이새이름", "개명").json()["requestId"]
    second = member(world, "박다른")
    two = ask(world, "최새이름", "오타 정정").json()["requestId"]
    boss(world)
    items = call(world, "GET", ADMIN).json()["items"]
    assert [i["requestId"] for i in items] == [one, two]
    assert (items[0]["memberId"], items[0]["loginId"], items[0]["currentNameMasked"]) == (
        str(first["MBR_SN"]),
        first["LGN_ID"],
        "김*원",
    )
    assert (items[0]["requestedName"], items[0]["reason"], items[0]["state"]) == (
        "이새이름",
        "개명",
        "PENDING",
    )
    assert items[1]["memberId"] == str(second["MBR_SN"]) and items[1]["decidedBy"] is None


def test_승인하면_이름이_바뀌고_결정한_담당자와_메모가_남으며_다시_결정할_수_없다(world: World) -> None:
    member(world)
    sn = ask(world, "이새이름").json()["requestId"]
    who = boss(world)
    res = call(world, "POST", f"{ADMIN}/{sn}/approve", {"note": "판결문 확인"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["state"], out["decisionNote"], out["currentNameMasked"]) == (
        "APPROVED",
        "판결문 확인",
        mask_name("이새이름"),
    )
    assert out["decidedBy"] is not None and out["decidedAt"]
    [job] = jobs(world, "NAME_CHANGE_DECIDE")
    assert (job["a"], int(job["g"]), job["k"], job["c"]) == (
        "AK.ADMIN",
        int(who.row["MNGR_SN"]),
        sn,
        "승인 판결문 확인",
    )
    for action in ("approve", "reject"):
        again = call(world, "POST", f"{ADMIN}/{sn}/{action}", {})
        assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE", action
    assert len(jobs(world, "NAME_CHANGE_DECIDE")) == 1
    pending = call(world, "GET", ADMIN).json()["items"]
    done = call(world, "GET", f"{ADMIN}?state=DECIDED").json()["items"]
    assert pending == [] and [d["requestId"] for d in done] == [sn]


def test_승인한_뒤_회원은_바뀐_이름을_보고_새_요청을_할_수_있다(world: World) -> None:
    who = member(world)
    sn = ask(world, "이새이름").json()["requestId"]
    boss(world)
    call(world, "POST", f"{ADMIN}/{sn}/approve", {})
    as_member(world, who)
    assert profile_name(world) == "이새이름"
    mine = world.client.get(MINE).json()["items"]
    assert [(m["requestId"], m["state"]) for m in mine] == [(sn, "APPROVED")]
    assert ask(world, "또새이름").status_code == 201  # 결정이 끝났으니 다시 요청할 수 있다


def test_반려하면_이름은_그대로이고_회원에게_메모가_보인다(world: World) -> None:
    who = member(world)
    sn = ask(world, "이새이름").json()["requestId"]
    boss(world)
    res = call(world, "POST", f"{ADMIN}/{sn}/reject", {"note": "증빙 미확인"})
    assert res.status_code == 200 and res.json()["state"] == "REJECTED"
    as_member(world, who)
    assert profile_name(world) == "김회원"
    [mine] = world.client.get(MINE).json()["items"]
    assert (mine["state"], mine["decisionNote"]) == ("REJECTED", "증빙 미확인")
    [job] = jobs(world, "NAME_CHANGE_DECIDE")
    assert job["c"] == "반려 증빙 미확인"


@pytest.mark.parametrize("state", ["MS.WITHDRAW", "MS.LOCKED"])
def test_정상이_아닌_회원의_요청은_승인할_수_없고_반려는_할_수_있다(world: World, state: str) -> None:
    who = member(world)
    sn = ask(world, "이새이름").json()["requestId"]
    world.db.execute(
        text("UPDATE TB_MBR SET MBR_STTS_CD=:s WHERE MBR_SN=:m"), {"s": state, "m": who["MBR_SN"]}
    )
    boss(world)
    blocked = call(world, "POST", f"{ADMIN}/{sn}/approve", {})
    assert blocked.status_code == 409 and blocked.json()["code"] == "CONFLICT_STATE"
    name = world.db.execute(text("SELECT MBR_NM FROM TB_MBR WHERE MBR_SN=:m"), {"m": who["MBR_SN"]}).scalar()
    assert name == "김회원" and jobs(world, "NAME_CHANGE_DECIDE") == []
    assert call(world, "POST", f"{ADMIN}/{sn}/reject", {}).status_code == 200


def test_없는_요청과_다른_묶음의_요청과_다른_작업의_이력은_404이다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")
    stranger = person(world, "남의회원", OPER_BNDL_SN=other["OPER_BNDL_SN"])
    foreign = world.factory.make(
        "TB_JOB_HSTRY",
        ACTR_TYPE_CD="AK.MEMBER",
        OPER_BNDL_SN=other["OPER_BNDL_SN"],
        MBR_SN=stranger["MBR_SN"],
        JOB_CD="NAME_CHANGE_REQUEST",
        CHG_CN="요청 [idem a:b] v1:xx",
    )
    unrelated = world.factory.make(
        "TB_JOB_HSTRY", ACTR_TYPE_CD="AK.SYSTEM", JOB_CD="RETENTION_EXECUTE", CHG_CN="처리 1건 [자동]"
    )
    boss(world)
    for sn in (999999, foreign["JOB_HSTRY_SN"], unrelated["JOB_HSTRY_SN"]):
        assert call(world, "POST", f"{ADMIN}/{sn}/approve", {}).status_code == 404, sn
        assert call(world, "POST", f"{ADMIN}/{sn}/reject", {}).status_code == 404, sn
    assert call(world, "GET", ADMIN).json()["items"] == []  # 다른 묶음의 요청은 목록에 없다


def test_CSRF_토큰이_없으면_관리자_결정도_403이다(world: World) -> None:
    member(world)
    sn = ask(world).json()["requestId"]
    who = boss(world)
    for action in ("approve", "reject"):
        res = world.client.post(f"/api/admin/v1{ADMIN}/{sn}/{action}", json={})
        assert res.status_code == 403, action
    assert who is not None


def test_시스템_배정은_묶음_전체_권한이어도_이름_요청을_보거나_결정하지_못한다(world: World) -> None:
    member(world)
    sn = ask(world).json()["requestId"]
    boss(world, "AU.GRANT_W", kind="SK.SYSTEM")  # 시스템 배정은 회원 정보를 바꾸지 못한다(R20)
    assert call(world, "GET", ADMIN).status_code == 403
    assert call(world, "POST", f"{ADMIN}/{sn}/approve", {}).status_code == 403
    assert call(world, "POST", f"{ADMIN}/{sn}/reject", {}).status_code == 403
    assert profile_name(world) == "김회원"
