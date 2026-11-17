# 웹훅 재시도 작업(조회 실패로 남은 통보를 1분 간격 최대 3회 다시 조회, 대사가 필요한 사건은 건드리지 않음)을 실제 MariaDB로 확인하는 시험
from typing import Any

import pytest
from sqlalchemy import text

from app.worker import jobs
from tests.test_payments_flow import rows
from tests.test_payments_webhook import app_state, approved, issue, pay_state, send
from tests.world import World

pytestmark = pytest.mark.db


def event(w: World) -> Any:
    return rows(w, "SELECT * FROM TB_STLM_EVENT WHERE EVENT_TYPE_CD = 'ET.WEBHOOK'")[0]


def failed(w: World) -> str:
    """조회가 실패해 재시도 대상으로 남은 통보 한 건을 만들고 그 주문번호를 돌려준다."""
    _, order = issue(w)
    w.pg.lookup_raises = True
    assert send(w, order["orderNo"]).json() == {"result": "retry"}
    w.pg.lookup_raises = False
    return str(order["orderNo"])


def retry(w: World) -> int:
    w.db.commit()  # 작업은 처음에 트랜잭션을 닫으므로 시험이 만든 데이터를 먼저 고정한다
    return jobs.retry_webhooks(w.db, w.settings, w.pg, w.bundle, w.clock)


def test_1분이_지나기_전에는_다시_보지_않고_지나면_조회해_확정한다(world: World) -> None:
    order = failed(world)
    world.pg.lookup_results[order] = approved(order)
    before = len(world.pg.lookups)
    world.clock.advance(seconds=59)
    assert retry(world) == 0 and len(world.pg.lookups) == before
    world.clock.advance(seconds=1)
    assert retry(world) == 1
    assert (pay_state(world), app_state(world)) == ("PS.PAID", "ES.CONFIRM")
    got = event(world)
    assert (got["PRCS_STTS_CD"], got["RTRY_NMTM"]) == ("EP.DONE", 0)
    job = rows(world, "SELECT ACTR_TYPE_CD a, JOB_CD j FROM TB_JOB_HSTRY WHERE JOB_CD = 'PAY_WEBHOOK_RETRY'")
    assert [(r["a"], r["j"]) for r in job] == [("AK.SYSTEM", "PAY_WEBHOOK_RETRY")]


def test_다시_조회해도_모르면_횟수만_늘리고_세_번이면_멈춘다(world: World) -> None:
    failed(world)  # 최초 통보가 1회째다
    world.pg.lookup_raises = True  # 조회가 예외를 내도 작업은 멈추지 않고 결과 불명으로 본다
    handled = []
    for _ in range(4):
        world.clock.advance(minutes=1)
        handled.append(retry(world))
    assert handled == [1, 1, 0, 0]  # 통보 때 1회 + 재시도 2회 = 3회에서 멈춘다
    got = event(world)
    assert (got["PRCS_STTS_CD"], got["RTRY_NMTM"]) == ("EP.FAIL", 3)
    assert (pay_state(world), app_state(world)) == ("PS.READY", "ES.HOLD")  # 업무는 바꾸지 않았다


def test_재시도에서_불일치가_드러나면_확정하지_않고_대사_대상으로_남긴다(world: World) -> None:
    order = failed(world)
    world.pg.lookup_results[order] = approved(order, amount=1)
    world.clock.advance(minutes=1)
    assert retry(world) == 1
    got = event(world)
    assert got["PRCS_STTS_CD"] == "EP.FAIL" and "불일치" in got["FAIL_RSN"] and got["RTRY_NMTM"] == 0
    assert pay_state(world) == "PS.READY"
    world.clock.advance(minutes=5)
    assert retry(world) == 0  # 사람이 대사할 사건은 다시 조회하지 않는다


def test_처음부터_대사가_필요했던_사건은_재시도하지_않는다(world: World) -> None:
    _, order = issue(world)
    world.pg.lookup_results[order["orderNo"]] = approved(order["orderNo"], amount=1)
    send(world, order["orderNo"])
    assert event(world)["PRCS_STTS_CD"] == "EP.FAIL" and event(world)["RTRY_NMTM"] == 0
    world.clock.advance(minutes=5)
    assert retry(world) == 0 and event(world)["FAIL_RSN"] is not None


def test_다른_경로가_이미_결제를_끝냈으면_사건만_완료로_닫는다(world: World) -> None:
    order = failed(world)
    world.pg.lookup_results[order] = approved(order)
    world.clock.advance(minutes=1)
    assert retry(world) == 1
    # 같은 사건이 다시 재시도 대상이 된 상황(예: 다른 처리가 먼저 결제를 확정한 뒤 늦게 도는 재시도)
    world.db.execute(
        text(
            "UPDATE TB_STLM_EVENT SET PRCS_STTS_CD='EP.FAIL', RTRY_NMTM=1, FAIL_RSN='GATEWAY_ERROR' "
            "WHERE EVENT_TYPE_CD='ET.WEBHOOK'"
        )
    )
    world.clock.advance(minutes=1)
    assert retry(world) == 1
    assert (event(world)["PRCS_STTS_CD"], pay_state(world), app_state(world)) == (
        "EP.DONE",
        "PS.PAID",
        "ES.CONFIRM",
    )
    paid = rows(world, "SELECT COUNT(*) n FROM TB_STLM WHERE STLM_STTS_CD='PS.PAID'")[0]["n"]
    assert paid == 1


def test_통보가_아닌_종류의_사건은_재시도하지_않는다(world: World) -> None:
    failed(world)
    world.db.execute(
        text("UPDATE TB_STLM_EVENT SET EVENT_TYPE_CD='ET.RECON' WHERE EVENT_TYPE_CD='ET.WEBHOOK'")
    )
    world.clock.advance(minutes=5)
    assert retry(world) == 0


def test_조회하는_사이_다른_처리가_사건을_바꿨으면_결제_반영도_하지_않는다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = failed(world)
    world.pg.lookup_results[order] = approved(order)
    real = world.pg.lookup

    def racing(*, order_no: str) -> Any:
        world.db.execute(text("UPDATE TB_STLM_EVENT SET RTRY_NMTM=2 WHERE EVENT_TYPE_CD='ET.WEBHOOK'"))
        return real(order_no=order_no)  # 다른 처리가 이 사건을 먼저 집어 갔다

    monkeypatch.setattr(world.pg, "lookup", racing)
    world.clock.advance(minutes=1)
    assert retry(world) == 0
    world.db.rollback()
    assert (pay_state(world), app_state(world)) == ("PS.READY", "ES.HOLD")  # 결제 반영도 함께 되돌렸다
