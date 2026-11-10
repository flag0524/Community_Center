# 결제 요청·승인 확인·영수증을 실제 앱, 모의 PG, MariaDB로 확인하는 시험(ADR-006, TDD 5.4)
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.pg.base import ApproveOutcome
from tests.test_applications_read import RESIDENT, application, open_course, sign_in
from tests.world import MEMBER, START, World, make_admin, make_member

pytestmark = pytest.mark.db

_keys = iter(range(1, 100_000))


def key() -> str:
    return f"pay-key-{next(_keys):08d}"


def csrf(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])


def request_pay(
    w: World, app: dict[str, Any], method: str = "CARD", idem: str | None = None, **headers: str
) -> Any:
    sent = {"X-CSRF-Token": csrf(w), "Idempotency-Key": idem or key(), **headers}
    return w.client.post(
        f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/payments", json={"method": method}, headers=sent
    )


def confirm(w: World, order_no: str, amount: int, payment_key: str = "pk-0001") -> Any:
    return w.client.post(
        f"{MEMBER}/payments/confirm",
        json={"orderNo": order_no, "paymentKey": payment_key, "amount": amount},
        headers={"X-CSRF-Token": csrf(w)},
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings().all())


def holding(w: World, **course_values: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """로그인한 회원의 결제대기 신청(수강료 30000원)과 그 신청."""
    me = sign_in(w, **RESIDENT)
    row = open_course(w, EDU_BGNG_YMD="20261201", EDU_END_YMD="20261231", **course_values)
    app = application(w, me, row, "ES.HOLD")
    w.db.commit()
    return row, app


def paid_flow(w: World, app: dict[str, Any]) -> tuple[Any, Any]:
    requested = request_pay(w, app)
    order = requested.json()
    return requested, confirm(w, order["orderNo"], order["amount"])


# --- 결제 요청 ----------------------------------------------------------------------------------


def test_결제를_요청하면_결제창_값과_신청의_기한을_준다(world: World) -> None:
    _, app = holding(world)
    response = request_pay(world, app, "TRANSFER")
    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 30000 and body["method"] == "TRANSFER" and body["gateway"] == "mock"
    assert body["deadline"].startswith("2026-11-09T09:10:00") and body["serverNow"].startswith(
        "2026-11-09T09:00:00"
    )
    assert len(body["orderNo"]) <= 20 and body["orderNo"].startswith("JR")
    assert body["gatewayParams"] == {"orderNo": body["orderNo"], "amount": "30000", "method": "TRANSFER"}
    saved = rows(world, "SELECT * FROM TB_STLM")[0]
    assert (
        saved["STLM_STTS_CD"] == "PS.READY"
        and saved["STLM_MNS_CD"] == "PM.TRANSFER"
        and saved["STLM_AMT"] == 30000
    )
    assert saved["PG_NM"] == "mock" and saved["FRCS_ID"] == "MOCK-MERCHANT" and saved["PG_DLNG_ID"] is None
    assert saved["STLM_EXPRY_DT"] == START + timedelta(minutes=10) and saved["STLM_NO"] == body["orderNo"]


def test_결제_금액은_신청에_저장한_값이고_요청에서_바꿀_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, EDU_BGNG_YMD="20261201")
    app = application(
        world,
        me,
        row,
        "ES.HOLD",
        TTCHG_AMT=100000,
        STLM_PRNMNT_AMT=70000,
        RDCT_AMT=30000,
        RDCT_RSN="감면",
        RDCT_MNGR_SN=make_admin(world, "reviewer")["MNGR_SN"],
    )
    world.db.commit()
    assert request_pay(world, app).json()["amount"] == 70000


def test_결제수단이_카드나_계좌이체가_아니면_400이다(world: World) -> None:
    _, app = holding(world)
    for method in ("VIRTUAL", "MANUAL", "cash"):
        assert request_pay(world, app, method).status_code == 400
    assert rows(world, "SELECT 1 FROM TB_STLM") == []


def test_같은_키로_다시_요청하면_이전_결과이고_기한은_늘어나지_않는다(world: World) -> None:
    _, app = holding(world)
    same = key()
    first = request_pay(world, app, idem=same).json()
    world.clock.advance(minutes=4)
    again = request_pay(world, app, idem=same)
    assert again.status_code == 201 and again.json()["orderNo"] == first["orderNo"]
    assert again.json()["deadline"] == first["deadline"]  # 재요청·시간 경과로 늘어나지 않는다(FN-036)
    assert len(rows(world, "SELECT 1 FROM TB_STLM")) == 1


def test_같은_키를_다른_수단이나_다른_신청에_쓰면_409다(world: World) -> None:
    row, app = holding(world)
    me = rows(world, "SELECT MBR_SN FROM TB_MBR WHERE LGN_ID = 'me'")[0]
    other = application(
        world,
        {"MBR_SN": me["MBR_SN"]},
        open_course(world, CORS_NM="다른 강좌", EDU_BGNG_YMD="20261201"),
        "ES.HOLD",
    )
    world.db.commit()
    same = key()
    assert request_pay(world, app, "CARD", same).status_code == 201
    for target, method in ((app, "TRANSFER"), (other, "CARD")):
        response = request_pay(world, target, method, same)
        assert response.status_code == 409 and response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_새로_요청하면_이전에_발급한_결제창은_쓸_수_없다(world: World) -> None:
    _, app = holding(world)
    first = request_pay(world, app).json()
    second = request_pay(world, app, "TRANSFER").json()
    status = {
        r["STLM_NO"]: r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_NO, STLM_STTS_CD FROM TB_STLM")
    }
    assert status[first["orderNo"]] == "PS.CANCEL" and status[second["orderNo"]] == "PS.READY"
    assert confirm(world, first["orderNo"], first["amount"]).json()["code"] == "PAY_NOT_PAYABLE"


@pytest.mark.parametrize("state", ["ES.WAIT", "ES.CONFIRM", "ES.CANCEL", "ES.COMPLETE"])
def test_결제대기가_아닌_신청은_결제할_수_없다(world: World, state: str) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), state, **({"WTNG_SEQ": 1} if state == "ES.WAIT" else {}))
    world.db.commit()
    response = request_pay(world, app)
    assert response.status_code == 422 and response.json()["code"] == "PAY_NOT_PAYABLE"
    assert rows(world, "SELECT 1 FROM TB_STLM") == []


def test_결제할_금액이_0원이면_결제할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD", TTCHG_AMT=0, STLM_PRNMNT_AMT=0)
    world.db.commit()
    assert request_pay(world, app).json()["code"] == "PAY_NOT_PAYABLE"


def test_결제_결과_확인_중에는_다시_요청할_수_없다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    world.pg.next_outcome = ApproveOutcome.UNKNOWN
    assert confirm(world, order["orderNo"], order["amount"]).json()["status"] == "PENDING"
    response = request_pay(world, app)
    assert response.status_code == 422 and response.json()["code"] == "PAY_RESULT_PENDING"


def test_기한이_지난_뒤_요청하면_만료시키고_자리를_돌려준다(world: World) -> None:
    row, app = holding(world, RCRT_NOPE=1, WTNG_NOPE=5)
    other = make_member(world, "next", MBL_TELNO="01012345678", **RESIDENT)
    waiting = application(world, other, row, "ES.WAIT", WTNG_SEQ=1)
    world.db.commit()
    world.clock.advance(minutes=10)  # 기한 정각은 이미 지났다
    response = request_pay(world, app)
    assert response.status_code == 422 and response.json()["code"] == "PAY_DEADLINE_EXPIRED"
    saved = rows(
        world,
        "SELECT APLY_STTS_CD, SEAT_ALTMNT_DT, STLM_DDLN_DT FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s",
        s=app["ATNLC_APLY_SN"],
    )[0]
    assert (
        saved["APLY_STTS_CD"] == "ES.EXPIRE" and saved["SEAT_ALTMNT_DT"] == START
    )  # 배정 시각을 지우지 않는다
    promoted = rows(
        world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s", s=waiting["ATNLC_APLY_SN"]
    )[0]
    assert promoted["APLY_STTS_CD"] == "ES.HOLD"  # 대기자가 바로 이어받는다
    assert request_pay(world, app).json()["code"] == "PAY_DEADLINE_EXPIRED"


def test_기한_1초_전까지는_요청할_수_있다(world: World) -> None:
    _, app = holding(world)
    world.clock.advance(minutes=9, seconds=59)
    assert request_pay(world, app).status_code == 201


def test_남의_신청_없는_신청은_404이고_형식이_틀리면_400이다(world: World) -> None:
    row, _ = holding(world)
    theirs = application(world, make_member(world, "stranger"), row, "ES.HOLD")
    world.db.commit()
    assert request_pay(world, theirs).status_code == 404
    assert request_pay(world, {"ATNLC_APLY_SN": 99999999}).status_code == 404
    assert (
        world.client.post(
            f"{MEMBER}/me/applications/abc/payments",
            json={"method": "CARD"},
            headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()},
        ).status_code
        == 400
    )


def test_결제_요청은_로그인과_CSRF_멱등키가_필요하다(world: World) -> None:
    _, app = holding(world)
    url = f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/payments"
    no_csrf = world.client.post(url, json={"method": "CARD"}, headers={"Idempotency-Key": key()})
    no_key = world.client.post(url, json={"method": "CARD"}, headers={"X-CSRF-Token": csrf(world)})
    assert no_csrf.status_code == 403 and no_key.status_code == 400
    world.client.cookies.clear()
    assert (
        world.client.post(
            url, json={"method": "CARD"}, headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()}
        ).status_code
        == 401
    )
    assert rows(world, "SELECT 1 FROM TB_STLM") == []


# --- 승인 확인 ----------------------------------------------------------------------------------


def test_승인되면_결제완료_수강확정이고_영수증을_받을_수_있다(world: World) -> None:
    _, app = holding(world)
    requested, response = paid_flow(world, app)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PAID" and body["applicationDisplayState"] == "CONFIRMED"
    assert body["paymentId"] == requested.json()["paymentId"] and body["applicationId"] == str(
        app["ATNLC_APLY_SN"]
    )
    assert [(c.order_no, c.payment_key, c.amount) for c in world.pg.calls] == [
        (requested.json()["orderNo"], "pk-0001", 30000)
    ]
    pay = rows(world, "SELECT * FROM TB_STLM")[0]
    assert (
        pay["STLM_STTS_CD"] == "PS.PAID"
        and pay["STLM_APRV_NO"] == "A0000001"
        and pay["PG_DLNG_ID"] == "pk-0001"  # 결제창이 준 paymentKey를 그대로 둔다
    )
    saved = rows(world, "SELECT APLY_STTS_CD, SEAT_ALTMNT_DT FROM TB_ATNLC_APLY")[0]
    assert saved["APLY_STTS_CD"] == "ES.CONFIRM" and saved["SEAT_ALTMNT_DT"] == START
    receipt = world.client.get(f"{MEMBER}/me/payments/{body['paymentId']}/receipt").json()
    assert (
        receipt["amount"] == 30000 and receipt["approvalNo"] == "A0000001" and receipt["courseName"] == "요가"
    )
    assert (
        receipt["method"] == "CARD"
        and receipt["payerName"] == "김회원"
        and receipt["applicationId"] == body["applicationId"]
    )


def test_승인_시각은_PG가_준_값을_쓰고_없으면_서버_시각이다(world: World) -> None:
    _, app = holding(world)
    world.pg.approved_at = START - timedelta(minutes=1)
    paid_flow(world, app)
    assert rows(world, "SELECT STLM_APRV_DT FROM TB_STLM")[0]["STLM_APRV_DT"] == START - timedelta(minutes=1)


def test_PG는_트랜잭션_밖에서_부르고_그_전에_결과_대기가_확정된다(world: World) -> None:
    _, app = holding(world)
    seen: dict[str, Any] = {}
    original = world.pg.approve

    def spy(**kwargs: Any) -> Any:
        seen["status"] = [r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_STTS_CD FROM TB_STLM")]
        return original(**kwargs)

    world.pg.approve = spy  # type: ignore[method-assign]
    paid_flow(world, app)
    assert seen["status"] == ["PS.PENDING"]  # 승인 요청 시점에는 이미 결과 대기 상태다


def test_금액이_다르면_PG를_부르지_않고_거절한다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    response = confirm(world, order["orderNo"], 1)
    assert response.status_code == 422 and response.json()["code"] == "PAY_AMOUNT_MISMATCH"
    assert (
        world.pg.calls == []
        and rows(world, "SELECT STLM_STTS_CD FROM TB_STLM")[0]["STLM_STTS_CD"] == "PS.READY"
    )


def test_거절되면_결제실패이고_기한_안에서는_다시_결제할_수_있다(world: World) -> None:
    _, app = holding(world)
    first = request_pay(world, app).json()
    world.pg.next_outcome = ApproveOutcome.REJECTED
    body = confirm(world, first["orderNo"], first["amount"]).json()
    assert body["status"] == "FAILED" and body["applicationDisplayState"] == "PAYMENT_FAILED"
    pay = rows(world, "SELECT STLM_STTS_CD, FAIL_CD FROM TB_STLM")[0]
    assert pay["STLM_STTS_CD"] == "PS.FAIL" and pay["FAIL_CD"] == "MOCK_REJECTED"
    assert rows(world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")[0]["APLY_STTS_CD"] == "ES.HOLD"
    retry = request_pay(world, app).json()
    assert confirm(world, retry["orderNo"], retry["amount"], "pk-0002").json()["status"] == "PAID"


def test_거절됐을_때_기한이_이미_지났으면_만료시키고_자리를_돌려준다(world: World) -> None:
    row, app = holding(world, RCRT_NOPE=1, WTNG_NOPE=5)
    waiting = application(
        world, make_member(world, "next", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    world.db.commit()
    order = request_pay(world, app).json()
    original = world.pg.approve

    def slow(**kwargs: Any) -> Any:
        world.clock.advance(minutes=11)  # PG가 응답하는 사이 기한이 지났다
        return original(**kwargs)

    world.pg.approve = slow  # type: ignore[method-assign]
    world.pg.next_outcome = ApproveOutcome.REJECTED
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert body["status"] == "FAILED" and body["applicationDisplayState"] == "EXPIRED"
    assert (
        rows(
            world,
            "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s",
            s=waiting["ATNLC_APLY_SN"],
        )[0]["APLY_STTS_CD"]
        == "ES.HOLD"
    )


def test_결과를_모르면_결과_확인_중으로_두고_자리를_지킨다(world: World) -> None:
    row, app = holding(world, RCRT_NOPE=1, WTNG_NOPE=5)
    waiting = application(
        world, make_member(world, "next", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    world.db.commit()
    order = request_pay(world, app).json()
    world.pg.next_outcome = ApproveOutcome.UNKNOWN
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert body["status"] == "PENDING" and body["applicationDisplayState"] == "PAYMENT_UNKNOWN"
    assert rows(world, "SELECT STLM_STTS_CD FROM TB_STLM")[0]["STLM_STTS_CD"] == "PS.PENDING"
    world.clock.advance(
        minutes=25
    )  # 기한(10분)이 한참 지나도 자리는 그대로다. 세션 유휴(30분)보다는 짧게 둔다
    assert (
        rows(
            world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s", s=app["ATNLC_APLY_SN"]
        )[0]["APLY_STTS_CD"]
        == "ES.HOLD"
    )
    assert (
        rows(
            world,
            "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s",
            s=waiting["ATNLC_APLY_SN"],
        )[0]["APLY_STTS_CD"]
        == "ES.WAIT"
    )
    again = confirm(world, order["orderNo"], order["amount"])
    assert again.status_code == 422 and again.json()["code"] == "PAY_RESULT_PENDING"
    assert len(world.pg.calls) == 1  # 확인 중에는 다시 승인 요청하지 않는다


def test_PG가_예외를_던져도_결과_확인_중으로_다룬다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    world.pg.raises = True
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert (
        body["status"] == "PENDING"
        and rows(world, "SELECT STLM_STTS_CD FROM TB_STLM")[0]["STLM_STTS_CD"] == "PS.PENDING"
    )


@pytest.mark.parametrize(
    "answer", [{"answer_amount": 1}, {"answer_order_no": "JR0000000000000000"}], ids=["금액", "주문번호"]
)
def test_승인_응답이_우리_값과_다르면_확정하지_않고_결과_확인_중으로_둔다(
    world: World, answer: dict[str, Any]
) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    for name, value in answer.items():
        setattr(world.pg, name, value)
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert body["status"] == "PENDING" and body["applicationDisplayState"] == "PAYMENT_UNKNOWN"
    assert rows(world, "SELECT STLM_STTS_CD, STLM_APRV_NO FROM TB_STLM")[0] == {
        "STLM_STTS_CD": "PS.PENDING",
        "STLM_APRV_NO": None,
    }
    assert rows(world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")[0]["APLY_STTS_CD"] == "ES.HOLD"
    event = rows(world, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.RESPONSE'")[0]
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "불일치" in event["FAIL_RSN"]


def test_결제가_끝난_주문을_다시_확인하면_같은_결과이고_PG를_또_부르지_않는다(world: World) -> None:
    _, app = holding(world)
    requested, first = paid_flow(world, app)
    order = requested.json()
    again = confirm(world, order["orderNo"], order["amount"])
    assert (
        again.status_code == 200
        and again.json()["status"] == "PAID"
        and again.json()["paymentId"] == first.json()["paymentId"]
    )
    assert len(world.pg.calls) == 1


def test_이미_실패한_주문은_다시_확인할_수_없다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    world.pg.next_outcome = ApproveOutcome.REJECTED
    confirm(world, order["orderNo"], order["amount"])
    again = confirm(world, order["orderNo"], order["amount"])
    assert again.status_code == 422 and again.json()["code"] == "PAY_NOT_PAYABLE" and len(world.pg.calls) == 1


def test_기한이_지난_뒤_승인_확인을_하면_PG를_부르지_않고_만료시킨다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    world.clock.advance(minutes=10)
    response = confirm(world, order["orderNo"], order["amount"])
    assert response.status_code == 422 and response.json()["code"] == "PAY_DEADLINE_EXPIRED"
    assert world.pg.calls == []
    assert rows(world, "SELECT STLM_STTS_CD FROM TB_STLM")[0]["STLM_STTS_CD"] == "PS.CANCEL"
    assert rows(world, "SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")[0]["APLY_STTS_CD"] == "ES.EXPIRE"


def test_취소된_신청의_주문은_승인할_수_없다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    world.client.post(
        f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/cancel", headers={"X-CSRF-Token": csrf(world)}
    )
    response = confirm(world, order["orderNo"], order["amount"])
    assert (
        response.status_code == 422 and response.json()["code"] == "PAY_NOT_PAYABLE" and world.pg.calls == []
    )


def test_같은_거래_아이디를_다른_결제에_쓰면_거절한다(world: World) -> None:
    row, app = holding(world)
    other_app = application(world, make_member(world, "other", **RESIDENT), row, "ES.HOLD")
    world.db.commit()
    first = request_pay(world, app).json()
    confirm(world, first["orderNo"], first["amount"], "shared-pk")
    other_login = sign_in_other(world)
    second = other_login(other_app)
    response = confirm(world, second["orderNo"], second["amount"], "shared-pk")
    assert response.status_code == 422 and response.json()["code"] == "PAY_NOT_PAYABLE"
    assert len(world.pg.calls) == 1


def sign_in_other(w: World) -> Any:
    from tests.world import login

    def go(app: dict[str, Any]) -> Any:
        w.client.cookies.clear()
        assert login(w, MEMBER, "other").status_code == 200
        return request_pay(w, app).json()

    return go


def test_남의_주문은_404이고_PG를_부르지_않는다(world: World) -> None:
    row, app = holding(world)
    order = request_pay(world, app).json()
    world.client.cookies.clear()
    make_member(world, "intruder", **RESIDENT)
    from tests.world import login

    assert login(world, MEMBER, "intruder").status_code == 200
    response = confirm(world, order["orderNo"], order["amount"])
    assert response.status_code == 404 and world.pg.calls == []
    assert confirm(world, "NOPE", 1).status_code == 404


def test_승인_확인은_로그인과_CSRF가_필요하다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    body = {"orderNo": order["orderNo"], "paymentKey": "pk-1", "amount": order["amount"]}
    assert world.client.post(f"{MEMBER}/payments/confirm", json=body).status_code == 403
    world.client.cookies.clear()
    assert (
        world.client.post(
            f"{MEMBER}/payments/confirm", json=body, headers={"X-CSRF-Token": csrf(world)}
        ).status_code
        == 401
    )
    assert world.pg.calls == []


@pytest.mark.parametrize(
    "bad", [{"orderNo": ""}, {"paymentKey": ""}, {"amount": -1}, {"amount": 1.5}, {"extra": 1}]
)
def test_승인_확인_요청의_형식이_틀리면_400이다(world: World, bad: dict[str, Any]) -> None:
    _, app = holding(world)
    body = {"orderNo": "JR1", "paymentKey": "pk", "amount": 1, **bad}
    response = world.client.post(
        f"{MEMBER}/payments/confirm", json=body, headers={"X-CSRF-Token": csrf(world)}
    )
    assert response.status_code == 400


def test_결제_사건과_감사가_남고_PG_원문은_남지_않는다(world: World) -> None:
    _, app = holding(world)
    paid_flow(world, app)
    events = rows(world, "SELECT * FROM TB_STLM_EVENT ORDER BY STLM_EVENT_SN")
    assert [(e["EVENT_TYPE_CD"], e["PRCS_STTS_CD"]) for e in events] == [
        ("ET.REQUEST", "EP.PROCESS"),
        ("ET.RESPONSE", "EP.DONE"),
    ]
    assert all(len(e["EVENT_HASH_VL"]) == 64 for e in events) and "pk-0001" not in " ".join(
        e["EVENT_CN"] for e in events
    )
    jobs = rows(
        world, "SELECT JOB_CD, ACTR_TYPE_CD FROM TB_JOB_HSTRY WHERE JOB_CD LIKE 'PAY_%' ORDER BY JOB_HSTRY_SN"
    )
    assert [(j["JOB_CD"], j["ACTR_TYPE_CD"]) for j in jobs] == [
        ("PAY_REQUEST", "AK.MEMBER"),
        ("PAY_CONFIRM", "AK.MEMBER"),
    ]


# --- 영수증 -------------------------------------------------------------------------------------


def test_결제가_끝나지_않은_결제나_남의_결제는_영수증이_404다(world: World) -> None:
    row, app = holding(world)
    ready = request_pay(world, app).json()
    assert world.client.get(f"{MEMBER}/me/payments/{ready['paymentId']}/receipt").status_code == 404
    other_app = application(world, make_member(world, "other", **RESIDENT), row, "ES.CONFIRM")
    other_pay = world.factory.make(
        "TB_STLM",
        ATNLC_APLY_SN=other_app["ATNLC_APLY_SN"],
        STLM_STTS_CD="PS.PAID",
        STLM_APRV_NO="A9",
        STLM_APRV_DT=START,
        STLM_MNS_CD="PM.CARD",
        STLM_AMT=100,
    )
    world.db.commit()
    assert world.client.get(f"{MEMBER}/me/payments/{other_pay['STLM_SN']}/receipt").status_code == 404
    assert world.client.get(f"{MEMBER}/me/payments/99999999/receipt").status_code == 404
    assert world.client.get(f"{MEMBER}/me/payments/abc/receipt").status_code == 400


def test_영수증은_로그인이_필요하다(world: World) -> None:
    assert world.client.get(f"{MEMBER}/me/payments/1/receipt").status_code == 401


# --- 보강: 경계와 기록 --------------------------------------------------------------------------


def test_다른_운영묶음이_같은_멱등키를_썼어도_충돌이_아니다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs_cycle = world.factory.make(
        "TB_EDU_CYCL",
        OPER_BNDL_SN=other,
        EDU_YR="2026",
        EDU_CYCL=9,
        EDU_CYCL_NM="남",
        EDU_BGNG_YMD="20261101",
        EDU_END_YMD="20261231",
        RCPT_BGNG_DT=START - timedelta(days=1),
        RCPT_END_DT=START + timedelta(days=1),
    )
    from tests.test_courses_public import course

    theirs_course = course(world, theirs_cycle, "남의", OPER_BNDL_SN=other)
    stranger = make_member(world, "stranger", OPER_BNDL_SN=other)
    theirs_app = application(world, stranger, theirs_course, "ES.HOLD", OPER_BNDL_SN=other)
    world.factory.make(
        "TB_STLM",
        OPER_BNDL_SN=other,
        ATNLC_APLY_SN=theirs_app["ATNLC_APLY_SN"],
        STLM_MNS_CD="PM.CARD",
        STLM_AMT=100,
        IDEM_KEY="shared-pay-0009",
    )
    _, app = holding(world)
    assert request_pay(world, app, idem="shared-pay-0009").status_code == 201


def test_PG가_응답하는_사이_다른_경로가_결제를_끝냈으면_그_결과를_덮어쓰지_않는다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    original = world.pg.approve

    def settled_elsewhere(**kwargs: Any) -> Any:
        # 통보나 대사가 먼저 결제를 끝낸 상황을 흉내 낸다
        world.db.execute(
            text("UPDATE TB_STLM SET STLM_STTS_CD='PS.PAID', STLM_APRV_NO='ELSEWHERE', STLM_APRV_DT=:n"),
            {"n": START},
        )
        world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CONFIRM'"))
        world.db.commit()
        return original(**kwargs)

    world.pg.approve = settled_elsewhere  # type: ignore[method-assign]
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert body["status"] == "PAID"
    saved = rows(world, "SELECT STLM_APRV_NO FROM TB_STLM")[0]
    assert saved["STLM_APRV_NO"] == "ELSEWHERE"  # 먼저 끝낸 쪽의 승인 번호가 남는다
    assert len(rows(world, "SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.RESPONSE'")) == 0


@pytest.mark.parametrize(
    ("advance", "display"), [({"minutes": 9, "seconds": 59}, "PAYMENT_FAILED"), ({"minutes": 10}, "EXPIRED")]
)
def test_거절_응답_시점이_기한_정각이면_만료이고_1초_전이면_다시_결제할_수_있다(
    world: World, advance: dict[str, int], display: str
) -> None:
    _, app = holding(world)
    order = request_pay(world, app).json()
    original = world.pg.approve

    def slow(**kwargs: Any) -> Any:
        world.clock.advance(**advance)
        return original(**kwargs)

    world.pg.approve = slow  # type: ignore[method-assign]
    world.pg.next_outcome = ApproveOutcome.REJECTED
    body = confirm(world, order["orderNo"], order["amount"]).json()
    assert body["applicationDisplayState"] == display


def test_결제_사건은_내용의_해시를_담고_처리일시는_끝난_사건에만_있다(world: World) -> None:
    import hashlib

    _, app = holding(world)
    paid_flow(world, app)
    events = rows(world, "SELECT * FROM TB_STLM_EVENT ORDER BY STLM_EVENT_SN")
    for event in events:
        assert event["EVENT_HASH_VL"] == hashlib.sha256(event["EVENT_CN"].encode()).hexdigest()
    request_event, response_event = events
    assert request_event["PRCS_DT"] is None  # 처리 중인 사건은 아직 끝나지 않았다
    assert response_event["PRCS_DT"] == START and response_event["RCPTN_DT"] == START


def test_계좌이체로_낸_결제의_영수증은_계좌이체다(world: World) -> None:
    _, app = holding(world)
    order = request_pay(world, app, "TRANSFER").json()
    paid = confirm(world, order["orderNo"], order["amount"]).json()
    assert (
        world.client.get(f"{MEMBER}/me/payments/{paid['paymentId']}/receipt").json()["method"] == "TRANSFER"
    )
