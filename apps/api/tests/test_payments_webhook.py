# PG 통보(웹훅) 수신의 서명 검증, 멱등 저장, 충돌 격리, 거래 조회 기반 반영을 확인하는 시험(TDD 5.4.2, ADR-009·040)
import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.pg.base import CURRENCY, ApproveOutcome, ApproveResult
from tests.test_applications_read import RESIDENT, application
from tests.test_payments_flow import confirm, csrf, holding, request_pay, rows
from tests.world import MEMBER, START, World, make_member

pytestmark = pytest.mark.db

URL = "/api/pg/webhook/mock"


def approved(ours: str, **answer: Any) -> ApproveResult:
    """우리 주문(ours)을 승인했다는 조회 결과. answer로 공급자가 알려 주는 값을 일부러 어긋나게 만든다."""
    defaults: dict[str, Any] = {
        "outcome": ApproveOutcome.APPROVED,
        "transaction_id": "tx-hook-1",
        "approval_no": "H0000001",
        "order_no": ours,
        "amount": 30000,
        "merchant_id": "MOCK-MERCHANT",
        "currency": CURRENCY,
    }
    return ApproveResult(**{**defaults, **answer})


def send(w: World, order_no: str, event_id: str = "evt-1", **extra: Any) -> Any:
    body = json.dumps({"eventId": event_id, "orderNo": order_no, **extra}, sort_keys=True).encode()
    return w.client.post(
        URL, content=body, headers={"x-mock-signature": w.pg.sign(body), "content-type": "application/json"}
    )


def issue(w: World) -> tuple[dict[str, Any], dict[str, Any]]:
    _, app = holding(w)
    return app, request_pay(w, app).json()


def pay_state(w: World) -> str:
    return str(rows(w, "SELECT STLM_STTS_CD FROM TB_STLM")[0]["STLM_STTS_CD"])


def app_state(w: World) -> str:
    return str(rows(w, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")[0]["APLY_STTS_CD"])


# --- 서명과 저장 --------------------------------------------------------------------------------


def test_서명이_틀리면_401이고_아무것도_저장하지_않으며_거래를_조회하지도_않는다(world: World) -> None:
    _, order = issue(world)
    body = json.dumps({"eventId": "e", "orderNo": order["orderNo"]}).encode()
    for headers in ({}, {"x-mock-signature": "0" * 64}, {"x-mock-signature": world.pg.sign(body + b" ")}):
        response = world.client.post(URL, content=body, headers=headers)
        assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"
    assert rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'") == []
    assert world.pg.lookups == [] and pay_state(world) == "PS.READY"


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"eventId": "e"}', b'{"orderNo": "x"}'])
def test_서명은_맞아도_형식을_읽을_수_없으면_401이다(world: World, body: bytes) -> None:
    response = world.client.post(URL, content=body, headers={"x-mock-signature": world.pg.sign(body)})
    assert response.status_code == 401 and world.pg.lookups == []


def test_이_배포가_쓰지_않는_대행사_경로는_404다(world: World) -> None:
    body = b"{}"
    response = world.client.post(
        "/api/pg/webhook/toss", content=body, headers={"x-mock-signature": world.pg.sign(body)}
    )
    assert response.status_code == 404


def test_웹훅은_프런트_계약에_들어가지_않는다(world: World) -> None:
    spec = world.client.app.openapi()  # type: ignore[attr-defined]
    assert not any(path.startswith("/api/pg") for path in spec["paths"])


def test_우리_주문이_아니면_격리하고_저장하지_않는다(world: World) -> None:
    issue(world)
    response = send(world, "JR-UNKNOWN-0001")
    assert response.status_code == 200 and response.json() == {"result": "unidentified"}
    assert (
        rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'") == []
        and world.pg.lookups == []
    )


# --- 거래 조회 기반 반영 ------------------------------------------------------------------------


def test_통보를_받으면_사건을_저장하고_거래를_다시_조회해_결제대기_결제를_확정한다(world: World) -> None:
    app, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    response = send(world, order["orderNo"], "evt-1")
    assert response.status_code == 200 and response.json() == {"result": "processed"}
    assert world.pg.lookups == [order["orderNo"]]
    assert pay_state(world) == "PS.PAID" and app_state(world) == "ES.CONFIRM"
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.DONE" and event["EVENT_ID"] == "evt-1" and event["PRCS_DT"] == START
    assert event["RCPTN_DT"] == START and event["RTRY_NMTM"] == 0 and len(event["EVENT_HASH_VL"]) == 64
    paid = rows(world, "SELECT STLM_APRV_NO, PG_DLNG_ID FROM TB_STLM")[0]
    assert (
        paid["STLM_APRV_NO"] == "H0000001" and paid["PG_DLNG_ID"] is None
    )  # 확인 요청 없이 끝났으니 paymentKey가 없다


def test_통보한_내용이_아니라_조회한_결과로_판단한다(world: World) -> None:
    _, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = ApproveResult(ApproveOutcome.REJECTED, failure_code="X")
    response = send(world, order["orderNo"], "evt-1", status="DONE", amount=30000)  # 통보는 승인이라 주장한다
    assert response.json() == {"result": "processed"}
    assert pay_state(world) == "PS.FAIL" and app_state(world) == "ES.HOLD"  # 기한이 남아 다시 결제할 수 있다


def test_결과_확인_중인_결제도_통보로_확정된다(world: World) -> None:
    app, order = issue(world)
    world.pg.next_outcome = ApproveOutcome.UNKNOWN
    assert confirm(world, order["orderNo"], order["amount"]).json()["status"] == "PENDING"
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    assert pay_state(world) == "PS.PAID" and app_state(world) == "ES.CONFIRM"


def test_결제창만_발급됐고_신청이_기한_안이면_금액이_맞을_때_확정한다(world: World) -> None:
    _, order = issue(world)  # 회원이 승인 확인 요청을 보내지 않은 채 PG에서 승인됐다
    assert pay_state(world) == "PS.READY"
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    assert pay_state(world) == "PS.PAID" and app_state(world) == "ES.CONFIRM"


@pytest.mark.parametrize(
    "answer",
    [{"amount": 1}, {"order_no": "JR-OTHER"}, {"merchant_id": "OTHER-SHOP"}, {"currency": "USD"}],
    ids=["금액", "주문번호", "가맹점", "통화"],
)
def test_조회_결과가_우리_값과_다르면_확정하지_않고_대사로_올린다(
    world: World, answer: dict[str, Any]
) -> None:
    _, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"], **answer)
    response = send(world, order["orderNo"])
    assert response.status_code == 200
    assert pay_state(world) == "PS.READY" and app_state(world) == "ES.HOLD"
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "불일치" in event["FAIL_RSN"]


@pytest.mark.parametrize("closed", ["ES.EXPIRE", "ES.CANCEL"])
def test_이미_만료_취소된_신청에_승인_통보가_오면_확정하지_않고_보상환불_대상으로_남긴다(
    world: World, closed: str
) -> None:
    row, app = holding(world, RCRT_NOPE=1, WTNG_NOPE=5)
    waiting = application(
        world, make_member(world, "next", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    order = request_pay(world, app).json()
    if closed == "ES.CANCEL":  # 회원이 결제창을 연 채 신청을 취소했다
        cancel = f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/cancel"
        assert world.client.post(cancel, headers={"X-CSRF-Token": csrf(world)}).status_code == 200
    else:  # 기한이 지난 뒤 다시 결제를 시도해 신청이 만료됐다
        world.clock.advance(minutes=10)
        assert request_pay(world, app).json()["code"] == "PAY_DEADLINE_EXPIRED"
    assert (
        rows(
            world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :a", a=app["ATNLC_APLY_SN"]
        )[0]["APLY_STTS_CD"]
        == closed
    )
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    assert pay_state(world) == "PS.CANCEL"  # 닫힌 결제를 되살리지 않는다
    assert (
        rows(
            world,
            "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :a",
            a=waiting["ATNLC_APLY_SN"],
        )[0]["APLY_STTS_CD"]
        == "ES.HOLD"
    )  # 이어받은 사람의 자리를 빼앗지 않는다
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "보상환불" in event["FAIL_RSN"]


def test_거래_조회가_실패하면_재시도_대상으로_남기고_업무는_바꾸지_않는다(world: World) -> None:
    _, order = issue(world)
    world.pg.lookup_raises = True
    response = send(world, order["orderNo"])
    assert response.status_code == 200 and response.json() == {"result": "retry"}
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and event["RTRY_NMTM"] == 1
    assert pay_state(world) == "PS.READY" and app_state(world) == "ES.HOLD"


def test_조회_결과가_불명이어도_재시도_대상이다(world: World) -> None:
    _, order = issue(world)  # 모의 PG는 조회 결과가 없으면 결과 불명을 돌려준다
    assert send(world, order["orderNo"]).json() == {"result": "retry"}
    assert pay_state(world) == "PS.READY"


def test_거절_통보로_결제실패가_되고_기한이_지났으면_신청을_만료시킨다(world: World) -> None:
    row, app = holding(world, RCRT_NOPE=1, WTNG_NOPE=5)
    waiting = application(
        world, make_member(world, "next", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    order = request_pay(world, app).json()
    world.clock.advance(minutes=10)
    world.pg.lookup_results[order["orderNo"]] = ApproveResult(ApproveOutcome.REJECTED)
    send(world, order["orderNo"])
    assert pay_state(world) == "PS.FAIL"
    assert (
        rows(
            world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :a", a=app["ATNLC_APLY_SN"]
        )[0]["APLY_STTS_CD"]
        == "ES.EXPIRE"
    )
    assert (
        rows(
            world,
            "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :a",
            a=waiting["ATNLC_APLY_SN"],
        )[0]["APLY_STTS_CD"]
        == "ES.HOLD"
    )


# --- 멱등과 충돌 --------------------------------------------------------------------------------


def test_같은_통보를_다시_받으면_업무를_다시_바꾸지_않고_조회도_하지_않는다(world: World) -> None:
    _, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    first = send(world, order["orderNo"], "evt-1")
    again = send(world, order["orderNo"], "evt-1")
    assert (
        first.json() == {"result": "processed"}
        and again.status_code == 200
        and again.json() == {"result": "duplicate"}
    )
    assert world.pg.lookups == [order["orderNo"]]  # 두 번째는 조회하지 않는다
    assert len(rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")) == 1
    assert len(rows(world, "SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'PAY_WEBHOOK'")) == 1


def test_같은_사건_번호에_다른_내용이_오면_충돌로_격리하고_업무를_바꾸지_않는다(world: World) -> None:
    _, order = issue(world)
    send(world, order["orderNo"], "evt-1", status="READY")
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    conflict = send(world, order["orderNo"], "evt-1", status="DONE")  # 같은 번호, 다른 내용
    assert conflict.status_code == 200 and conflict.json() == {"result": "conflict"}
    assert pay_state(world) == "PS.READY"  # 두 번째 내용으로는 결제를 확정하지 않는다
    events = rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")
    assert len(events) == 1
    deny = rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD = 'PAY_WEBHOOK' AND JOB_RSLT_CD = 'JR.DENY'")
    assert len(deny) == 1 and deny[0]["ACTR_TYPE_CD"] == "AK.SYSTEM" and deny[0]["MBR_SN"] is None


def test_사건_번호가_다르면_같은_주문의_통보도_따로_처리한다(world: World) -> None:
    _, order = issue(world)
    send(world, order["orderNo"], "evt-1")
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    second = send(world, order["orderNo"], "evt-2")
    assert second.json() == {"result": "processed"} and pay_state(world) == "PS.PAID"
    assert len(rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")) == 2


def test_이미_결제완료인_주문의_통보는_결제를_다시_바꾸지_않는다(world: World) -> None:
    _, order = issue(world)
    confirm(world, order["orderNo"], order["amount"])
    before = rows(world, "SELECT STLM_APRV_NO, RCRD_VER FROM TB_STLM")[0]
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"], approval_no="CHANGED")
    send(world, order["orderNo"])
    assert rows(world, "SELECT STLM_APRV_NO, RCRD_VER FROM TB_STLM")[0] == before


def test_사건_기록에는_통보_원문을_복사하지_않는다(world: World) -> None:
    _, order = issue(world)
    send(world, order["orderNo"], "evt-1", cardNumber="1234-5678", secret="SHOULD-NOT-BE-STORED")
    stored = rows(world, "SELECT EVENT_CN FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0][
        "EVENT_CN"
    ]
    assert "1234-5678" not in stored and "SHOULD-NOT-BE-STORED" not in stored
    assert json.loads(stored) == {"eventId": "evt-1", "orderNo": order["orderNo"]}


def test_통보_처리는_시스템_작업으로_작업이력에_남고_회원은_비어_있다(world: World) -> None:
    _, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    log = rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD = 'PAY_WEBHOOK'")
    assert len(log) == 1 and log[0]["ACTR_TYPE_CD"] == "AK.SYSTEM" and log[0]["MBR_SN"] is None
    assert log[0]["TRGT_TBL_NM"] == "TB_STLM" and log[0]["JOB_RSLT_CD"] == "JR.SUCCESS"


def test_로그인이_없어도_서명만_맞으면_받는다(world: World) -> None:
    _, order = issue(world)
    world.client.cookies.clear()
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    assert send(world, order["orderNo"]).status_code == 200


# --- 보강: 닫힌 결제, 다른 묶음, 저장 시점, 보안 로그 ------------------------------------------------


def test_닫힌_결제에_승인_통보가_와도_신청이_유효하다고_결제를_되살리지_않는다(world: World) -> None:
    app, first = issue(world)
    second = request_pay(world, app, "TRANSFER").json()  # 새로 요청하면 첫 결제창은 취소된다
    assert {
        r["STLM_NO"]: r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_NO, STLM_STTS_CD FROM TB_STLM")
    }[first["orderNo"]] == "PS.CANCEL"
    world.pg.lookup_results[first["orderNo"]] = approved(first["orderNo"])
    send(world, first["orderNo"])
    status = {
        r["STLM_NO"]: r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_NO, STLM_STTS_CD FROM TB_STLM")
    }
    assert (
        status == {first["orderNo"]: "PS.CANCEL", second["orderNo"]: "PS.READY"}
        and app_state(world) == "ES.HOLD"
    )
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "보상환불" in event["FAIL_RSN"]


def test_이미_결제완료인_주문의_통보는_완료_사건으로_남는다(world: World) -> None:
    _, order = issue(world)
    confirm(world, order["orderNo"], order["amount"])
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.DONE" and event["FAIL_RSN"] is None  # 대사할 일이 없다


def test_신청이_유효하지_않은데_결제가_열려_있으면_승인_통보로_확정하지_않는다(world: World) -> None:
    _, order = issue(world)
    world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD = 'ES.CANCEL', RTRCN_DT = :n"), {"n": START})
    world.db.commit()  # 실제 흐름으로는 닫힌 신청의 결제도 닫히지만, 어긋난 데이터에도 확정하지 않는다
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    send(world, order["orderNo"])
    assert pay_state(world) == "PS.READY" and app_state(world) == "ES.CANCEL"
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "보상환불" in event["FAIL_RSN"]


def test_거절_통보가_와도_유효하지_않은_신청을_다시_만료시키지_않는다(world: World) -> None:
    _, order = issue(world)
    world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD = 'ES.CANCEL', RTRCN_DT = :n"), {"n": START})
    world.db.commit()
    world.clock.advance(minutes=11)  # 기한도 지났다
    world.pg.lookup_results[order["orderNo"]] = ApproveResult(ApproveOutcome.REJECTED)
    send(world, order["orderNo"])
    assert app_state(world) == "ES.CANCEL"  # 취소를 만료로 바꾸지 않는다


def test_다른_운영묶음의_결제와_주문번호가_같아도_우리_묶음의_결제만_다룬다(world: World) -> None:
    from tests.test_courses_public import course

    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    their_cycle = world.factory.make(
        "TB_EDU_CYCL", OPER_BNDL_SN=other, EDU_YR="2026", EDU_CYCL=9, EDU_CYCL_NM="남",
        EDU_BGNG_YMD="20261101", EDU_END_YMD="20261231",
        RCPT_BGNG_DT=START - timedelta(days=1), RCPT_END_DT=START + timedelta(days=1),
    )  # fmt: skip
    their_app = application(
        world,
        make_member(world, "stranger", OPER_BNDL_SN=other),
        course(world, their_cycle, "남의", OPER_BNDL_SN=other),
        "ES.HOLD",
        OPER_BNDL_SN=other,
    )
    theirs = world.factory.make(  # 다른 묶음의 결제를 먼저 만들어 번호가 더 앞서게 한다
        "TB_STLM", OPER_BNDL_SN=other, ATNLC_APLY_SN=their_app["ATNLC_APLY_SN"], STLM_NO="SAME-ORDER-1",
        STLM_MNS_CD="PM.CARD", STLM_AMT=100,
    )  # fmt: skip
    _, order = issue(world)
    world.db.execute(
        text("UPDATE TB_STLM SET STLM_NO = 'SAME-ORDER-1' WHERE STLM_SN <> :t"), {"t": theirs["STLM_SN"]}
    )
    world.db.commit()
    world.pg.lookup_results["SAME-ORDER-1"] = approved("SAME-ORDER-1")
    send(world, "SAME-ORDER-1")
    status = {
        r["STLM_SN"]: r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_SN, STLM_STTS_CD FROM TB_STLM")
    }
    assert status.pop(theirs["STLM_SN"]) == "PS.READY" and list(status.values()) == [
        "PS.PAID"
    ]  # 우리 것만 확정됐다
    assert order["orderNo"] != "SAME-ORDER-1"


def test_거래_조회_시점에는_받은_사건이_수신_상태로_저장되어_있다(world: World) -> None:
    _, order = issue(world)
    seen: list[str] = []
    original = world.pg.lookup

    def spy(*, order_no: str) -> ApproveResult:
        seen.extend(
            r["PRCS_STTS_CD"]
            for r in rows(world, "SELECT PRCS_STTS_CD FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")
        )
        return original(order_no=order_no)

    world.pg.lookup = spy  # type: ignore[method-assign]
    send(world, order["orderNo"])
    assert seen == ["EP.RECEIVED"]  # PG를 부르기 전에 받은 사건을 먼저 남긴다


def test_서명_실패_충돌_격리는_보안_로그에_남고_본문은_남지_않는다(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    _, order = issue(world)
    with caplog.at_level("WARNING", logger="app.security"):
        world.client.post(URL, content=b'{"secret": "LEAK-ME"}', headers={"x-mock-signature": "0" * 64})
        send(world, "JR-UNKNOWN-0002")
        send(world, order["orderNo"], "evt-1", status="A")
        send(world, order["orderNo"], "evt-1", status="B")
    messages = [r.getMessage() for r in caplog.records if r.name == "app.security"]
    assert (
        any("서명" in m for m in messages)
        and any("격리" in m for m in messages)
        and any("충돌" in m for m in messages)
    )
    assert not any("LEAK-ME" in m or order["orderNo"] in m for m in messages)
