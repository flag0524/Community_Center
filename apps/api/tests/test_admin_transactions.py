# 관리자 결제·거래 대조(범위, 목록·상세, PG 재조회, 수동 대사)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.pg.base import ApproveOutcome, ApproveResult
from app.audit import record_job
from tests.test_admin_access import dong
from tests.test_admin_refunds import Actor, call, staff, use
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_applications_read import open_course as _open_course
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
_keys = itertools.count(1)
HASH = "a1b2c3d4" * 8


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def member(w: World, name: str = "홍길동") -> dict[str, Any]:
    return make_member(w, f"t{next(_keys)}", MBR_NM=name, **RESIDENT)


def pending(
    w: World, row: dict[str, Any] | None = None, state: str = "PS.PENDING", **values: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """결제 결과를 기다리는 결제대기 신청과 그 결제. (신청, 결제)"""
    row = row or course(w)
    app = application(w, member(w), row, "ES.HOLD")
    pay = payment(w, app, state, **{"STLM_AMT": 30000, "STLM_DMND_DT": START, **values})
    return app, pay


def approved(w: World, pay: dict[str, Any], **values: Any) -> ApproveResult:
    return ApproveResult(
        ApproveOutcome.APPROVED,
        transaction_id="tx-1",
        approval_no="A777",
        approved_at=START,
        order_no=pay["STLM_NO"],
        amount=int(pay["STLM_AMT"]),
        merchant_id=w.pg.merchant_id,
        currency="KRW",
        **values,
    )


def pay_row(w: World, pay: dict[str, Any]) -> Any:
    return (
        w.db.execute(text("SELECT * FROM TB_STLM WHERE STLM_SN=:s"), {"s": pay["STLM_SN"]}).mappings().one()
    )


def app_state(w: World, app: dict[str, Any]) -> str:
    return str(
        w.db.execute(
            text("SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a"), {"a": app["ATNLC_APLY_SN"]}
        ).scalar()
    )


def events(w: World, pay: dict[str, Any]) -> list[Any]:
    return list(
        w.db.execute(
            text("SELECT * FROM TB_STLM_EVENT WHERE STLM_SN=:s ORDER BY STLM_EVENT_SN"), {"s": pay["STLM_SN"]}
        )
        .mappings()
        .all()
    )


def jobs(w: World, pay: dict[str, Any], *codes: str) -> list[str]:
    rows = w.db.execute(
        text(
            "SELECT JOB_CD FROM TB_JOB_HSTRY WHERE TRGT_TBL_NM='TB_STLM' AND TRGT_KEY_VL=:k ORDER BY JOB_HSTRY_SN"
        ),
        {"k": str(pay["STLM_SN"])},
    )
    return [str(r[0]) for r in rows if not codes or r[0] in codes]


def recheck(w: World, pay: dict[str, Any]) -> Any:
    return call(w, "POST", f"/transactions/{pay['STLM_SN']}/recheck")


def reconcile(w: World, pay: dict[str, Any], outcome: str = "PAID", **body: Any) -> Any:
    sent = {
        "outcome": outcome,
        "approvalNo": "A999" if outcome == "PAID" else None,
        "evidence": "PG 관리자 화면에서 승인 확인",
        "version": int(pay_row(w, pay)["RCRD_VER"]),
        **body,
    }
    return call(w, "POST", f"/transactions/{pay['STLM_SN']}/manual-reconcile", sent)


def boss(w: World, *codes: str) -> Actor:
    who = staff(w, f"b{next(_keys)}", *(codes or ("AU.STLM_R", "AU.STLM_W")))
    use(w, who)
    return who


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_로그인하지_않으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/transactions").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R"))
    assert call(world, "GET", "/transactions").status_code == 403


def test_조회_권한만으로는_재조회와_수동_대사를_할_수_없다(world: World) -> None:
    _, pay = pending(world)
    boss(world, "AU.STLM_R")
    assert call(world, "GET", f"/transactions/{pay['STLM_SN']}").status_code == 200
    assert recheck(world, pay).status_code == 403
    assert reconcile(world, pay).status_code == 403
    assert world.pg.lookups == [] and pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING"


def test_동_담당자는_자기_동_강좌의_거래만_보고_다른_동은_404이다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    visible = pending(world, course(world, DONG_SN=mine["DONG_SN"]))[1]
    hidden = pending(world, course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))[1]
    common = pending(world, course(world, CORS_NM="공통"))[1]
    use(world, staff(world, "d1", "AU.STLM_R", "AU.STLM_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    ids = [i["transactionId"] for i in call(world, "GET", "/transactions").json()["items"]]
    assert ids == [str(visible["STLM_SN"])]
    for target in (hidden, common):
        assert call(world, "GET", f"/transactions/{target['STLM_SN']}").status_code == 404
        assert recheck(world, target).status_code == 404
        assert reconcile(world, target).status_code == 404
    assert world.pg.lookups == []


# --- 목록 ---------------------------------------------------------------------------------------


def test_결과_확인_중인_거래를_먼저_보이고_나머지는_최근_요청_순이다(world: World) -> None:
    done_old = pending(
        world, state="PS.PAID", STLM_DMND_DT=START - 3 * DAY, STLM_APRV_NO="A1", STLM_APRV_DT=START
    )[1]
    done_new = pending(
        world, state="PS.PAID", STLM_DMND_DT=START - 1 * DAY, STLM_APRV_NO="A2", STLM_APRV_DT=START
    )[1]
    wait_old = pending(world, STLM_DMND_DT=START - 5 * DAY)[1]
    boss(world)
    items = call(world, "GET", "/transactions").json()["items"]
    assert [i["transactionId"] for i in items] == [
        str(wait_old["STLM_SN"]),
        str(done_new["STLM_SN"]),
        str(done_old["STLM_SN"]),
    ]


def test_목록_항목은_금액과_수단과_상태와_재조회_횟수를_준다(world: World) -> None:
    app, pay = pending(world)
    for n in (1, 2):
        world.factory.make(
            "TB_STLM_EVENT", STLM_SN=pay["STLM_SN"], EVENT_TYPE_CD="ET.RECON", EVENT_ID=f"RECHECK:{n}"
        )
    world.factory.make("TB_STLM_EVENT", STLM_SN=pay["STLM_SN"], EVENT_TYPE_CD="ET.RECON", EVENT_ID="MANUAL:1")
    boss(world)
    [item] = call(world, "GET", "/transactions").json()["items"]
    assert item["orderNo"] == pay["STLM_NO"] and item["applicationNo"] == str(app["ATNLC_APLY_SN"])
    assert (item["amount"], item["status"], item["recheckCount"]) == (
        30000,
        "PENDING",
        2,
    )  # 수동 대사는 세지 않는다
    assert item["hasConflict"] is False and item["approvedAt"] is None


def test_검색과_거르기(world: World) -> None:
    a_app, a = pending(
        world, state="PS.PAID", STLM_DMND_DT=START - 10 * DAY, STLM_APRV_NO="A1", STLM_APRV_DT=START
    )
    b_app, b = pending(world, STLM_MNS_CD="PM.TRANSFER", STLM_DMND_DT=START)
    boss(world)

    def ids(query: str) -> list[str]:
        return [i["transactionId"] for i in call(world, "GET", f"/transactions?{query}").json()["items"]]

    sa, sb = str(a["STLM_SN"]), str(b["STLM_SN"])
    assert ids(f"q={a['STLM_NO']}") == [sa]
    assert ids(f"q={b_app['ATNLC_APLY_SN']}") == [sb]
    assert ids("q=%25") == []
    assert ids("status=PENDING") == [sb] and ids("status=PAID") == [sa]
    assert ids("method=TRANSFER") == [sb] and ids("method=CARD") == [sa]
    assert ids("from=2026-11-09") == [sb] and ids("to=2026-11-08") == [sa]
    assert a_app


def test_기간은_한국_날짜의_시작과_끝으로_가른다(world: World) -> None:
    # 한국 11월 9일 00:00 = UTC 11월 8일 15:00
    first_second = pending(world, STLM_DMND_DT=datetime(2026, 11, 8, 15, 0, 0))[1]
    last_second = pending(world, STLM_DMND_DT=datetime(2026, 11, 8, 14, 59, 59))[1]
    boss(world)

    def ids(query: str) -> list[str]:
        return [i["transactionId"] for i in call(world, "GET", f"/transactions?{query}").json()["items"]]

    assert ids("from=2026-11-09") == [str(first_second["STLM_SN"])]
    assert ids("to=2026-11-08") == [str(last_second["STLM_SN"])]


def test_충돌_통보가_있는_거래만_모아_볼_수_있다(world: World) -> None:
    _, conflicted = pending(world)
    pending(world)
    record_job(
        world.db,
        actor="AK.SYSTEM",
        job="PAY_WEBHOOK",
        table="TB_STLM",
        key=conflicted["STLM_SN"],
        request_id="r",
        now=START,
        bundle_sn=world.bundle,
        result="JR.DENY",
        change="충돌",
    )
    boss(world)
    items = call(world, "GET", "/transactions?conflictOnly=true").json()["items"]
    assert [(i["transactionId"], i["hasConflict"]) for i in items] == [(str(conflicted["STLM_SN"]), True)]
    assert call(world, "GET", "/transactions").json()["total"] == 2


def test_충돌_거래가_없으면_충돌만_보기는_빈_목록이다(world: World) -> None:
    pending(world)
    boss(world)
    assert call(world, "GET", "/transactions?conflictOnly=true").json()["items"] == []


# --- 상세 ---------------------------------------------------------------------------------------


def test_상세는_통보_이력과_조치와_연결_환불을_보인다(world: World) -> None:
    app, pay = pending(world)
    world.factory.make(
        "TB_STLM_EVENT",
        STLM_SN=pay["STLM_SN"],
        EVENT_TYPE_CD="ET.WEBHOOK",
        EVENT_ID="evt-1",
        EVENT_HASH_VL=HASH,
        PRCS_STTS_CD="EP.DONE",
        RCPTN_DT=START,
    )
    record_job(
        world.db,
        actor="AK.SYSTEM",
        job="PAY_WEBHOOK",
        table="TB_STLM",
        key=pay["STLM_SN"],
        request_id="r",
        now=START + timedelta(minutes=1),
        bundle_sn=world.bundle,
        result="JR.DENY",
        change="충돌",
    )
    world.factory.make("TB_RFND", STLM_SN=pay["STLM_SN"], RFND_AMT=1000, RFND_STTS_CD="RS.REQUEST")
    boss(world)
    body = call(world, "GET", f"/transactions/{pay['STLM_SN']}").json()
    assert body["merchantId"] == pay["FRCS_ID"] and body["courseName"] == "요가"
    assert body["applicantName"] == "홍*동" and body["recheckMax"] == 3
    assert body["applicationState"] == "PAYMENT_UNKNOWN"
    assert [(n["handling"], n["hashPrefix"]) for n in body["notices"]] == [
        ("DONE", "a1b2c3d4"),
        ("CONFLICT", ""),
    ]
    assert body["refund"]["status"] == "REQUESTED" and body["canRecheck"] and body["canReconcile"]
    assert body["version"] == 1 and body["actions"] == []
    assert app


def test_확인_중이_아니거나_쓰기_권한이_없으면_재조회_대사_가능이_거짓이다(world: World) -> None:
    _, done = pending(world, state="PS.PAID", STLM_APRV_NO="A1", STLM_APRV_DT=START)
    _, wait = pending(world)
    boss(world, "AU.STLM_R")
    assert call(world, "GET", f"/transactions/{wait['STLM_SN']}").json()["canRecheck"] is False
    boss(world)
    finished = call(world, "GET", f"/transactions/{done['STLM_SN']}").json()
    assert finished["canRecheck"] is False and finished["canReconcile"] is False
    assert call(world, "GET", f"/transactions/{wait['STLM_SN']}").json()["canReconcile"] is True


# --- PG 재조회 ----------------------------------------------------------------------------------


def test_재조회로_승인이_확인되면_결제완료와_수강확정이고_사건과_이력이_남는다(world: World) -> None:
    app, pay = pending(world)
    world.pg.lookup_results[pay["STLM_NO"]] = approved(world, pay)
    who = boss(world)
    r = recheck(world, pay)
    assert r.status_code == 200 and r.json()["status"] == "PAID" and r.json()["canRecheck"] is False
    row = pay_row(world, pay)
    assert row["STLM_APRV_NO"] == "A777" and app_state(world, app) == "ES.CONFIRM"
    [event] = events(world, pay)
    assert (event["EVENT_TYPE_CD"], event["EVENT_ID"], event["PRCS_STTS_CD"]) == (
        "ET.RECON",
        "RECHECK:1",
        "EP.DONE",
    )
    assert jobs(world, pay) == ["PAY_RECHECK"] and world.pg.lookups == [pay["STLM_NO"]]
    assert r.json()["actions"][0]["actor"] == "김관리" and r.json()["actions"][0]["kind"] == "RECHECK"
    assert who.sn


def test_재조회로_거절이_확인되면_결제실패이고_기한이_남았으면_신청은_결제대기로_둔다(world: World) -> None:
    app, pay = pending(world, STLM_DMND_DT=START)
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET STLM_DDLN_DT=:d WHERE ATNLC_APLY_SN=:a"),
        {"d": START + DAY, "a": app["ATNLC_APLY_SN"]},
    )
    world.pg.lookup_results[pay["STLM_NO"]] = ApproveResult(
        ApproveOutcome.REJECTED, failure_code="CARD_DECLINED"
    )
    boss(world)
    r = recheck(world, pay)
    assert r.json()["status"] == "FAILED" and app_state(world, app) == "ES.HOLD"


def test_재조회로_거절이_확인됐고_기한이_지났으면_신청을_만료시키고_자리를_돌려준다(world: World) -> None:
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261201")
    app, pay = pending(world, row)
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET STLM_DDLN_DT=:d WHERE ATNLC_APLY_SN=:a"),
        {"d": START - timedelta(minutes=1), "a": app["ATNLC_APLY_SN"]},
    )
    waiter = application(world, member(world), row, "ES.WAIT", WTNG_SEQ=1)
    world.pg.lookup_results[pay["STLM_NO"]] = ApproveResult(ApproveOutcome.REJECTED, failure_code="X")
    boss(world)
    assert recheck(world, pay).json()["status"] == "FAILED"
    assert app_state(world, app) == "ES.EXPIRE" and app_state(world, waiter) == "ES.HOLD"


def test_결과가_불명이면_그대로_두고_재조회_사건만_남긴다(world: World) -> None:
    app, pay = pending(world)
    boss(world)  # 모의 PG는 조회 결과가 없으면 불명이다
    r = recheck(world, pay)
    assert r.status_code == 200 and r.json()["status"] == "PENDING" and r.json()["canRecheck"] is True
    assert app_state(world, app) == "ES.HOLD" and pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING"
    [event] = events(world, pay)
    assert event["PRCS_STTS_CD"] == "EP.PROCESS" and event["EVENT_ID"] == "RECHECK:1"
    again = recheck(world, pay)
    assert [e["EVENT_ID"] for e in events(world, pay)] == ["RECHECK:1", "RECHECK:2"]
    assert again.json()["recheckCount"] == 2 and again.json()["lastRecheckAt"]


def test_PG를_부르는_동안에는_트랜잭션을_쥐지_않는다(world: World) -> None:
    _, pay = pending(world)
    seen: list[bool] = []
    original = world.pg.lookup

    def watch(**kwargs: Any) -> Any:
        seen.append(world.db.in_transaction())  # 요청의 세션 잠금(활동 시각 갱신)을 풀고 호출해야 한다
        return original(**kwargs)

    world.pg.lookup = watch  # type: ignore[method-assign]
    boss(world)
    assert recheck(world, pay).status_code == 200
    assert seen == [False]


def test_실패한_조치는_조치_이력에_보이지_않는다(world: World) -> None:
    _, pay = pending(world)
    record_job(
        world.db,
        actor="AK.ADMIN",
        job="PAY_RECHECK",
        table="TB_STLM",
        key=pay["STLM_SN"],
        request_id="r",
        now=START,
        bundle_sn=world.bundle,
        admin_sn=boss(world).sn,
        result="JR.FAIL",
        change="실패",
    )
    assert call(world, "GET", f"/transactions/{pay['STLM_SN']}").json()["actions"] == []


def test_조회가_실패해도_결과_불명으로_그대로_둔다(world: World) -> None:
    _, pay = pending(world)
    world.pg.lookup_raises = True
    boss(world)
    assert recheck(world, pay).json()["status"] == "PENDING"
    assert events(world, pay)[0]["PRCS_STTS_CD"] == "EP.PROCESS"


def test_금액이_다른_승인_응답은_확정하지_않고_대사_필요_사건으로_남긴다(world: World) -> None:
    app, pay = pending(world)
    world.pg.lookup_results[pay["STLM_NO"]] = approved(world, pay).__class__(
        ApproveOutcome.APPROVED,
        transaction_id="t",
        approval_no="A",
        approved_at=START,
        order_no=pay["STLM_NO"],
        amount=29000,
        merchant_id=world.pg.merchant_id,
        currency="KRW",
    )
    boss(world)
    r = recheck(world, pay)
    assert r.json()["status"] == "PENDING" and app_state(world, app) == "ES.HOLD"
    assert events(world, pay)[0]["PRCS_STTS_CD"] == "EP.FAIL" and "금액" in events(world, pay)[0]["FAIL_RSN"]


@pytest.mark.parametrize("state", ["PS.READY", "PS.PAID", "PS.FAIL", "PS.CANCEL"])
def test_결과_확인_중이_아니면_재조회할_수_없고_PG를_부르지_않는다(world: World, state: str) -> None:
    extra: dict[str, Any] = {"STLM_APRV_NO": "A1", "STLM_APRV_DT": START} if state == "PS.PAID" else {}
    _, pay = pending(world, state=state, **extra)
    boss(world)
    r = recheck(world, pay)
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert world.pg.lookups == [] and events(world, pay) == []


def test_조회하는_사이_다른_경로가_먼저_끝냈으면_다시_반영하지_않는다(world: World) -> None:
    app, pay = pending(world)
    world.pg.lookup_results[pay["STLM_NO"]] = approved(world, pay)
    original = world.pg.lookup

    def settled_elsewhere(**kwargs: Any) -> Any:
        world.db.execute(
            text(
                "UPDATE TB_STLM SET STLM_STTS_CD='PS.PAID', STLM_APRV_NO='B', STLM_APRV_DT=:t WHERE STLM_SN=:s"
            ),
            {"t": START, "s": pay["STLM_SN"]},
        )
        world.db.execute(
            text(
                "UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CONFIRM', SEAT_ALTMNT_DT=:t WHERE ATNLC_APLY_SN=:a"
            ),
            {"t": START, "a": app["ATNLC_APLY_SN"]},
        )
        return original(**kwargs)

    world.pg.lookup = settled_elsewhere  # type: ignore[method-assign]
    boss(world)
    r = recheck(world, pay)
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    assert events(world, pay) == [] and jobs(world, pay) == []  # 먼저 끝낸 쪽 결과를 따른다


# --- 수동 대사 ----------------------------------------------------------------------------------


def test_수동_대사로_성공을_입력하면_승인번호가_남고_수강확정이다(world: World) -> None:
    app, pay = pending(world)
    boss(world)
    r = reconcile(world, pay, evidence="PG 관리자 화면 거래내역에서 승인 확인")
    assert (
        r.status_code == 200
        and r.json()["status"] == "PAID"
        and r.json()["actions"][0]["kind"] == "MANUAL_RECONCILE"
    )
    row = pay_row(world, pay)
    assert (
        row["STLM_APRV_NO"] == "A999"
        and row["STLM_APRV_DT"] == START
        and app_state(world, app) == "ES.CONFIRM"
    )
    [event] = events(world, pay)
    assert event["EVENT_ID"] == "MANUAL:1" and event["PRCS_STTS_CD"] == "EP.DONE"
    assert "PG 관리자 화면 거래내역" in event["EVENT_CN"] and jobs(world, pay) == ["PAY_RECONCILE"]
    assert world.pg.lookups == []  # 수동 대사는 PG를 부르지 않는다
    assert r.json()["recheckCount"] == 0  # 재조회 횟수에 세지 않는다


def test_수동_대사로_실패를_입력하면_결제실패이고_기한이_지났으면_만료시킨다(world: World) -> None:
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261201")
    app, pay = pending(world, row)
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET STLM_DDLN_DT=:d WHERE ATNLC_APLY_SN=:a"),
        {"d": START - timedelta(minutes=1), "a": app["ATNLC_APLY_SN"]},
    )
    waiter = application(world, member(world), row, "ES.WAIT", WTNG_SEQ=1)
    boss(world)
    r = reconcile(world, pay, "FAILED")
    assert r.status_code == 200 and r.json()["status"] == "FAILED"
    assert pay_row(world, pay)["FAIL_CD"] == "MANUAL_RECONCILE"
    assert app_state(world, app) == "ES.EXPIRE" and app_state(world, waiter) == "ES.HOLD"


def test_성공_대사는_승인번호가_필수이고_근거는_5자_이상이어야_한다(world: World) -> None:
    app, pay = pending(world)
    boss(world)
    no_approval = reconcile(world, pay, approvalNo=None)
    assert no_approval.status_code == 422 and no_approval.json()["code"] == "RULE_REJECTED"
    blank = reconcile(world, pay, approvalNo="  ")
    assert blank.status_code == 422
    short = reconcile(world, pay, evidence="네")
    assert short.status_code == 400
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING" and events(world, pay) == []
    assert app_state(world, app) == "ES.HOLD"


def test_실패_대사는_승인번호_없이_할_수_있다(world: World) -> None:
    _, pay = pending(world)
    boss(world)
    assert reconcile(world, pay, "FAILED").status_code == 200


def test_읽은_버전과_다르면_409이고_바뀌지_않는다(world: World) -> None:
    _, pay = pending(world)
    boss(world)
    r = reconcile(world, pay, version=9)
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING" and events(world, pay) == []


@pytest.mark.parametrize("state", ["PS.READY", "PS.PAID", "PS.FAIL", "PS.CANCEL"])
def test_결과_확인_중이_아니면_수동_대사를_할_수_없다(world: World, state: str) -> None:
    extra: dict[str, Any] = {"STLM_APRV_NO": "A1", "STLM_APRV_DT": START} if state == "PS.PAID" else {}
    _, pay = pending(world, state=state, **extra)
    boss(world)
    r = reconcile(world, pay)
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert pay_row(world, pay)["STLM_STTS_CD"] == state


def test_이미_대사한_거래를_다시_대사하면_409다(world: World) -> None:
    _, pay = pending(world)
    boss(world)
    assert reconcile(world, pay).status_code == 200
    again = call(
        world,
        "POST",
        f"/transactions/{pay['STLM_SN']}/manual-reconcile",
        {
            "outcome": "FAILED",
            "evidence": "다시 입력해 본다",
            "version": int(pay_row(world, pay)["RCRD_VER"]),
        },
    )
    assert again.status_code == 409 and pay_row(world, pay)["STLM_STTS_CD"] == "PS.PAID"
