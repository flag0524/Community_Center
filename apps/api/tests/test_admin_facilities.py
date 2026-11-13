# 관리자 센터·강의실(AU.FCLT_W, 센터-강의실 구조, 이름 중복, 사용 중지, 층·공개 여부 처리, 동 범위)을 실제 앱과 MariaDB로 확인하는 시험
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.world import World

pytestmark = pytest.mark.db


def body(kind: str = "CENTER", **values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": kind,
        "parentId": None,
        "name": "조리 센터",
        "floor": None,
        "address": "파주시 조리읍",
        "isPublic": True,
        "inUse": True,
    }
    if kind == "ROOM":
        base.update(name="1강의실", floor="3층", address=None)
    return {**base, **values}


def make(w: World, payload: dict[str, Any] | None = None, key: str = "fclt-key-0001") -> Any:
    return call(w, "POST", "/facilities", payload or body(), **{"Idempotency-Key": key})


def center(w: World, name: str = "조리 센터", key: str = "fclt-key-0001", **values: Any) -> dict[str, Any]:
    r = make(w, body("CENTER", name=name, **values), key)
    assert r.status_code == 201, r.text
    return dict(r.json())


def room(
    w: World, parent: dict[str, Any], name: str = "1강의실", key: str = "fclt-key-0002", **values: Any
) -> Any:
    return make(w, body("ROOM", parentId=parent["facilityId"], name=name, **values), key)


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/facilities").status_code == 401
    use(world, staff(world, "x", "AU.CORS_W", "AU.CORS_R"))
    for method, path, payload in (
        ("GET", "/facilities", None),
        ("POST", "/facilities", body()),
        ("GET", "/facilities/1", None),
        ("PUT", "/facilities/1", {**body(), "version": 1}),
    ):
        assert (
            call(world, method, path, payload, **{"Idempotency-Key": "fclt-key-0001"}).status_code == 403
        ), path


# --- 등록 ---------------------------------------------------------------------------------------


def test_센터를_등록하면_공통_센터로_저장하고_작업이력에_남긴다(world: World) -> None:
    boss = staff(world, "boss", "AU.FCLT_W")
    use(world, boss)
    r = make(world, body("CENTER", name="  조리 센터  ", address="  파주시  "))
    assert r.status_code == 201
    out = r.json()
    assert (out["kind"], out["parentId"], out["name"], out["address"], out["floor"]) == (
        "CENTER",
        None,
        "조리 센터",
        "파주시",
        None,
    )
    assert (out["isPublic"], out["inUse"], out["version"], out["scheduleCount"]) == (True, True, 1, 0)
    [row] = rows(world, "SELECT * FROM TB_FCLT")
    assert (row["FCLT_TYPE_CD"], row["DONG_SN"], row["UP_FCLT_SN"], row["USE_YN"], row["FCLT_EXPLN"]) == (
        "FT.CENTER",
        None,
        None,
        "Y",
        None,
    )
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='FCLT_CREATE'"
    )
    assert (job["m"], job["t"]) == (boss.sn, "TB_FCLT") and job["c"].startswith("CENTER [idem ")


def test_강의실은_센터_아래에_두고_층을_설명에_담아_읽을_때_떼어_낸다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    parent = center(world)
    r = room(world, parent, floor=" 3층 ")
    assert r.status_code == 201
    out = r.json()
    assert (out["kind"], out["parentId"], out["floor"], out["address"]) == (
        "ROOM",
        parent["facilityId"],
        "3층",
        None,
    )
    stored = rows(
        world, "SELECT FCLT_EXPLN e, FCLT_TYPE_CD t FROM TB_FCLT WHERE FCLT_SN=:s", s=out["facilityId"]
    )[0]
    assert stored == {"e": "층: 3층", "t": "FT.ROOM"}
    none = room(world, parent, "2강의실", "fclt-key-0003", floor=None)
    assert (
        none.json()["floor"] is None
        and rows(world, "SELECT FCLT_EXPLN e FROM TB_FCLT WHERE FCLT_SN=:s", s=none.json()["facilityId"])[0][
            "e"
        ]
        is None
    )


def test_구조_규칙을_검사한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    parent = center(world)
    other_room = room(world, parent).json()
    cases = [
        ("센터에_상위_시설", body("CENTER", parentId=parent["facilityId"], name="가"), "parentId"),
        ("강의실에_상위_없음", body("ROOM", parentId=None), "parentId"),
        ("강의실의_상위가_강의실", body("ROOM", parentId=other_room["facilityId"], name="나"), "parentId"),
        ("없는_상위", body("ROOM", parentId="999999999", name="다"), "parentId"),
        ("강의실에_주소", body("ROOM", parentId=parent["facilityId"], name="라", address="서울"), "address"),
        ("공백_이름", body("CENTER", name="   "), "name"),
        ("비공개", body("CENTER", name="마", isPublic=False), "isPublic"),
    ]
    for n, (label, payload, field) in enumerate(cases):
        r = make(world, payload, f"fclt-key-1{n:03d}")
        assert r.status_code == 422 and field in r.json()["fields"], label
    assert rows(world, "SELECT COUNT(*) n FROM TB_FCLT")[0]["n"] == 2


def test_같은_위치의_같은_이름은_거절하고_다른_센터_아래는_허용한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    a, b = center(world, "A 센터", "fclt-key-0001"), center(world, "B 센터", "fclt-key-0002")
    assert room(world, a, "1강의실", "fclt-key-0003").status_code == 201
    dup = room(world, a, "1강의실", "fclt-key-0004")
    assert dup.status_code == 422 and "name" in dup.json()["fields"]
    assert room(world, b, "1강의실", "fclt-key-0005").status_code == 201
    dup_center = make(world, body("CENTER", name="A 센터"), "fclt-key-0006")
    assert dup_center.status_code == 422 and "name" in dup_center.json()["fields"]


def test_사용을_중지한_시설의_이름도_중복으로_센다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    parent = center(world)
    made = room(world, parent).json()
    call(
        world,
        "PUT",
        f"/facilities/{made['facilityId']}",
        {**body("ROOM", parentId=parent["facilityId"]), "inUse": False, "version": 1},
    )
    assert room(world, parent, "1강의실", "fclt-key-0009").status_code == 422


def test_같은_키로_다시_보내면_같은_시설이고_내용이_다르면_409다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    first = make(world).json()
    again = make(world)
    assert again.status_code == 201 and again.json()["facilityId"] == first["facilityId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_FCLT")[0]["n"] == 1
    diff = make(world, body(name="다른 센터"))
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/facilities", body()).status_code in (400, 422)


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_센터_아래에_강의실을_이름순으로_묶고_일정_수를_준다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    b = center(world, "B 센터", "fclt-key-0001")
    a = center(world, "A 센터", "fclt-key-0002")
    r2 = room(world, a, "2강의실", "fclt-key-0003").json()
    room(world, a, "1강의실", "fclt-key-0004")
    room(world, b, "가강의실", "fclt-key-0005")
    from tests.test_courses_public import course, cycle  # noqa: PLC0415

    cyc = cycle(world)
    world.factory.make("TB_CORS_SCHDL", CORS_SN=course(world, cyc)["CORS_SN"], FCLT_SN=r2["facilityId"])
    items = call(world, "GET", "/facilities").json()["items"]
    assert [(i["name"], i["kind"]) for i in items] == [
        ("B 센터", "CENTER"),
        ("가강의실", "ROOM"),
        ("A 센터", "CENTER"),
        ("1강의실", "ROOM"),
        ("2강의실", "ROOM"),
    ]  # 센터는 만든 순서이고 그 아래 강의실이 이름순이다
    by = {i["name"]: i for i in items}
    assert by["2강의실"]["scheduleCount"] == 1 and by["1강의실"]["scheduleCount"] == 0
    detail = call(world, "GET", f"/facilities/{r2['facilityId']}").json()
    assert detail["scheduleCount"] == 1 and detail["parentId"] == a["facilityId"]
    assert call(world, "GET", "/facilities/999999999").status_code == 404
    assert call(world, "GET", "/facilities/abc").status_code in (400, 422)


# --- 수정 ---------------------------------------------------------------------------------------


def test_수정하면_버전이_오르고_사용을_중지해도_일정은_유지한다(world: World) -> None:
    boss = staff(world, "boss", "AU.FCLT_W")
    use(world, boss)
    parent = center(world)
    made = room(world, parent).json()
    from tests.test_courses_public import course, cycle  # noqa: PLC0415

    sched = world.factory.make(
        "TB_CORS_SCHDL", CORS_SN=course(world, cycle(world))["CORS_SN"], FCLT_SN=made["facilityId"]
    )
    r = call(
        world,
        "PUT",
        f"/facilities/{made['facilityId']}",
        {
            **body("ROOM", parentId=parent["facilityId"], name="새 이름", floor="4층"),
            "inUse": False,
            "version": 1,
        },
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["name"], out["floor"], out["inUse"], out["version"], out["scheduleCount"]) == (
        "새 이름",
        "4층",
        False,
        2,
        1,
    )
    assert rows(
        world, "SELECT FCLT_SN s FROM TB_CORS_SCHDL WHERE CORS_SCHDL_SN=:s", s=sched["CORS_SCHDL_SN"]
    )[0]["s"] == int(made["facilityId"])
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='FCLT_UPDATE'")
    assert (job["m"], job["c"]) == (boss.sn, "ROOM 사용 N")
    assert (
        rows(world, "SELECT MDFCN_DT d FROM TB_FCLT WHERE FCLT_SN=:s", s=made["facilityId"])[0]["d"]
        is not None
    )


def test_읽은_버전이_다르면_409이고_종류와_상위는_바꿀_수_없다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    a, b = center(world, "A 센터", "fclt-key-0001"), center(world, "B 센터", "fclt-key-0002")
    made = room(world, a, "1강의실", "fclt-key-0003").json()
    path = f"/facilities/{made['facilityId']}"
    base = body("ROOM", parentId=a["facilityId"])
    assert call(world, "PUT", path, {**base, "name": "첫 수정", "version": 1}).status_code == 200
    stale = call(world, "PUT", path, {**base, "name": "낡은 수정", "version": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    kind = call(world, "PUT", path, {**body("CENTER"), "version": 2})
    assert kind.status_code == 422 and "kind" in kind.json()["fields"]
    moved = call(world, "PUT", path, {**body("ROOM", parentId=b["facilityId"], name="첫 수정"), "version": 2})
    assert moved.status_code == 422 and "parentId" in moved.json()["fields"]
    assert call(world, "GET", path).json()["name"] == "첫 수정"


def test_수정에서도_이름_중복과_자기_이름은_구분한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    a = center(world)
    one = room(world, a, "1강의실", "fclt-key-0002").json()
    two = room(world, a, "2강의실", "fclt-key-0003").json()
    same = call(
        world,
        "PUT",
        f"/facilities/{one['facilityId']}",
        {**body("ROOM", parentId=a["facilityId"], name="1강의실"), "version": 1},
    )
    assert same.status_code == 200  # 자기 이름은 그대로 써도 된다
    dup = call(
        world,
        "PUT",
        f"/facilities/{two['facilityId']}",
        {**body("ROOM", parentId=a["facilityId"], name="1강의실"), "version": 1},
    )
    assert dup.status_code == 422 and "name" in dup.json()["fields"]
    off = call(
        world,
        "PUT",
        f"/facilities/{two['facilityId']}",
        {**body("ROOM", parentId=a["facilityId"], name="2강의실", isPublic=False), "version": 1},
    )
    assert off.status_code == 422 and "isPublic" in off.json()["fields"]


# --- 동 범위 ------------------------------------------------------------------------------------


def test_동_담당자는_자기_동_시설만_다루고_만든_센터는_자기_동이다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM="내 센터", DONG_SN=a["DONG_SN"])
    other = world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM="남 센터", DONG_SN=b["DONG_SN"])
    common = world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM="공통 센터")
    use(world, staff(world, "d", "AU.FCLT_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [i["name"] for i in call(world, "GET", "/facilities").json()["items"]] == ["내 센터"]
    for hidden in (other, common):
        sn = hidden["FCLT_SN"]
        assert call(world, "GET", f"/facilities/{sn}").status_code == 404
        assert (
            call(
                world, "PUT", f"/facilities/{sn}", {**body(name=hidden["FCLT_NM"]), "version": 1}
            ).status_code
            == 404
        )
        under = make(world, body("ROOM", parentId=str(sn), name="침범"), "fclt-key-7000")
        assert (
            under.status_code == 422 and "parentId" in under.json()["fields"]
        )  # 남의 센터 아래에는 못 만든다
    created = make(world, body("CENTER", name="새 센터"), "fclt-key-7001").json()
    assert int(
        rows(world, "SELECT DONG_SN d FROM TB_FCLT WHERE FCLT_SN=:s", s=created["facilityId"])[0]["d"]
    ) == int(a["DONG_SN"])
    sub = room(world, {"facilityId": str(mine["FCLT_SN"])}, "동 강의실", "fclt-key-7002").json()
    assert int(
        rows(world, "SELECT DONG_SN d FROM TB_FCLT WHERE FCLT_SN=:s", s=sub["facilityId"])[0]["d"]
    ) == int(a["DONG_SN"])
    use(world, staff(world, "boss", "AU.FCLT_W"))
    assert len(call(world, "GET", "/facilities").json()["items"]) == 5


def test_사용_중지로_등록하면_중지_상태로_저장한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.FCLT_W"))
    r = make(world, body("CENTER", inUse=False))
    assert r.status_code == 201 and r.json()["inUse"] is False
    assert rows(world, "SELECT USE_YN u FROM TB_FCLT")[0]["u"] == "N"
