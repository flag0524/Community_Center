# 관리자 권한 배정(조회·위임 범위·기간·자기 배정 금지·회수·멱등)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.admin_access import Admin, scope_for
from app.domain.admin.types import AdminAuthority as AU
from tests.test_admin_access import dong, role
from tests.test_admin_refunds import call, staff, use
from tests.world import START, World, make_admin

pytestmark = pytest.mark.db

_n = itertools.count(1)
TODAY = "2026-11-09"  # 시험 시계는 한국 시각 2026-11-09 18:00이다


def grantor(w: World, *codes: str, end: str | None = None, **kw: Any) -> Any:
    who = staff(w, f"gr{next(_n)}", "AU.GRANT_W", *codes, **kw)
    if end is not None:
        w.db.execute(text("UPDATE TB_MNGR_SCP SET VLD_END_DT=:e WHERE MNGR_SN=:m"), {"e": end, "m": who.sn})
    use(w, who)
    return who


def target(w: World, name: str = "대상자") -> dict[str, Any]:
    return make_admin(w, f"tg{next(_n)}", MNGR_NM=name)


def body(admin: dict[str, Any], r: dict[str, Any], scope: str = "GROUP", **values: Any) -> dict[str, Any]:
    return {
        "adminId": str(admin["MNGR_SN"]),
        "roleId": str(r["ROLE_SN"]),
        "scope": scope,
        "dongId": None,
        "validFrom": TODAY,
        "validTo": None,
        **values,
    }


def give(w: World, payload: dict[str, Any], key: str | None = None) -> Any:
    return call(
        w, "POST", "/role-assignments", payload, **{"Idempotency-Key": key or f"role-key-{next(_n):06d}"}
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def admin_of(w: World, who: dict[str, Any]) -> Admin:
    return Admin(int(who["MNGR_SN"]), w.bundle, None)  # type: ignore[arg-type]


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_배정_권한이_없으면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/role-assignments").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R", "AU.ROLE_W", "AU.MNGR_W"))
    r = role(world, "수강신청 조회", "AU.APLY_R")
    for method, path, payload in (
        ("GET", "/role-assignment-options", None),
        ("GET", "/role-assignments", None),
        ("GET", "/role-assignments/1", None),
        ("POST", "/role-assignments", body(target(world), r)),
        ("POST", "/role-assignments/1/revoke", {"version": 1}),
    ):
        res = call(world, method, path, payload, **{"Idempotency-Key": "role-key-0001"})
        assert res.status_code == 403, path


# --- 위임 선택지 --------------------------------------------------------------------------------


def test_선택지는_내가_가진_권한과_범위_안의_역할만_주고_자기_자신은_뺀다(world: World) -> None:
    dong(world, "가동")
    dong(world, "나동")
    me = grantor(world, "AU.APLY_R", "AU.APLY_W")
    mine = role(world, "신청 조회", "AU.APLY_R")
    both = role(world, "신청 처리", "AU.APLY_R", "AU.APLY_W")
    role(world, "환불 승인", "AU.APLY_R", "AU.RFND_A")  # 내가 갖지 않은 권한이 섞여 있다
    role(world, "강사 심사", "AU.INSTR_W")
    role(world, "비어 있음")
    role(world, "사용 안 함", "AU.APLY_R", USE_YN="N")
    other = target(world, "다른 관리자")
    target(world, "중지된 관리자")
    world.db.execute(text("UPDATE TB_MNGR SET USE_YN='N' WHERE MNGR_NM='중지된 관리자'"))
    out = call(world, "GET", "/role-assignment-options").json()
    names = {r["name"]: r for r in out["roles"]}
    assert set(names) == {"신청 조회", "신청 처리", f"r-{me.row['LGN_ID']}"}
    assert names["신청 조회"]["scopes"] == ["GROUP", "DONG"] and names["신청 처리"]["authorities"] == [
        "AU.APLY_R",
        "AU.APLY_W",
    ]
    own = names[f"r-{me.row['LGN_ID']}"]  # 내 역할에는 GRANT_W(구조 권한)가 있어 동 범위로는 줄 수 없다
    assert own["scopes"] == ["GROUP"]
    assert [a["name"] for a in out["admins"] if a["id"] == str(me.sn)] == []
    assert str(other["MNGR_SN"]) in {a["id"] for a in out["admins"]}
    assert "중지된 관리자" not in [a["name"] for a in out["admins"]]
    assert sorted(d["name"] for d in out["dongs"]) == ["가동", "나동"]
    assert mine["ROLE_SN"] and both["ROLE_SN"]


def test_동_범위_부여자는_자기_동의_동_범위_역할만_준다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    grantor(world, "AU.APLY_R", kind="SK.DONG", dong_sn=a["DONG_SN"])
    role(world, "신청 조회", "AU.APLY_R")
    role(world, "강사 심사", "AU.INSTR_W")
    out = call(world, "GET", "/role-assignment-options").json()
    assert [(r["name"], r["scopes"]) for r in out["roles"] if r["name"] == "신청 조회"] == [
        ("신청 조회", ["DONG"])
    ]
    assert [r["name"] for r in out["roles"] if r["name"] == "강사 심사"] == []
    assert [d["name"] for d in out["dongs"]] == ["가동"] and b["DONG_SN"]


def test_전체_운영구조_부여자는_구조_권한_역할만_줄_수_있다(world: World) -> None:
    grantor(world, "AU.ROLE_W", "AU.MNGR_W", kind="SK.SYSTEM")
    role(world, "구조 관리", "AU.ROLE_W", "AU.MNGR_W")
    role(world, "신청 조회", "AU.APLY_R")
    out = call(world, "GET", "/role-assignment-options").json()
    names = {r["name"]: r["scopes"] for r in out["roles"]}
    assert names["구조 관리"] == ["SYSTEM", "GROUP"] and "신청 조회" not in names


# --- 배정 ---------------------------------------------------------------------------------------


def test_배정하면_대상이_그_권한을_갖고_부여자와_기록이_남는다(world: World) -> None:
    me = grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    who = target(world, "김담당")
    res = give(world, body(who, r, validTo="2026-12-31"))
    assert res.status_code == 201, res.text
    out = res.json()
    assert (
        out["adminName"],
        out["roleName"],
        out["scope"],
        out["scopeLabel"],
        out["validFrom"],
        out["validTo"],
    ) == (
        "김담당",
        "신청 조회",
        "GROUP",
        "운영묶음 전체",
        TODAY,
        "2026-12-31",
    )
    assert (out["status"], out["authorities"], out["version"], out["canRevoke"], out["grantedBy"]) == (
        "ACTIVE",
        ["AU.APLY_R"],
        1,
        True,
        me.row["MNGR_NM"],
    )
    [row] = rows(world, "SELECT * FROM TB_MNGR_SCP WHERE MNGR_SN=:m", m=who["MNGR_SN"])
    assert (
        row["SCP_TYPE_CD"].strip(),
        row["OPER_BNDL_SN"],
        row["DONG_SN"],
        row["GRNT_MNGR_SN"],
        row["USE_YN"],
        row["RCRD_VER"],
    ) == (
        "SK.GROUP",
        world.bundle,
        None,
        me.sn,
        "Y",
        1,
    )
    assert row["VLD_BGNG_DT"] == datetime(2026, 11, 8, 15, 0) and row["VLD_END_DT"] == datetime(
        2026, 12, 31, 15, 0
    )
    [job] = rows(world, "SELECT MNGR_SN m, TRGT_KEY_VL k FROM TB_JOB_HSTRY WHERE JOB_CD='ROLE_GRANT'")
    assert (job["m"], job["k"]) == (me.sn, out["assignmentId"])
    assert scope_for(world.db, admin_of(world, who), AU.APLY_R, START).whole  # 판정 함수가 이 배정을 쓴다
    assert not scope_for(
        world.db, admin_of(world, who), AU.APLY_R, datetime(2027, 1, 1)
    ).whole  # 종료일 다음 날부터는 끝난다


def test_시작_전_배정은_예정이고_동_배정은_동_이름을_보인다(world: World) -> None:
    a = dong(world, "가동")
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    soon = give(world, body(target(world), r, validFrom="2026-11-20")).json()
    assert (soon["status"], soon["validFrom"], soon["validTo"]) == ("SCHEDULED", "2026-11-20", None)
    local = give(world, body(target(world), r, "DONG", dongId=str(a["DONG_SN"]))).json()
    assert (local["scope"], local["scopeLabel"]) == ("DONG", "가동")
    [row] = rows(
        world,
        "SELECT DONG_SN d, OPER_BNDL_SN b FROM TB_MNGR_SCP WHERE MNGR_SCP_SN=:s",
        s=local["assignmentId"],
    )
    assert (row["d"], row["b"]) == (a["DONG_SN"], world.bundle)


def test_자기_자신과_없는_대상과_쓸_수_없는_역할은_거절한다(world: World) -> None:
    me = grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    me_row = {"MNGR_SN": me.sn}
    gone = target(world)
    world.db.execute(text("UPDATE TB_MNGR SET USE_YN='N' WHERE MNGR_SN=:m"), {"m": gone["MNGR_SN"]})
    off = role(world, "꺼진 역할", "AU.APLY_R", USE_YN="N")
    empty = role(world, "빈 역할")
    world.db.commit()  # 오류 응답의 롤백이 준비한 변경을 되돌리지 않게 고정한다
    cases = [
        (body(me_row, r), "adminId"),
        (body({"MNGR_SN": 999999999}, r), "adminId"),
        (body(gone, r), "adminId"),
        (body(target(world), {"ROLE_SN": 999999999}), "roleId"),
        (body(target(world), off), "roleId"),
        (body(target(world), empty), "roleId"),
    ]
    for payload, field in cases:
        res = give(world, payload)
        assert res.status_code == 422 and field in res.json()["fields"], payload
    assert rows(world, "SELECT COUNT(*) n FROM TB_MNGR_SCP")[0]["n"] == 1  # 내 배정뿐이다


def test_내가_갖지_않은_권한이_있는_역할은_줄_수_없다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "환불 승인", "AU.APLY_R", "AU.RFND_A")
    res = give(world, body(target(world), r))
    assert res.status_code == 422 and "roleId" in res.json()["fields"] and "넘는" in res.json()["message"]


def test_내_배정_기간을_넘는_기간은_줄_수_없다(world: World) -> None:
    grantor(world, "AU.APLY_R", end="2026-12-31 15:00:00")  # 한국 시각 12월 31일 끝까지
    r = role(world, "신청 조회", "AU.APLY_R")
    assert give(world, body(target(world), r, validTo="2026-12-31")).status_code == 201
    for extra in (
        {"validTo": "2027-01-01"},
        {"validTo": None},
        {"validFrom": "2026-12-30", "validTo": "2027-02-01"},
    ):
        res = give(world, body(target(world), r, **extra))
        assert res.status_code == 422 and "roleId" in res.json()["fields"], extra


def test_내_권한이_여러_배정에_이어져_있으면_그_전체_기간까지_줄_수_있다(world: World) -> None:
    me = grantor(world, "AU.APLY_R", end="2026-12-01 15:00:00")
    second = role(world, "신청 조회 연장", "AU.APLY_R")
    world.db.execute(
        text(
            "INSERT INTO TB_MNGR_SCP (MNGR_SN, ROLE_SN, SCP_TYPE_CD, OPER_BNDL_SN, VLD_BGNG_DT, VLD_END_DT, GRNT_MNGR_SN, USE_YN, REG_DT, RCRD_VER)"
            " VALUES (:m, :r, 'SK.GROUP', :b, '2026-12-01 15:00:00', '2026-12-31 15:00:00', :m, 'Y', :n, 1)"
        ),
        {"m": me.sn, "r": second["ROLE_SN"], "b": world.bundle, "n": START},
    )
    r = role(world, "신청 조회", "AU.APLY_R")
    assert give(world, body(target(world), r, validTo="2026-12-31")).status_code == 201  # 이어진 두 기간 안
    assert give(world, body(target(world), r, validTo="2027-01-05")).status_code == 422


def test_시작일은_오늘_이후이고_종료일은_시작일_이후여야_한다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    past = give(world, body(target(world), r, validFrom="2026-11-08"))
    assert past.status_code == 422 and "validFrom" in past.json()["fields"]
    back = give(world, body(target(world), r, validFrom="2026-11-20", validTo="2026-11-19"))
    assert back.status_code == 422 and "validTo" in back.json()["fields"]
    assert (
        give(world, body(target(world), r, validFrom="2026-11-20", validTo="2026-11-20")).status_code == 201
    )  # 하루짜리


def test_범위와_동과_역할의_조합이_틀리면_거절한다(world: World) -> None:
    a = dong(world, "가동")
    grantor(world, "AU.APLY_R", "AU.INSTR_W")
    plain = role(world, "신청 조회", "AU.APLY_R")
    wide = role(world, "강사 심사", "AU.INSTR_W")
    who = target(world)
    for payload, field in (
        (body(who, plain, "DONG"), "dongId"),  # 동을 골라야 한다
        (body(who, plain, "DONG", dongId="999999999"), "dongId"),
        (body(who, plain, "GROUP", dongId=str(a["DONG_SN"])), "dongId"),
        (
            body(who, wide, "DONG", dongId=str(a["DONG_SN"])),
            "scope",
        ),  # 묶음 공통 권한은 동 담당자에게 줄 수 없다
        (body(who, plain, "SYSTEM"), "scope"),  # 업무 권한은 전체 운영구조 범위로 줄 수 없다
    ):
        res = give(world, payload)
        assert res.status_code == 422 and field in res.json()["fields"], payload
    assert give(world, body(who, wide, "GROUP")).status_code == 201


def test_동_범위_부여자는_자기_동에만_줄_수_있다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    grantor(world, "AU.APLY_R", kind="SK.DONG", dong_sn=a["DONG_SN"])
    r = role(world, "신청 조회", "AU.APLY_R")
    ok = give(world, body(target(world), r, "DONG", dongId=str(a["DONG_SN"])))
    assert ok.status_code == 201 and ok.json()["scopeLabel"] == "가동"
    for payload in (
        body(target(world), r, "DONG", dongId=str(b["DONG_SN"])),
        body(target(world), r, "GROUP"),
    ):
        assert give(world, payload).status_code == 422, payload


def extra_assignment(w: World, who: Any, r: dict[str, Any], kind: str, dong_sn: Any = None) -> None:
    """부여자에게 따로 준 배정 한 줄. 권한 배정 권한(GRANT_W)과 범위가 다른 업무 권한을 만들 때 쓴다."""
    w.factory.make(
        "TB_MNGR_SCP",
        MNGR_SN=who.sn,
        ROLE_SN=r["ROLE_SN"],
        SCP_TYPE_CD=kind,
        OPER_BNDL_SN=None if kind == "SK.SYSTEM" else w.bundle,
        DONG_SN=dong_sn,
        VLD_BGNG_DT=START - timedelta(days=1),
        GRNT_MNGR_SN=who.sn,
    )


def test_배정_권한의_범위가_동이면_업무_권한이_묶음이어도_다른_동에는_줄_수_없다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    me = grantor(world, kind="SK.DONG", dong_sn=a["DONG_SN"])  # GRANT_W만 가-동 범위
    r = role(world, "신청 조회", "AU.APLY_R")
    extra_assignment(world, me, r, "SK.GROUP")  # 신청 조회는 묶음 전체로 가졌다
    assert give(world, body(target(world), r, "DONG", dongId=str(a["DONG_SN"]))).status_code == 201
    res = give(world, body(target(world), r, "DONG", dongId=str(b["DONG_SN"])))
    assert res.status_code == 422 and "roleId" in res.json()["fields"]
    assert give(world, body(target(world), r, "GROUP")).status_code == 422  # 묶음 전체로도 줄 수 없다


def test_전체_운영구조_배정으로_가진_업무_권한은_줄_수_없다(world: World) -> None:
    me = grantor(world, kind="SK.SYSTEM")
    r = role(world, "신청 조회", "AU.APLY_R")
    extra_assignment(
        world, me, r, "SK.SYSTEM"
    )  # 업무 권한을 전체 운영구조 범위로 가졌지만 판정에는 쓰이지 않는다(R29)
    res = give(world, body(target(world), r, "GROUP"))
    assert res.status_code == 422 and "roleId" in res.json()["fields"]
    assert "신청 조회" not in [
        x["name"] for x in call(world, "GET", "/role-assignment-options").json()["roles"]
    ]


def test_내가_가진_동_배정은_그_동에만_줄_수_있다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    me = grantor(world)  # GRANT_W는 묶음 전체
    r = role(world, "신청 조회", "AU.APLY_R")
    extra_assignment(world, me, r, "SK.DONG", a["DONG_SN"])  # 신청 조회는 가동만
    assert give(world, body(target(world), r, "DONG", dongId=str(a["DONG_SN"]))).status_code == 201
    res = give(world, body(target(world), r, "DONG", dongId=str(b["DONG_SN"])))
    assert res.status_code == 422 and "roleId" in res.json()["fields"]
    assert give(world, body(target(world), r, "GROUP")).status_code == 422


def test_전체_운영구조_부여자가_구조_역할을_전체_범위로_주면_묶음_없이_저장한다(world: World) -> None:
    grantor(world, "AU.ROLE_W", kind="SK.SYSTEM")
    r = role(world, "역할 관리", "AU.ROLE_W")
    res = give(world, body(target(world), r, "SYSTEM"))
    assert res.status_code == 201, res.text
    assert (res.json()["scope"], res.json()["scopeLabel"]) == ("SYSTEM", "전체 운영구조")
    [row] = rows(
        world,
        "SELECT OPER_BNDL_SN b, DONG_SN d FROM TB_MNGR_SCP WHERE MNGR_SCP_SN=:s",
        s=res.json()["assignmentId"],
    )
    assert (row["b"], row["d"]) == (None, None)
    assert call(world, "GET", f"/role-assignments/{res.json()['assignmentId']}").status_code == 200


def test_같은_대상에_같은_역할·범위가_겹치면_거절하고_이어지는_기간은_허용한다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    who = target(world)
    assert give(world, body(who, r, validTo="2026-11-30")).status_code == 201
    dup = give(world, body(who, r, validFrom="2026-11-30", validTo="2026-12-10"))
    assert dup.status_code == 422 and "이미" in dup.json()["message"]
    assert give(world, body(who, r, validFrom="2026-12-01", validTo="2026-12-10")).status_code == 201
    other = role(world, "다른 조회", "AU.APLY_R")
    assert give(world, body(who, other)).status_code == 201  # 다른 역할은 겹쳐도 된다
    assert give(world, body(target(world), r)).status_code == 201  # 다른 대상도 된다


def test_같은_키로_다시_보내면_같은_배정이고_내용이_다르면_409다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    who = target(world)
    first = give(world, body(who, r), "role-key-same01").json()
    again = give(world, body(who, r), "role-key-same01")
    assert again.status_code == 201 and again.json()["assignmentId"] == first["assignmentId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_MNGR_SCP WHERE MNGR_SN=:m", m=who["MNGR_SN"])[0]["n"] == 1
    other = give(world, body(who, r, validTo="2026-12-31"), "role-key-same01")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/role-assignments", body(who, r)).status_code in (400, 422)  # 키 필수


# --- 조회 ---------------------------------------------------------------------------------------


def seed(world: World, who: dict[str, Any], r: dict[str, Any], kind: str, **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "MNGR_SN": who["MNGR_SN"],
        "ROLE_SN": r["ROLE_SN"],
        "SCP_TYPE_CD": kind,
        "OPER_BNDL_SN": None if kind == "SK.SYSTEM" else world.bundle,
        "VLD_BGNG_DT": START - timedelta(days=3),
        "GRNT_MNGR_SN": who["MNGR_SN"],
    }
    return world.factory.make("TB_MNGR_SCP", **{**defaults, **values})


def test_목록은_상태와_이름으로_거르고_최근_배정이_먼저이며_쪽을_나눈다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    kim, park = target(world, "김담당"), target(world, "박담당")
    active = seed(world, kim, r, "SK.GROUP", REG_DT=START - timedelta(days=3))
    future = seed(
        world, kim, r, "SK.GROUP", VLD_BGNG_DT=START + timedelta(days=5), REG_DT=START - timedelta(days=2)
    )
    ended = seed(
        world, park, r, "SK.GROUP", VLD_END_DT=START - timedelta(days=1), REG_DT=START - timedelta(days=1)
    )
    revoked = seed(world, park, r, "SK.GROUP", USE_YN="N", REG_DT=START)

    def ids(qs: str) -> list[str]:
        return [i["assignmentId"] for i in call(world, "GET", f"/role-assignments{qs}").json()["items"]]

    seeds = {str(x["MNGR_SCP_SN"]) for x in (active, future, ended, revoked)}
    mine = [i for i in ids("") if i in seeds]
    assert mine == [
        str(revoked["MNGR_SCP_SN"]),
        str(ended["MNGR_SCP_SN"]),
        str(future["MNGR_SCP_SN"]),
        str(active["MNGR_SCP_SN"]),
    ]
    assert ids("?status=ACTIVE").count(str(active["MNGR_SCP_SN"])) == 1 and str(
        future["MNGR_SCP_SN"]
    ) not in ids("?status=ACTIVE")
    assert ids("?status=SCHEDULED") == [str(future["MNGR_SCP_SN"])]
    assert ids("?status=EXPIRED") == [str(ended["MNGR_SCP_SN"])]
    assert ids("?status=REVOKED") == [str(revoked["MNGR_SCP_SN"])]
    assert sorted(ids("?q=박")) == sorted([str(ended["MNGR_SCP_SN"]), str(revoked["MNGR_SCP_SN"])])
    assert ids("?q=_") == [] and ids("?q=%25") == []
    body_ = call(world, "GET", "/role-assignments?size=2&page=2").json()
    assert (len(body_["items"]), body_["canGrant"], body_["total"]) == (2, True, 5)
    assert call(world, "GET", "/role-assignments?status=NOPE").status_code in (400, 422)


def test_동_범위_부여자는_자기_동의_동_배정만_본다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    grantor(world, "AU.APLY_R", kind="SK.DONG", dong_sn=a["DONG_SN"])
    r = role(world, "신청 조회", "AU.APLY_R")
    mine = seed(world, target(world, "가동담당"), r, "SK.DONG", DONG_SN=a["DONG_SN"])
    other = seed(world, target(world, "나동담당"), r, "SK.DONG", DONG_SN=b["DONG_SN"])
    group = seed(world, target(world, "묶음담당"), r, "SK.GROUP")
    system = seed(world, target(world, "구조담당"), r, "SK.SYSTEM")
    items = call(world, "GET", "/role-assignments").json()["items"]
    listed = {i["assignmentId"] for i in items}
    assert str(mine["MNGR_SCP_SN"]) in listed
    assert not ({str(other["MNGR_SCP_SN"]), str(group["MNGR_SCP_SN"]), str(system["MNGR_SCP_SN"])} & listed)
    for hidden in (other, group, system):
        assert call(world, "GET", f"/role-assignments/{hidden['MNGR_SCP_SN']}").status_code == 404
        assert (
            call(
                world, "POST", f"/role-assignments/{hidden['MNGR_SCP_SN']}/revoke", {"version": 1}
            ).status_code
            == 404
        )
    assert call(world, "GET", f"/role-assignments/{mine['MNGR_SCP_SN']}").status_code == 200


def test_묶음_전체_부여자는_전체_운영구조_배정도_보고_없는_배정은_404다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    system = seed(world, target(world), r, "SK.SYSTEM")
    assert call(world, "GET", f"/role-assignments/{system['MNGR_SCP_SN']}").status_code == 200
    assert call(world, "GET", "/role-assignments/999999999").status_code == 404
    assert call(world, "GET", "/role-assignments/abc").status_code in (400, 422)


# --- 회수 ---------------------------------------------------------------------------------------


def test_회수하면_사용_중지로_바꾸고_그_권한이_바로_사라진다(world: World) -> None:
    me = grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    who = target(world)
    sn = give(world, body(who, r)).json()["assignmentId"]
    assert scope_for(world.db, admin_of(world, who), AU.APLY_R, START).whole
    res = call(world, "POST", f"/role-assignments/{sn}/revoke", {"version": 1})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["status"], out["version"], out["canRevoke"]) == ("REVOKED", 2, False)
    [row] = rows(world, "SELECT USE_YN u, RCRD_VER v FROM TB_MNGR_SCP WHERE MNGR_SCP_SN=:s", s=sn)
    assert (row["u"], row["v"]) == ("N", 2)  # 행은 지우지 않는다
    assert not scope_for(world.db, admin_of(world, who), AU.APLY_R, START).whole
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='ROLE_REVOKE'"
    )
    assert (job["m"], job["k"]) == (me.sn, sn) and "ACTIVE" in job["c"] and "REVOKED" in job["c"]
    assert call(world, "POST", f"/role-assignments/{sn}/revoke", {"version": 2}).status_code == 409


def test_시작_전_배정도_회수할_수_있고_끝난_배정은_409다(world: World) -> None:
    grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    future = seed(world, target(world), r, "SK.GROUP", VLD_BGNG_DT=START + timedelta(days=5))
    ended = seed(world, target(world), r, "SK.GROUP", VLD_END_DT=START - timedelta(days=1))
    assert (
        call(world, "POST", f"/role-assignments/{future['MNGR_SCP_SN']}/revoke", {"version": 1}).json()[
            "status"
        ]
        == "REVOKED"
    )
    res = call(world, "POST", f"/role-assignments/{ended['MNGR_SCP_SN']}/revoke", {"version": 1})
    assert res.status_code == 409 and res.json()["code"] == "CONFLICT_STATE"


def test_자기_배정은_회수할_수_없고_읽은_버전이_다르면_409다(world: World) -> None:
    me = grantor(world, "AU.APLY_R")
    r = role(world, "신청 조회", "AU.APLY_R")
    mine = rows(world, "SELECT MNGR_SCP_SN s FROM TB_MNGR_SCP WHERE MNGR_SN=:m", m=me.sn)[0]["s"]
    own = call(world, "POST", f"/role-assignments/{mine}/revoke", {"version": 1})
    assert own.status_code == 422 and "assignmentId" in own.json()["fields"]
    assert call(world, "GET", f"/role-assignments/{mine}").json()["canRevoke"] is False
    other = seed(world, target(world), r, "SK.GROUP")
    stale = call(world, "POST", f"/role-assignments/{other['MNGR_SCP_SN']}/revoke", {"version": 5})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert (
        rows(world, "SELECT USE_YN u FROM TB_MNGR_SCP WHERE MNGR_SCP_SN=:s", s=other["MNGR_SCP_SN"])[0]["u"]
        == "Y"
    )
