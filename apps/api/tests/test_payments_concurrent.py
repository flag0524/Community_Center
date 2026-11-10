# 결제 요청·승인 확인의 동시성을 서로 다른 DB 연결로 확인하는 시험(승인 한 번, 결과 대기 중 자리 보존, ADR-006·040)
from collections.abc import Callable
from typing import Any

import pytest

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
