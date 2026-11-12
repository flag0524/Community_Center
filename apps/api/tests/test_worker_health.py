# 일일 정합성 점검(오래 확정되지 않은 결제·환불·문자·파일)과 /api/health(DB·워커 생존)를 실제 MariaDB로 확인하는 시험
import itertools
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_db
from app.worker import consistency
from app.worker.consistency import find_stale
from app.worker.status import record_run
from tests.test_admin_refunds import refund
from tests.test_admin_transactions import pending
from tests.test_worker_sms import outbox
from tests.world import START, World

pytestmark = pytest.mark.db

HOUR = timedelta(hours=1)
_keys = itertools.count(1)


def stale(w: World) -> consistency.StaleReport:
    w.db.commit()
    return find_stale(w.db, w.bundle, w.clock())


def kinds(report: consistency.StaleReport) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for item in report.items:
        found.setdefault(item.kind, []).append(item.key)
    return found


def file_row(w: World, status: str, age: timedelta) -> dict[str, Any]:
    n = next(_keys)
    return w.factory.make(
        "TB_FILE",
        STRG_KEY=f"b{w.bundle}/{n}-object",
        FILE_NM="a.pdf",
        FILE_SZ=1,
        MIME_TYPE_NM="application/pdf",
        FILE_USE_CD="FP.ATTACH",
        FILE_STTS_CD=status,
        REG_DT=START - age,
    )


# --- 정합성 점검 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age", "listed"),
    [
        (timedelta(hours=24), True),
        (timedelta(hours=24) - timedelta(seconds=1), False),
        (timedelta(days=3), True),
    ],
    ids=["정확히_24시간", "1초_모자람", "사흘"],
)
def test_오래_결과_확인_중인_결제를_찾는다(world: World, age: timedelta, listed: bool) -> None:
    _, pay = pending(world, STLM_DMND_DT=START - age)
    found = kinds(stale(world)).get("PAYMENT_PENDING", [])
    assert (int(pay["STLM_SN"]) in found) is listed


def test_결제는_마지막_수정_시각을_기준으로_하고_확인_중이_아니면_찾지_않는다(world: World) -> None:
    _, recent = pending(world, STLM_DMND_DT=START - timedelta(days=3), MDFCN_DT=START - HOUR)  # 최근에 손댔다
    _, paid = pending(
        world, state="PS.PAID", STLM_DMND_DT=START - timedelta(days=3), STLM_APRV_NO="A", STLM_APRV_DT=START
    )
    assert kinds(stale(world)).get("PAYMENT_PENDING", []) == []
    assert recent and paid


@pytest.mark.parametrize(("age", "listed"), [(timedelta(hours=24), True), (timedelta(hours=23), False)])
def test_오래_처리_중인_환불을_찾고_집행_요청_시각을_기준으로_한다(
    world: World, age: timedelta, listed: bool
) -> None:
    target = refund(world, status="RS.PENDING", IMPL_DMND_DT=START - age, IMPL_MNGR_SN=refund_admin(world))
    done = refund(world, status="RS.DONE", IMPL_DMND_DT=START - timedelta(days=9), RFND_DT=START)
    found = kinds(stale(world)).get("REFUND_PENDING", [])
    assert (int(target["RFND_SN"]) in found) is listed and int(done["RFND_SN"]) not in found


def refund_admin(w: World) -> int:
    from tests.test_admin_refunds import staff

    return staff(w, f"ex{next(_keys)}", "AU.RFND_X").sn


@pytest.mark.parametrize(("age", "listed"), [(HOUR, True), (HOUR - timedelta(seconds=1), False)])
def test_오래_결과를_모르는_문자를_찾는다(world: World, age: timedelta, listed: bool) -> None:
    trgt = outbox(world)
    world.db.execute(
        text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.UNKNOWN', MDFCN_DT=:t WHERE SMS_TRGT_SN=:s"),
        {"t": START - age, "s": trgt},
    )
    assert (trgt in kinds(stale(world)).get("SMS_UNKNOWN", [])) is listed


def test_OTP_문자와_다른_상태의_문자는_점검하지_않는다(world: World) -> None:
    otp = outbox(world, event="CERT:9")
    sending = outbox(world)
    for sn, status in ((otp, "SS.UNKNOWN"), (sending, "SS.SENDING")):
        world.db.execute(
            text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD=:c, MDFCN_DT=:t WHERE SMS_TRGT_SN=:s"),
            {"c": status, "t": START - timedelta(days=2), "s": sn},
        )
    assert "SMS_UNKNOWN" not in kinds(stale(world))


@pytest.mark.parametrize(
    ("status", "age", "listed"),
    [
        ("FS.PENDING", HOUR, True),
        ("FS.PENDING", HOUR - timedelta(seconds=1), False),
        ("FS.SAFE", timedelta(days=2), False),
    ],
)
def test_오래_검사_대기_중인_파일을_찾는다(world: World, status: str, age: timedelta, listed: bool) -> None:
    row = file_row(world, status, age)
    assert (int(row["FILE_SN"]) in kinds(stale(world)).get("FILE_PENDING", [])) is listed


def test_목록은_오래된_것부터이고_넘치면_건수만_정확히_센다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    pays = [pending(world, STLM_DMND_DT=START - timedelta(days=n + 2))[1] for n in range(3)]
    monkeypatch.setattr(consistency, "PER_KIND", 2)
    report = stale(world)
    assert report.counts["PAYMENT_PENDING"] == 3 and report.total == 3
    assert kinds(report)["PAYMENT_PENDING"] == [
        int(pays[2]["STLM_SN"]),
        int(pays[1]["STLM_SN"]),
    ]  # 가장 오래된 둘


def test_점검은_조회만_하고_로그에는_건수만_남긴다(world: World, caplog: pytest.LogCaptureFixture) -> None:
    _, pay = pending(world, STLM_DMND_DT=START - timedelta(days=2))
    world.db.commit()
    with caplog.at_level(logging.WARNING, logger="app.worker"):
        assert consistency.consistency_check(world.db, world.bundle, world.clock) == 1
    assert "'PAYMENT_PENDING': 1" in caplog.text and str(pay["STLM_NO"]) not in caplog.text
    row = world.db.execute(
        text("SELECT STLM_STTS_CD FROM TB_STLM WHERE STLM_SN=:s"), {"s": pay["STLM_SN"]}
    ).scalar()
    assert row == "PS.PENDING"  # 바꾸지 않는다
    caplog.clear()
    world.db.execute(text("DELETE FROM TB_STLM WHERE STLM_SN=:s"), {"s": pay["STLM_SN"]})
    with caplog.at_level(logging.WARNING, logger="app.worker"):
        assert consistency.consistency_check(world.db, world.bundle, world.clock) == 0
    assert caplog.text == ""  # 이상이 없으면 조용하다


# --- /api/health --------------------------------------------------------------------------------


def with_status_file(w: World, path: Path) -> None:
    settings = replace(w.settings, worker_status_file=str(path))
    w.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]


def health(w: World) -> Any:
    return w.client.get("/api/health")


def test_상태_파일이_없으면_워커가_정지한_것으로_보고_503이다(world: World, tmp_path: Path) -> None:
    with_status_file(world, tmp_path / "none.json")
    r = health(world)
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": True, "worker": {"running": False, "jobs": {}}}


def test_워커가_최근에_일했고_모두_성공이면_200이다(world: World, tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    with_status_file(world, path)
    record_run(path, "expire_payments", ok=True, now=START - timedelta(seconds=10), handled=0)
    r = health(world)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["worker"] == {
        "running": True,
        "jobs": {"expire_payments": {"lastRun": "2026-11-09T08:59:50+00:00", "ok": True}},
    }


def test_마지막_실행이_실패한_작업이_있으면_503이고_오류_내용은_보이지_않는다(
    world: World, tmp_path: Path
) -> None:
    path = tmp_path / "s.json"
    with_status_file(world, path)
    record_run(path, "expire_payments", ok=True, now=START)
    record_run(path, "sms_dispatch", ok=False, now=START, error="OperationalError", handled=None)
    r = health(world)
    assert r.status_code == 503 and r.json()["worker"]["running"] is True
    assert r.json()["worker"]["jobs"]["sms_dispatch"]["ok"] is False
    assert "OperationalError" not in r.text


def test_5분_넘게_아무_작업도_돌지_않으면_503이다(world: World, tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    with_status_file(world, path)
    record_run(path, "expire_payments", ok=True, now=START)
    world.clock.advance(minutes=5)
    assert health(world).status_code == 200  # 정확히 5분은 정지가 아니다
    world.clock.advance(seconds=1)
    r = health(world)
    assert r.status_code == 503 and r.json()["worker"]["running"] is False and r.json()["database"] is True


def test_DB에_닿지_않으면_503이다(world: World, tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    with_status_file(world, path)
    record_run(path, "expire_payments", ok=True, now=START)

    class Broken:
        def execute(self, *_: Any, **__: Any) -> Any:
            raise ConnectionError("접속 끊김")

        def commit(self) -> None: ...

        def rollback(self) -> None: ...

        def close(self) -> None: ...

    world.client.app.dependency_overrides[get_db] = lambda: iter([Broken()])  # type: ignore[attr-defined]
    r = health(world)
    assert r.status_code == 503 and r.json()["database"] is False and r.json()["worker"]["running"] is True


def test_건강_확인은_로그인_없이_부를_수_있고_계약_문서에는_없다(world: World, tmp_path: Path) -> None:
    with_status_file(world, tmp_path / "none.json")
    assert health(world).status_code in (200, 503)  # 401이 아니다
    assert "/api/health" not in world.client.app.openapi()["paths"]  # type: ignore[attr-defined]
