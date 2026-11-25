# 회원 본인 정보(조회·이메일 수정), 비밀번호 변경, 탈퇴(진행 중인 신청·결제·환불이 있으면 거절)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.passwords import verify_password
from app.auth.sessions import issue_session
from tests.test_applications_read import application, open_course, payment
from tests.test_member_inquiries import as_member, csrf, person
from tests.world import MEMBER, PASSWORD, START, World, login

pytestmark = pytest.mark.db

_n = itertools.count(1)
NEW_PASSWORD = "Brand-New-Pass-77"


def put(w: World, path: str, body: dict[str, Any]) -> Any:
    return w.client.put(f"{MEMBER}{path}", json=body, headers=csrf(w))


def withdraw(w: World, password: str = PASSWORD, **extra: Any) -> Any:
    return w.client.post(f"{MEMBER}/me/withdraw", json={"password": password, **extra}, headers=csrf(w))


def row(w: World, sql: str, **params: Any) -> Any:
    return w.db.execute(text(sql), params).mappings().one()


def member(w: World, **values: Any) -> dict[str, Any]:
    who = person(w, MBL_TELNO="01012345678", EML_ADDR="old@example.com", **values)
    as_member(w, who)
    return who


def refund_of(w: World, app: dict[str, Any], status: str) -> dict[str, Any]:
    paid = payment(w, app, "PS.PAID", STLM_AMT=30000)
    extra: dict[str, Any] = {}
    if status == "RS.HOLD":
        extra["HLDOF_RSN"] = "서류 확인"
    if status == "RS.REJECT":
        extra["RJCT_RSN"] = "불가"
    return w.factory.make(
        "TB_RFND", STLM_SN=paid["STLM_SN"], RFND_AMT=30000, RFND_STTS_CD=status, RFND_DMND_DT=START, **extra
    )


# --- 조회·이메일 수정 -----------------------------------------------------------------------------


def test_로그인이_없으면_모두_401이다(world: World) -> None:
    world.db.commit()
    assert world.client.get(f"{MEMBER}/me/profile").status_code == 401
    assert world.client.put(f"{MEMBER}/me/profile", json={"email": "a@b.co"}).status_code == 401
    assert world.client.put(f"{MEMBER}/me/password", json={}).status_code == 401
    assert world.client.post(f"{MEMBER}/me/withdraw", json={}).status_code == 401


def test_내_정보는_전화번호를_가려서_보이고_거주지역은_비어_있다(world: World) -> None:
    who = member(world, HAB_RGN_CD="RA.JORI", HAB_IDNTY_STTS_CD="RV.OK")
    out = world.client.get(f"{MEMBER}/me/profile").json()
    assert out["memberId"] == str(who["MBR_SN"]) and out["loginId"] == who["LGN_ID"]
    assert (out["email"], out["phoneMasked"]) == ("old@example.com", "010-****-5678")
    assert (out["residenceDeclared"], out["residenceStatus"]) == (None, "VERIFIED")
    assert "01012345678" not in str(out)


def test_이메일만_고치고_거주지역과_센터_확인_구분은_바꾸지_않는다(world: World) -> None:
    who = member(world)
    out = put(world, "/me/profile", {"email": "new@example.com", "residenceDeclared": "JORI"})
    assert out.status_code == 200, out.text
    assert (out.json()["email"], out.json()["residenceDeclared"]) == ("new@example.com", None)
    saved = row(
        world,
        "SELECT EML_ADDR e, HAB_RGN_CD r, HAB_IDNTY_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m",
        m=who["MBR_SN"],
    )
    assert (saved["e"], saved["r"].strip(), saved["s"].strip()) == (
        "new@example.com",
        "RA.UNKNOWN",
        "RV.NONE",
    )
    job = row(
        world,
        "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='PROFILE_UPDATE' AND MBR_SN=:m",
        m=who["MBR_SN"],
    )
    assert "new@example.com" not in job["c"]  # 값은 작업이력에 남기지 않는다


def test_형식이_틀린_이메일은_400이고_CSRF_토큰이_없으면_거절한다(world: World) -> None:
    member(world)
    assert put(world, "/me/profile", {"email": "not-an-email"}).status_code == 400
    assert world.client.put(f"{MEMBER}/me/profile", json={"email": "a@b.co"}).status_code == 403


# --- 비밀번호 변경 --------------------------------------------------------------------------------


def test_현재_비밀번호가_틀리면_400이고_바뀌지_않는다(world: World) -> None:
    who = member(world)
    res = put(world, "/me/password", {"currentPassword": "wrong-password", "newPassword": NEW_PASSWORD})
    assert res.status_code == 400 and "currentPassword" in res.json()["fields"]
    world.db.commit()
    saved = row(world, "SELECT PSWD_HASH_VL h FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])
    assert verify_password(PASSWORD, saved["h"])


def test_비밀번호를_바꾸면_이_세션만_남기고_다른_세션은_끊는다(world: World) -> None:
    who = member(world)
    other, _ = issue_session(
        world.db, bundle_sn=world.bundle, member_sn=int(who["MBR_SN"]), admin_sn=None, now=START
    )
    res = put(world, "/me/password", {"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD})
    assert res.status_code == 204
    states = [
        r.d
        for r in world.db.execute(
            text("SELECT DSCD_RSN d FROM TB_LGN_SSN WHERE MBR_SN=:m ORDER BY LGN_SSN_SN"),
            {"m": who["MBR_SN"]},
        )
    ]
    assert states == [None, "PASSWORD_CHANGE"] and other  # 로그인한 세션은 남고 나머지는 끊겼다
    assert world.client.get(f"{MEMBER}/me/profile").status_code == 200
    saved = row(world, "SELECT PSWD_HASH_VL h FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])
    assert verify_password(NEW_PASSWORD, saved["h"]) and not verify_password(PASSWORD, saved["h"])
    job = row(
        world,
        "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='PASSWORD_CHANGE' AND MBR_SN=:m",
        m=who["MBR_SN"],
    )
    assert NEW_PASSWORD not in job["c"]
    world.client.cookies.clear()
    assert login(world, MEMBER, who["LGN_ID"], PASSWORD).status_code != 200
    assert login(world, MEMBER, who["LGN_ID"], NEW_PASSWORD).status_code == 200


def test_새_비밀번호가_10자_미만이면_400이다(world: World) -> None:
    member(world)
    assert (
        put(world, "/me/password", {"currentPassword": PASSWORD, "newPassword": "short"}).status_code == 400
    )


# --- 탈퇴 -----------------------------------------------------------------------------------------


def test_비밀번호가_틀리면_탈퇴하지_않는다(world: World) -> None:
    who = member(world)
    res = withdraw(world, "wrong-password")
    assert res.status_code == 400 and "password" in res.json()["fields"]
    world.db.commit()
    assert (
        row(world, "SELECT MBR_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])["s"].strip()
        == "MS.ACTIVE"
    )


@pytest.mark.parametrize(
    "case",
    [
        "wait",
        "hold",
        "payment-pending",
        "refund-request",
        "refund-hold",
        "refund-approve",
        "refund-pending",
        "refund-fail",  # PG 취소가 실패해 다시 처리해야 하는 환불(돌려줄 돈이 남아 있다)
    ],
)
def test_진행_중인_신청_결제_환불이_있으면_422이고_탈퇴하지_않는다(world: World, case: str) -> None:
    who = member(world)
    course = open_course(world)
    if case in ("wait", "hold"):
        application(world, who, course, "ES.WAIT" if case == "wait" else "ES.HOLD")
    elif case == "payment-pending":
        payment(world, application(world, who, course, "ES.CONFIRM"), "PS.PENDING")
    else:
        refund_of(world, application(world, who, course, "ES.CANCEL"), "RS." + case.split("-")[1].upper())
    world.db.commit()
    res = withdraw(world)
    assert res.status_code == 422 and res.json()["code"] == "RULE_REJECTED", res.text
    assert (
        row(world, "SELECT MBR_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])["s"].strip()
        == "MS.ACTIVE"
    )
    assert world.client.get(f"{MEMBER}/me/profile").status_code == 200


def test_끝난_신청과_완료된_환불은_막지_않고_다른_회원의_진행_건도_막지_않는다(world: World) -> None:
    who = member(world)
    course = open_course(world)
    application(world, who, course, "ES.CONFIRM")
    application(world, who, course, "ES.EXPIRE")
    refund_of(world, application(world, who, course, "ES.CANCEL"), "RS.DONE")
    refund_of(world, application(world, who, course, "ES.CANCEL"), "RS.REJECT")
    stranger = person(world, "남")
    application(world, stranger, course, "ES.HOLD")
    payment(world, application(world, stranger, open_course(world), "ES.CONFIRM"), "PS.PENDING")
    world.db.commit()
    res = withdraw(world, reason="NO_COURSE")
    assert res.status_code == 204, res.text
    cookie = res.headers.get("set-cookie", "")
    assert cookie.startswith("jori_session=") and "Max-Age=0" in cookie  # 쿠키를 지운다
    saved = row(world, "SELECT MBR_STTS_CD s, WHDWL_DT w FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])
    assert saved["s"].strip() == "MS.WITHDRAW" and saved["w"] is not None
    assert (
        row(world, "SELECT COUNT(*) n FROM TB_LGN_SSN WHERE MBR_SN=:m AND DSCD_DT IS NULL", m=who["MBR_SN"])[
            "n"
        ]
        == 0
    )
    job = row(
        world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='WITHDRAW' AND MBR_SN=:m", m=who["MBR_SN"]
    )
    assert "NO_COURSE" in job["c"]
    assert world.client.get(f"{MEMBER}/me/profile").status_code == 401
    world.client.cookies.clear()
    assert login(world, MEMBER, who["LGN_ID"], PASSWORD).status_code != 200


def test_탈퇴한_회원이_같은_세션으로_다시_부르면_401이고_탈퇴일은_바뀌지_않는다(world: World) -> None:
    who = member(world)
    world.db.commit()
    assert withdraw(world).status_code == 204
    first = row(world, "SELECT WHDWL_DT w FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])["w"]
    world.clock.advance(days=1)
    assert withdraw(world).status_code == 401
    assert row(world, "SELECT WHDWL_DT w FROM TB_MBR WHERE MBR_SN=:m", m=who["MBR_SN"])["w"] == first
    assert START - timedelta(seconds=1) < first


def test_탈퇴하면_다른_세션도_더_이상_쓸_수_없다(world: World) -> None:
    who = member(world)
    other, _ = issue_session(
        world.db, bundle_sn=world.bundle, member_sn=int(who["MBR_SN"]), admin_sn=None, now=START
    )
    world.db.commit()
    assert withdraw(world).status_code == 204
    world.client.cookies.set("jori_session", other)
    assert world.client.get(f"{MEMBER}/me/profile").status_code == 401
