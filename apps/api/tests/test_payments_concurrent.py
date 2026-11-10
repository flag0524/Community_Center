# 결제 요청·승인 확인의 동시성을 서로 다른 DB 연결로 확인하는 시험(승인 한 번, 결과 대기 중 자리 보존, ADR-006·040)
import json
import threading
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.pg.base import ApproveOutcome, ApproveResult
from app.adapters.pg.mock import MockPaymentGateway
from tests.arena import (
    Applicant,
    Arena,
    make_application,
    make_course,
    make_cycle,
    make_member,
    outcome,
    parallel,
)
from tests.factory import RowFactory

pytestmark = pytest.mark.db


def request_call(who: Applicant, application_sn: int, idem: str, method: str = "CARD") -> Callable[[], Any]:
    return lambda: who.client.post(
        f"/api/v1/me/applications/{application_sn}/payments",
        json={"method": method},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": idem},
    )


def confirm_call(who: Applicant, order_no: str, amount: int, payment_key: str) -> Callable[[], Any]:
    return lambda: who.client.post(
        "/api/v1/payments/confirm",
        json={"orderNo": order_no, "paymentKey": payment_key, "amount": amount},
        headers={"X-CSRF-Token": who.csrf},
    )


def cancel_call(who: Applicant, application_sn: int) -> Callable[[], Any]:
    return lambda: who.client.post(
        f"/api/v1/me/applications/{application_sn}/cancel", headers={"X-CSRF-Token": who.csrf}
    )


def one_holder(f: RowFactory) -> tuple[int, int, dict[str, Any], int]:
    bundle = f.bundle()
    course = make_course(f, bundle, make_cycle(f, bundle), "강좌", RCRT_NOPE=3, EDU_BGNG_YMD="20261201")
    member = make_member(f, bundle, "payer")
    return bundle, member, course, make_application(f, bundle, member, course, "ES.HOLD")


def test_같은_주문을_여러_기기에서_동시에_확인해도_PG_승인은_한_번이다(arena: Arena) -> None:
    bundle, member, _, application_sn = arena.build(one_holder)
    arena.serve(bundle)
    arena.pg.delay_seconds = 0.2  # 응답이 늦어 다른 요청이 그 사이에 들어온다
    first = arena.applicant(member, bundle)
    order = request_call(first, application_sn, "pay-concurrent-0001")().json()
    devices = [arena.applicant(member, bundle) for _ in range(8)]
    responses = parallel(
        [confirm_call(d, order["orderNo"], order["amount"], "pk-shared-0001") for d in devices]
    )
    assert len(arena.pg.calls) == 1  # 승인 요청 전에 결과 대기를 확정하므로 두 번째부터는 막힌다
    answers = [("PAID" if r.status_code == 200 else r.json()["code"]) for r in responses]
    assert set(answers) <= {"PAID", "PAY_RESULT_PENDING"}, (
        answers
    )  # 먼저 온 하나가 승인받고 나머지는 대기 안내
    assert answers.count("PAID") >= 1
    paid = arena.query("SELECT STLM_STTS_CD FROM TB_STLM")
    assert [p["STLM_STTS_CD"] for p in paid] == ["PS.PAID"]
    assert arena.query("SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")[0]["APLY_STTS_CD"] == "ES.CONFIRM"


def test_승인_확인과_취소가_겹쳐도_취소된_채_결제되는_일은_없다(arena: Arena) -> None:
    rounds = 6

    def make(f: RowFactory) -> tuple[int, int, list[int]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        member = make_member(f, bundle, "racer")
        apps = []
        for n in range(rounds):
            course = make_course(f, bundle, cycle, f"강좌{n}", RCRT_NOPE=3, EDU_BGNG_YMD="20261201")
            apps.append(make_application(f, bundle, member, course, "ES.HOLD"))
        return bundle, member, apps

    bundle, member, apps = arena.build(make)
    arena.serve(bundle)
    arena.pg.delay_seconds = 0.05
    phone, laptop = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, application_sn in enumerate(apps):
        order = request_call(phone, application_sn, f"race-{n}-key-0001")().json()
        parallel(
            [
                confirm_call(phone, order["orderNo"], order["amount"], f"pk-race-{n}"),
                cancel_call(laptop, application_sn),
            ]
        )
        state = arena.query(
            "SELECT a.APLY_STTS_CD, s.STLM_STTS_CD FROM TB_ATNLC_APLY a JOIN TB_STLM s "
            "ON s.ATNLC_APLY_SN = a.ATNLC_APLY_SN WHERE a.ATNLC_APLY_SN = :a",
            a=application_sn,
        )[0]
        pair = (state["APLY_STTS_CD"], state["STLM_STTS_CD"])
        # 둘 중 하나가 이긴다. 취소가 이기면 PG를 부르기 전이라 결제도 취소, 승인이 이기면 확정이다.
        assert pair in {("ES.CANCEL", "PS.CANCEL"), ("ES.CONFIRM", "PS.PAID")}, pair


def test_결제_요청을_여러_기기에서_동시에_해도_사용할_수_있는_결제창은_하나다(arena: Arena) -> None:
    bundle, member, _, application_sn = arena.build(one_holder)
    arena.serve(bundle)
    devices = [arena.applicant(member, bundle) for _ in range(6)]
    responses = parallel(
        [request_call(d, application_sn, f"many-{n}-key-0001") for n, d in enumerate(devices)]
    )
    assert {r.status_code for r in responses} == {201}
    states = sorted(r["STLM_STTS_CD"] for r in arena.query("SELECT STLM_STTS_CD FROM TB_STLM"))
    assert states == ["PS.CANCEL"] * 5 + ["PS.READY"]  # 마지막에 요청한 하나만 남는다


def test_같은_키로_동시에_결제를_요청해도_결제는_하나다(arena: Arena) -> None:
    bundle, member, _, application_sn = arena.build(one_holder)
    arena.serve(bundle)
    devices = [arena.applicant(member, bundle) for _ in range(8)]
    responses = parallel([request_call(d, application_sn, "same-pay-key-0001") for d in devices])
    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["orderNo"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_STLM")) == 1


def test_같은_키를_다른_신청에_동시에_쓰면_하나만_성공한다(arena: Arena) -> None:
    rounds = 6

    def make(f: RowFactory) -> tuple[int, int, list[tuple[int, int]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        member = make_member(f, bundle, "twin")
        pairs = []
        for n in range(rounds):
            one = make_course(f, bundle, cycle, f"가{n}", EDU_BGNG_YMD="20261201")
            two = make_course(f, bundle, cycle, f"나{n}", EDU_BGNG_YMD="20261201")
            pairs.append(
                (
                    make_application(f, bundle, member, one, "ES.HOLD"),
                    make_application(f, bundle, member, two, "ES.HOLD"),
                )
            )
        return bundle, member, pairs

    bundle, member, pairs = arena.build(make)
    arena.serve(bundle)
    phone, laptop = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, (one, two) in enumerate(pairs):
        key = f"cross-pay-{n}-key-0001"
        responses = parallel([request_call(phone, one, key), request_call(laptop, two, key)])
        assert sorted(outcome(r) for r in responses) == ["201", "IDEMPOTENCY_CONFLICT"]
    assert len(arena.query("SELECT 1 FROM TB_STLM")) == rounds


# --- PG 통보(웹훅) ------------------------------------------------------------------------------


def webhook_call(arena: Arena, order_no: str, event_id: str) -> Callable[[], Any]:
    """서명을 맞춘 통보를 로그인 없이 보낸다. 호출마다 따로 연 클라이언트다."""
    body = json.dumps({"eventId": event_id, "orderNo": order_no}, sort_keys=True).encode()
    client = TestClient(arena.app, base_url="https://testserver", raise_server_exceptions=False)
    return lambda: client.post(
        "/api/pg/webhook/mock",
        content=body,
        headers={"x-mock-signature": arena.pg.sign(body), "content-type": "application/json"},
    )


def approved(order_no: str, amount: int = 30000) -> ApproveResult:
    return ApproveResult(
        ApproveOutcome.APPROVED,
        transaction_id="tx-hook",
        approval_no="H0000001",
        order_no=order_no,
        amount=amount,
        merchant_id=MockPaymentGateway().merchant_id,
        currency="KRW",
    )


def test_같은_통보를_동시에_여러_번_받아도_한_번만_처리한다(arena: Arena) -> None:
    bundle, member, _, application_sn = arena.build(one_holder)
    arena.serve(bundle)
    order = request_call(arena.applicant(member, bundle), application_sn, "hook-dup-key-0001")().json()
    arena.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    arena.pg.delay_seconds = 0.0
    responses = parallel([webhook_call(arena, order["orderNo"], "evt-same") for _ in range(8)])
    answers = sorted(r.json()["result"] for r in responses)
    assert answers == ["duplicate"] * 7 + ["processed"], answers
    assert len(arena.pg.lookups) == 1  # 거래 조회도 한 번이다
    assert len(arena.query("SELECT 1 FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")) == 1
    assert [r["STLM_STTS_CD"] for r in arena.query("SELECT STLM_STTS_CD FROM TB_STLM")] == ["PS.PAID"]


def test_통보와_승인_확인이_겹쳐도_결제는_한_번만_완료된다(arena: Arena) -> None:
    rounds = 5

    def make(f: RowFactory) -> tuple[int, int, list[int]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        member = make_member(f, bundle, "racer")
        apps = []
        for n in range(rounds):
            course = make_course(f, bundle, cycle, f"강좌{n}", RCRT_NOPE=3, EDU_BGNG_YMD="20261201")
            apps.append(make_application(f, bundle, member, course, "ES.HOLD"))
        return bundle, member, apps

    bundle, member, apps = arena.build(make)
    arena.serve(bundle)
    arena.pg.delay_seconds = 0.05
    phone, laptop = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, application_sn in enumerate(apps):
        order = request_call(phone, application_sn, f"hook-race-{n}-key-0001")().json()
        arena.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
        parallel(
            [
                confirm_call(phone, order["orderNo"], order["amount"], f"pk-hook-{n}"),
                webhook_call(arena, order["orderNo"], f"evt-race-{n}"),
            ]
        )
        state = arena.query(
            "SELECT a.APLY_STTS_CD, s.STLM_STTS_CD FROM TB_ATNLC_APLY a JOIN TB_STLM s "
            "ON s.ATNLC_APLY_SN = a.ATNLC_APLY_SN WHERE a.ATNLC_APLY_SN = :a",
            a=application_sn,
        )[0]
        assert (state["APLY_STTS_CD"], state["STLM_STTS_CD"]) == ("ES.CONFIRM", "PS.PAID"), state
    paid = arena.query("SELECT 1 FROM TB_STLM WHERE STLM_STTS_CD = 'PS.PAID'")
    assert len(paid) == rounds  # 주문마다 정확히 한 번 완료됐다
    assert laptop is not None


def test_거래_조회가_오래_걸려도_같은_통보는_기다리지_않고_바로_중복으로_응답한다(arena: Arena) -> None:
    bundle, member, _, application_sn = arena.build(one_holder)
    arena.serve(bundle)
    order = request_call(arena.applicant(member, bundle), application_sn, "hook-slow-key-0001")().json()
    arena.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"])
    entered, release = threading.Event(), threading.Event()
    original = arena.pg.lookup

    def slow_lookup(*, order_no: str) -> ApproveResult:
        entered.set()
        release.wait(timeout=30)
        return original(order_no=order_no)

    arena.pg.lookup = slow_lookup  # type: ignore[method-assign]
    first_call, second_call = (
        webhook_call(arena, order["orderNo"], "evt-slow"),
        webhook_call(arena, order["orderNo"], "evt-slow"),
    )
    results: dict[str, Any] = {}
    first = threading.Thread(target=lambda: results.update(first=first_call()))
    first.start()
    assert entered.wait(timeout=10)  # 첫 통보가 PG 조회에 들어가 있다
    second = threading.Thread(target=lambda: results.update(second=second_call()))
    second.start()
    second.join(timeout=5)
    answered_while_looking_up = not second.is_alive()  # 조회가 끝나기 전에 응답했는가
    release.set()
    first.join(timeout=30)
    second.join(timeout=30)
    assert answered_while_looking_up, "받은 사건을 먼저 확정하지 않아 조회가 끝날 때까지 기다렸다"
    assert results["second"].json() == {"result": "duplicate"} and results["first"].json() == {
        "result": "processed"
    }
