# 워커 작업(결제기한 만료, 결제 결과 재조회, 환불 결과 조회)과 상태 파일·실행기를 실제 MariaDB로 확인하는 시험
import itertools
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from app.adapters.pg.base import ApproveOutcome, ApproveResult, CancelOutcome, CancelResult
from app.domain.admin.refund_service import pg_key
from app.worker import jobs
from app.worker.runner import Job, build_jobs, run_guarded
from app.worker.status import is_stale, record_run
from tests.test_admin_refunds import Actor, refund, staff
from tests.test_admin_transactions import app_state, approved, course, events, pay_row, pending
from tests.test_applications_read import RESIDENT, application, payment
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

MINUTE = timedelta(minutes=1)
_members = itertools.count(1)


def expire(w: World, limit: int = 50) -> int:
    w.db.commit()  # 작업은 처음에 트랜잭션을 닫으므로 시험이 만든 데이터를 먼저 고정한다
    return jobs.expire_payments(w.db, w.settings, w.bundle, w.clock, limit)


def recheck(w: World) -> int:
    w.db.commit()
    return jobs.recheck_payments(w.db, w.settings, w.pg, w.bundle, w.clock)


def recheck_refunds(w: World) -> int:
    w.db.commit()
    return jobs.recheck_refunds(w.db, w.pg, w.bundle, w.clock)


def holder(
    w: World, row: dict[str, Any], deadline: Any = None, state: str = "ES.HOLD", **values: Any
) -> dict[str, Any]:
    """결제기한이 지난 신청. 기한은 결제대기·수강확정 신청에만 둘 수 있다(CK_SEAT_01)."""
    extra: dict[str, Any] = {}
    if state in ("ES.HOLD", "ES.CONFIRM"):
        extra["STLM_DDLN_DT"] = deadline if deadline is not None else START - MINUTE
    return application(
        w,
        make_member(w, f"h{next(_members)}", MBL_TELNO="01012345678", **RESIDENT),
        row,
        state,
        **{**extra, **values},
    )


# --- 결제기한 만료 ------------------------------------------------------------------------------


def test_기한이_지난_결제대기_신청은_만료되고_자리가_대기자에게_넘어간다(world: World) -> None:
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    app = holder(world, row)
    waiter = application(
        world, make_member(world, "wt", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    assert expire(world) == 1
    assert app_state(world, app) == "ES.EXPIRE" and app_state(world, waiter) == "ES.HOLD"
    audit = (
        world.db.execute(
            text(
                "SELECT ACTR_TYPE_CD a, MNGR_SN m, MBR_SN b, JOB_CD j FROM TB_JOB_HSTRY WHERE JOB_CD IN ('APLY_EXPIRE','APLY_PROMOTE') ORDER BY JOB_HSTRY_SN"
            )
        )
        .mappings()
        .all()
    )
    assert [(r["j"], r["a"], r["m"], r["b"]) for r in audit] == [
        ("APLY_EXPIRE", "AK.SYSTEM", None, None),
        ("APLY_PROMOTE", "AK.SYSTEM", None, None),
    ]
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_SMS_DMND")).scalar() == 1


@pytest.mark.parametrize(
    ("offset", "expired"), [(timedelta(0), 1), (timedelta(seconds=1), 0), (-timedelta(seconds=1), 1)]
)
def test_기한_정각부터_만료하고_기한_전이면_두지_않는다(
    world: World, offset: timedelta, expired: int
) -> None:
    app = holder(world, course(world), deadline=START + offset)
    assert expire(world) == expired
    assert app_state(world, app) == ("ES.EXPIRE" if expired else "ES.HOLD")


def test_결제_결과를_확인_중인_신청은_기한이_지나도_자리를_지킨다(world: World) -> None:
    app, pay = pending(world)
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET STLM_DDLN_DT=:d WHERE ATNLC_APLY_SN=:a"),
        {"d": START - MINUTE, "a": app["ATNLC_APLY_SN"]},
    )
    assert expire(world) == 0
    assert app_state(world, app) == "ES.HOLD" and pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING"


def test_결제창만_발급된_결제는_함께_취소한다(world: World) -> None:
    app = holder(world, course(world))
    pay = payment(world, app, "PS.READY")
    assert expire(world) == 1
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.CANCEL"


@pytest.mark.parametrize("state", ["ES.CONFIRM", "ES.WAIT", "ES.CANCEL", "ES.EXPIRE", "ES.COMPLETE"])
def test_결제대기가_아닌_신청은_건드리지_않는다(world: World, state: str) -> None:
    extra: dict[str, Any] = {"WTNG_SEQ": 1} if state == "ES.WAIT" else {}
    app = holder(world, course(world), state=state, **extra)
    assert expire(world) == 0 and app_state(world, app) == state


def test_다시_돌려도_이미_만료한_신청은_또_처리하지_않는다(world: World) -> None:
    holder(world, course(world))
    assert expire(world) == 1 and expire(world) == 0
    assert (
        world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='APLY_EXPIRE'")).scalar() == 1
    )


def test_한_번에_집는_수를_넘으면_다음_주기가_이어서_처리한다(world: World) -> None:
    row = course(world)
    apps = [holder(world, row, deadline=START - MINUTE * (3 - n)) for n in range(3)]
    assert expire(world, limit=2) == 2
    states = [app_state(world, a) for a in apps]
    assert states == ["ES.EXPIRE", "ES.EXPIRE", "ES.HOLD"]  # 기한이 가장 오래된 것부터
    assert expire(world, limit=2) == 1


def test_후보를_읽은_뒤_잠그는_사이_결제가_끝났으면_만료하지_않는다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = holder(world, course(world))
    real = getattr(jobs, "lock_application")  # noqa: B009  (다시 내보내지 않는 이름이라 속성으로 읽는다)

    def paid_meanwhile(db: Any, bundle_sn: int, application_sn: int) -> Any:
        db.execute(
            text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CONFIRM' WHERE ATNLC_APLY_SN=:a"),
            {"a": application_sn},
        )
        return real(db, bundle_sn, application_sn)

    monkeypatch.setattr("app.worker.jobs.lock_application", paid_meanwhile)
    assert expire(world) == 0 and app_state(world, app) != "ES.EXPIRE"
    expired_jobs = world.db.execute(
        text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='APLY_EXPIRE'")
    ).scalar()
    assert expired_jobs == 0


def test_후보를_읽은_뒤_잠그는_사이_결제_결과_확인이_시작됐으면_만료하지_않는다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = holder(world, course(world))
    real = getattr(jobs, "lock_application")  # noqa: B009  (다시 내보내지 않는 이름이라 속성으로 읽는다)

    def pending_meanwhile(db: Any, bundle_sn: int, application_sn: int) -> Any:
        payment(world, app, "PS.PENDING", STLM_AMT=30000)
        return real(db, bundle_sn, application_sn)

    monkeypatch.setattr("app.worker.jobs.lock_application", pending_meanwhile)
    assert expire(world) == 0 and app_state(world, app) == "ES.HOLD"


def test_교육_시작일부터는_만료해도_대기자를_승격하지_않는다(world: World) -> None:
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261101", EDU_END_YMD="20261231")
    app = holder(world, row)
    waiter = application(world, make_member(world, "wt", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1)
    assert (
        expire(world) == 1 and app_state(world, app) == "ES.EXPIRE" and app_state(world, waiter) == "ES.WAIT"
    )


# --- 결제 결과 재조회 ---------------------------------------------------------------------------


def aged(w: World) -> None:
    """결제 요청 직후의 유예(30초)를 지나게 한다."""
    w.clock.advance(minutes=1)


def test_재조회로_승인이_확인되면_결제완료와_수강확정이고_시스템_이력이_남는다(world: World) -> None:
    app, pay = pending(world)
    world.pg.lookup_results[pay["STLM_NO"]] = approved(world, pay)
    aged(world)
    assert recheck(world) == 1
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.PAID" and app_state(world, app) == "ES.CONFIRM"
    [event] = events(world, pay)
    assert (event["EVENT_ID"], event["PRCS_STTS_CD"], event["EVENT_TYPE_CD"]) == (
        "RECHECK:1",
        "EP.DONE",
        "ET.RECON",
    )
    job = (
        world.db.execute(
            text("SELECT ACTR_TYPE_CD a, MNGR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='PAY_RECHECK'")
        )
        .mappings()
        .one()
    )
    assert (job["a"], job["m"]) == ("AK.SYSTEM", None)


def test_재조회로_거절이_확인되면_결제실패이고_기한이_지났으면_신청을_만료시킨다(world: World) -> None:
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261201")
    app, pay = pending(world, row)
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET STLM_DDLN_DT=:d WHERE ATNLC_APLY_SN=:a"),
        {"d": START - MINUTE, "a": app["ATNLC_APLY_SN"]},
    )
    waiter = application(world, make_member(world, "wt", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1)
    world.pg.lookup_results[pay["STLM_NO"]] = ApproveResult(ApproveOutcome.REJECTED, failure_code="X")
    aged(world)
    assert recheck(world) == 1
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.FAIL"
    assert app_state(world, app) == "ES.EXPIRE" and app_state(world, waiter) == "ES.HOLD"


def test_결과가_계속_불명이면_1분_간격으로_세_번까지만_재조회한다(world: World) -> None:
    app, pay = pending(world)
    aged(world)
    assert recheck(world) == 1
    assert recheck(world) == 0  # 1분이 지나지 않았다
    world.clock.advance(seconds=61)
    assert recheck(world) == 1
    world.clock.advance(seconds=61)
    assert recheck(world) == 1
    world.clock.advance(minutes=10)
    assert recheck(world) == 0  # 자동 재조회는 세 번이 한도다
    assert len(world.pg.lookups) == 3 and [e["EVENT_ID"] for e in events(world, pay)] == [
        "RECHECK:1",
        "RECHECK:2",
        "RECHECK:3",
    ]
    assert all(e["PRCS_STTS_CD"] == "EP.PROCESS" for e in events(world, pay))
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING" and app_state(world, app) == "ES.HOLD"


def test_재조회_간격은_정확히_1분이다(world: World) -> None:
    pending(world)
    aged(world)
    assert recheck(world) == 1
    world.clock.advance(seconds=59)
    assert recheck(world) == 0
    world.clock.advance(seconds=1)  # 마지막 재조회로부터 정확히 60초
    assert recheck(world) == 1


def test_요청_직후의_결제는_건드리지_않는다(world: World) -> None:
    _, pay = pending(world)
    world.clock.advance(seconds=29)
    assert recheck(world) == 0 and world.pg.lookups == []
    world.clock.advance(seconds=1)
    assert recheck(world) == 1


def test_수동_대사_사건은_자동_재조회_횟수에_세지_않는다(world: World) -> None:
    _, pay = pending(world)
    for n in (1, 2, 3):
        world.factory.make(
            "TB_STLM_EVENT",
            STLM_SN=pay["STLM_SN"],
            EVENT_TYPE_CD="ET.RECON",
            EVENT_ID=f"MANUAL:{n}",
            RCPTN_DT=START - 10 * MINUTE,
        )
    aged(world)
    assert recheck(world) == 1


@pytest.mark.parametrize("state", ["PS.READY", "PS.PAID", "PS.FAIL", "PS.CANCEL"])
def test_결과_확인_중이_아닌_결제는_조회하지_않는다(world: World, state: str) -> None:
    extra: dict[str, Any] = {"STLM_APRV_NO": "A1", "STLM_APRV_DT": START} if state == "PS.PAID" else {}
    pending(world, state=state, **extra)
    aged(world)
    assert recheck(world) == 0 and world.pg.lookups == []


def test_조회가_실패해도_결과_불명_사건을_남기고_멈추지_않는다(world: World) -> None:
    _, pay = pending(world)
    world.pg.lookup_raises = True
    aged(world)
    assert recheck(world) == 1
    assert (
        events(world, pay)[0]["PRCS_STTS_CD"] == "EP.PROCESS"
        and pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING"
    )


def test_금액이_다른_응답은_확정하지_않고_대사_필요_사건으로_남긴다(world: World) -> None:
    app, pay = pending(world)
    world.pg.lookup_results[pay["STLM_NO"]] = ApproveResult(
        ApproveOutcome.APPROVED,
        transaction_id="t",
        approval_no="A",
        approved_at=START,
        order_no=pay["STLM_NO"],
        amount=29000,
        merchant_id=world.pg.merchant_id,
        currency="KRW",
    )
    aged(world)
    assert recheck(world) == 1
    assert pay_row(world, pay)["STLM_STTS_CD"] == "PS.PENDING" and app_state(world, app) == "ES.HOLD"
    assert events(world, pay)[0]["PRCS_STTS_CD"] == "EP.FAIL"


def test_조회하는_사이_담당자가_먼저_끝냈으면_다시_반영하지_않는다(world: World) -> None:
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
            text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CONFIRM' WHERE ATNLC_APLY_SN=:a"),
            {"a": app["ATNLC_APLY_SN"]},
        )
        return original(**kwargs)

    world.pg.lookup = settled_elsewhere  # type: ignore[method-assign]
    aged(world)
    assert recheck(world) == 0
    assert (
        events(world, pay) == []
        and world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='PAY_RECHECK'")).scalar()
        == 0
    )


# --- 환불 결과 조회 -----------------------------------------------------------------------------


def pending_refund(w: World, **values: Any) -> dict[str, Any]:
    approver: Actor = staff(w, f"ap{next(_members)}", "AU.RFND_A")
    executor = staff(w, f"ex{next(_members)}", "AU.RFND_X")
    return refund(
        w, status="RS.PENDING", approver=approver, IMPL_MNGR_SN=executor.sn, IMPL_DMND_DT=START, **values
    )


def key_of(w: World, r: dict[str, Any]) -> str:
    return pg_key(w.bundle, int(r["RFND_SN"]))


def refund_state(w: World, r: dict[str, Any]) -> Any:
    return w.db.execute(text("SELECT * FROM TB_RFND WHERE RFND_SN=:r"), {"r": r["RFND_SN"]}).mappings().one()


def test_PG가_취소를_끝냈다고_하면_환불완료로_확정한다(world: World) -> None:
    r = pending_refund(world)
    world.pg.canceled[key_of(world, r)] = CancelResult(CancelOutcome.DONE, cancel_id="c-1", amount=30000)
    aged(world)
    assert recheck_refunds(world) == 1
    row = refund_state(world, r)
    assert (row["RFND_STTS_CD"], row["PG_RFND_ID"]) == ("RS.DONE", "c-1") and row["RFND_DT"] == world.clock()
    assert world.pg.cancel_lookups == [key_of(world, r)]
    job = (
        world.db.execute(text("SELECT ACTR_TYPE_CD a, MNGR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='RFND_DONE'"))
        .mappings()
        .one()
    )
    assert (job["a"], job["m"]) == ("AK.SYSTEM", None)


def test_PG가_취소를_거절했다고_하면_실패로_두어_담당자가_재처리한다(world: World) -> None:
    r = pending_refund(world)
    world.pg.canceled[key_of(world, r)] = CancelResult(CancelOutcome.REJECTED, failure_code="NO_BALANCE")
    aged(world)
    assert recheck_refunds(world) == 1 and refund_state(world, r)["RFND_STTS_CD"] == "RS.FAIL"


def test_PG에서도_결과를_모르면_처리_중으로_두고_사건을_남기지_않는다(world: World) -> None:
    r = pending_refund(world)
    aged(world)
    assert recheck_refunds(world) == 1 and refund_state(world, r)["RFND_STTS_CD"] == "RS.PENDING"
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_STLM_EVENT")).scalar() == 0
    world.pg.lookup_raises = True
    assert recheck_refunds(world) == 1 and refund_state(world, r)["RFND_STTS_CD"] == "RS.PENDING"


def test_취소_금액이_다르면_완료로_보지_않고_확인_필요_사건을_남긴다(world: World) -> None:
    r = pending_refund(world)
    world.pg.canceled[key_of(world, r)] = CancelResult(CancelOutcome.DONE, cancel_id="c", amount=29000)
    aged(world)
    recheck_refunds(world)
    assert refund_state(world, r)["RFND_STTS_CD"] == "RS.PENDING"
    assert world.db.execute(text("SELECT PRCS_STTS_CD FROM TB_STLM_EVENT")).scalar() == "EP.FAIL"


def test_수동_계좌환불과_요청_직후와_처리_중이_아닌_환불은_조회하지_않는다(world: World) -> None:
    manual = pending_refund(
        world, RFND_BANK_CD="004", RFND_ACTNO_ENCPT_VL="x" * 20, RFND_DPSTR_ENCPT_VL="y" * 20
    )
    young = pending_refund(world)
    done = refund(world, status="RS.DONE", RFND_DT=START, IMPL_DMND_DT=START)
    refund(world, status="RS.FAIL", IMPL_DMND_DT=START)
    world.clock.advance(seconds=29)
    assert recheck_refunds(world) == 0
    world.clock.advance(seconds=2)
    assert recheck_refunds(world) == 1  # 요청 직후 유예가 지난 PG 취소 한 건만
    assert world.pg.cancel_lookups == [key_of(world, young)] and manual and done


def test_조회하는_사이_다른_경로가_끝냈으면_다시_반영하지_않는다(world: World) -> None:
    r = pending_refund(world)
    world.pg.canceled[key_of(world, r)] = CancelResult(CancelOutcome.DONE, cancel_id="c", amount=30000)
    original = world.pg.lookup_cancel

    def settled_elsewhere(**kwargs: Any) -> Any:
        world.db.execute(
            text(
                "UPDATE TB_RFND SET RFND_STTS_CD='RS.DONE', RFND_DT=:t, RCRD_VER=RCRD_VER+1 WHERE RFND_SN=:r"
            ),
            {"t": START, "r": r["RFND_SN"]},
        )
        return original(**kwargs)

    world.pg.lookup_cancel = settled_elsewhere  # type: ignore[method-assign]
    aged(world)
    assert recheck_refunds(world) == 0
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='RFND_DONE'")).scalar() == 0


# --- 상태 파일·실행기 ---------------------------------------------------------------------------


def test_상태_파일에_작업별_마지막_실행과_결과를_남기고_오래되면_정지로_본다(tmp_path: Path) -> None:
    path = tmp_path / "run" / "status.json"
    assert is_stale(path, START)  # 파일이 없으면 정지다
    record_run(path, "expire_payments", ok=True, now=START)
    record_run(path, "recheck_payments", ok=False, now=START + MINUTE, error="TimeoutError")
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["expire_payments"]["ok"] is True and state["recheck_payments"] == {
        "lastRun": "2026-11-09T09:01:00+00:00",
        "ok": False,
        "error": "TimeoutError",
        "handled": None,
    }
    assert not is_stale(path, START + MINUTE * 5) and not is_stale(path, START + MINUTE * 6)
    assert is_stale(path, START + MINUTE * 6 + timedelta(seconds=1))


def test_상태_파일이_깨졌으면_정지로_본다(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text("{깨진", encoding="utf-8")
    assert is_stale(path, START)
    record_run(path, "x", ok=True, now=START)  # 깨진 파일 위에도 다시 쓸 수 있다
    assert not is_stale(path, START)


def test_작업이_오류를_내도_실행기는_멈추지_않고_결과를_기록한다(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    path = tmp_path / "status.json"

    def boom(_: Any) -> int:
        raise TimeoutError("내부 사정")

    run_guarded(Job("bad", 10, boom), engine, path, lambda: START)
    run_guarded(Job("good", 10, lambda _: 2), engine, path, lambda: START)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert state["bad"]["ok"] is False and state["bad"]["error"] == "TimeoutError"
    assert "내부 사정" not in path.read_text(encoding="utf-8")  # 오류 내용은 담지 않고 종류만 남긴다
    assert state["good"]["ok"] is True and state["good"]["handled"] == 2  # 처리한 건수를 남긴다


def test_작업_목록은_문서의_주기를_따른다(world: World) -> None:
    listed = build_jobs(world.settings, world.pg, world.sms, world.bundle, world.clock)
    assert [(j.name, j.seconds, j.cron) for j in listed] == [
        ("sms_dispatch", 5, None),
        ("expire_payments", 10, None),
        ("recheck_payments", 30, None),
        ("recheck_refunds", 30, None),
        ("consistency_check", 0, (3, 0)),  # 매일 03:00(한국 시각)
    ]
