# 보존·파기 실행(탈퇴 회원 비식별, 인증번호 요청 삭제, 확인 건수, 멱등, 권한, 실행 불가 대상)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import Actor, call, staff, use
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)


def operator(w: World, *codes: str, **kw: Any) -> Actor:
    who = staff(w, f"rx{next(_n)}", *(codes or ("AU.LOG_R", "AU.GRANT_W")), **kw)
    use(w, who)
    return who


def run(w: World, item: int, count: int, key: str | None = None) -> Any:
    return call(
        w,
        "POST",
        f"/retention/{item}/execute",
        {"expectedCount": count},
        **{"Idempotency-Key": key or f"retention-key-{next(_n):06d}"},
    )


def withdrawn(w: World, login: str, days: int, **values: Any) -> dict[str, Any]:
    return make_member(
        w,
        login,
        MBR_NM=f"이름{login}",
        MBL_TELNO="01012345678",
        EML_ADDR=f"{login}@example.com",
        MBR_STTS_CD="MS.WITHDRAW",
        WHDWL_DT=START - timedelta(days=days),
        **values,
    )


def member_row(w: World, sn: Any) -> Any:
    return (
        w.db.execute(
            text(
                "SELECT MBR_NM n, MBL_TELNO p, EML_ADDR e, LGN_ID l, MBR_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m"
            ),
            {"m": sn},
        )
        .mappings()
        .one()
    )


def otp(w: World, days: int, **values: Any) -> dict[str, Any]:
    return w.factory.make(
        "TB_CERT_DMND", OPER_BNDL_SN=w.bundle, REG_DT=START - timedelta(days=days), **values
    )


def cert_count(w: World) -> int:
    return int(
        w.db.execute(
            text("SELECT COUNT(*) FROM TB_CERT_DMND WHERE OPER_BNDL_SN=:b"), {"b": w.bundle}
        ).scalar()
        or 0
    )


# --- 권한·대상 -----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_조회_권한만_있거나_동_담당자면_403이다(world: World) -> None:
    withdrawn(world, "w1", 60)
    world.db.commit()
    res = world.client.post("/api/admin/v1/retention/1/execute", json={"expectedCount": 1})
    assert res.status_code == 401
    operator(world, "AU.LOG_R")
    assert run(world, 1, 1).status_code == 403
    operator(world, "AU.LOG_R", "AU.GRANT_W", kind="SK.DONG", dong_sn=dong(world, "가동")["DONG_SN"])
    assert run(world, 1, 1).status_code == 403  # 묶음 공통 자료라 묶음 전체 담당자만 실행한다
    assert (
        member_row(world, world.db.execute(text("SELECT MBR_SN FROM TB_MBR WHERE LGN_ID='w1'")).scalar())["n"]
        == "이름w1"
    )


def test_감사이력_환불계좌_문자기록은_실행할_수_없고_없는_번호는_404이다(world: World) -> None:
    operator(world)
    for item in (3, 4, 5):
        res = run(world, item, 1)
        assert res.status_code == 422 and res.json()["code"] == "RULE_REJECTED", item
    assert run(world, 99, 1).status_code == 404
    assert (
        call(
            world,
            "POST",
            "/retention/1/execute",
            {"expectedCount": 0},
            **{"Idempotency-Key": "retention-key-zero0"},
        ).status_code
        == 400
    )  # 건수는 1 이상이다


# --- 탈퇴 회원 비식별 ----------------------------------------------------------------------------


def test_30일이_지난_탈퇴_회원만_비식별하고_회원_번호는_그대로_둔다(world: World) -> None:
    old1, old2 = withdrawn(world, "old1", 60), withdrawn(world, "old2", 31)
    young, active = withdrawn(world, "young", 10), make_member(world, "active", MBL_TELNO="01099998888")
    done = make_member(
        world, "done", MBR_NM="탈퇴회원", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START - timedelta(days=90)
    )
    who = operator(world)
    res = run(world, 1, 2)
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["count"], out["state"]) == (0, "WAITING")  # 30일이 안 된 회원만 남았다
    assert out["executions"][0]["processed"] == 2 and out["canExecute"] is False
    for row in (old1, old2):
        got = member_row(world, row["MBR_SN"])
        assert (got["n"], got["p"], got["e"], got["s"].strip()) == ("탈퇴회원", None, None, "MS.WITHDRAW")
        assert got["l"] == f"withdrawn-{row['MBR_SN']}"
    assert member_row(world, young["MBR_SN"])["n"] == "이름young"
    assert member_row(world, active["MBR_SN"])["p"] == "01099998888"
    assert member_row(world, done["MBR_SN"])["l"] == "done"  # 이미 처리한 회원은 다시 건드리지 않는다
    job = (
        world.db.execute(
            text(
                "SELECT MNGR_SN m, TRGT_TBL_NM t, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='RETENTION_EXECUTE'"
            )
        )
        .mappings()
        .one()
    )
    assert (job["m"], job["t"], job["k"]) == (who.sn, "TB_MBR", "1") and job["c"].startswith("처리 2건")
    assert "이름old1" not in job["c"] and "01012345678" not in job["c"]  # 값은 작업이력에 남기지 않는다


def test_다른_묶음의_탈퇴_회원은_세지도_처리하지도_않는다(world: World) -> None:
    mine = withdrawn(world, "mine", 60)
    other = world.factory.make("TB_OPER_BNDL")
    foreign = withdrawn(world, "foreign", 60, OPER_BNDL_SN=other["OPER_BNDL_SN"])
    operator(world)
    assert run(world, 1, 1).status_code == 200
    assert member_row(world, mine["MBR_SN"])["n"] == "탈퇴회원"
    assert member_row(world, foreign["MBR_SN"])["n"] == "이름foreign"


def test_확인한_건수가_다르면_409이고_아무것도_바꾸지_않는다(world: World) -> None:
    row = withdrawn(world, "w1", 60)
    withdrawn(world, "w2", 60)
    operator(world)
    res = run(world, 1, 1)
    assert res.status_code == 409 and res.json()["code"] == "CONFLICT_STATE"
    world.db.commit()
    assert member_row(world, row["MBR_SN"])["n"] == "이름w1"
    assert (
        world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='RETENTION_EXECUTE'")).scalar()
        == 0
    )


def test_같은_키로_다시_보내면_이전_결과이고_내용이_다르면_충돌이며_새_키는_대상이_없어_409이다(
    world: World,
) -> None:
    withdrawn(world, "w1", 60)
    withdrawn(world, "w2", 60)
    operator(world)
    first = run(world, 1, 2, "retention-same-key")
    assert first.status_code == 200
    again = run(world, 1, 2, "retention-same-key")
    assert again.status_code == 200 and len(again.json()["executions"]) == 1  # 두 번 처리하지 않았다
    different = run(world, 1, 5, "retention-same-key")
    assert different.status_code == 409 and different.json()["code"] == "IDEMPOTENCY_CONFLICT"
    fresh = run(world, 1, 2, "retention-other-key")
    assert fresh.status_code == 409 and fresh.json()["code"] == "CONFLICT_STATE"  # 이미 처리해 대상이 0건이다


def test_같은_아이디가_이미_있으면_해시_아이디를_쓴다(world: World) -> None:
    row = withdrawn(world, "w1", 60)
    make_member(world, f"withdrawn-{row['MBR_SN']}", MBL_TELNO="01055556666")
    operator(world)
    assert run(world, 1, 1).status_code == 200
    login = member_row(world, row["MBR_SN"])["l"]
    assert login.startswith("w-") and len(login) == 20


# --- 인증번호 요청 삭제 --------------------------------------------------------------------------


def test_30일이_지난_인증번호_요청만_지우고_문자_기록이_가리키는_것은_남긴다(world: World) -> None:
    otp(world, 40)
    otp(world, 31)
    kept = otp(world, 5)
    pinned = otp(world, 90)
    sms = world.factory.make("TB_SMS_DMND", OPER_BNDL_SN=world.bundle, REG_DT=START - timedelta(days=90))
    world.factory.make(
        "TB_SMS_TRGT",
        OPER_BNDL_SN=world.bundle,
        SMS_DMND_SN=sms["SMS_DMND_SN"],
        CERT_DMND_SN=pinned["CERT_DMND_SN"],
        MBR_SN=None,  # 회원과 인증 요청 중 하나만 가리킨다(CK_SMS_03_ONE)
    )
    operator(world)
    listing = call(world, "GET", "/retention").json()["items"]
    assert [i["count"] for i in listing if i["target"] == "AUTH_RECORDS"] == [
        2
    ]  # 문자 기록이 가리키는 것은 세지 않는다
    res = run(world, 2, 2)
    assert res.status_code == 200, res.text
    remaining = {
        int(r)
        for r in world.db.execute(
            text("SELECT CERT_DMND_SN FROM TB_CERT_DMND WHERE OPER_BNDL_SN=:b"), {"b": world.bundle}
        ).scalars()
    }
    assert remaining == {int(kept["CERT_DMND_SN"]), int(pinned["CERT_DMND_SN"])}
    assert res.json()["executions"][0]["processed"] == 2
    assert run(world, 2, 2).status_code == 409


def test_상세의_실행_가능은_실행_권한과_대상이_있을_때만_true이다(world: World) -> None:
    withdrawn(world, "w1", 60)
    operator(world)
    assert call(world, "GET", "/retention/1").json()["canExecute"] is True
    assert call(world, "GET", "/retention/2").json()["canExecute"] is False  # 대상이 없다
    assert call(world, "GET", "/retention/3").json()["canExecute"] is False  # 검토만 한다
    operator(world, "AU.LOG_R")
    assert call(world, "GET", "/retention/1").json()["canExecute"] is False  # 실행 권한이 없다
