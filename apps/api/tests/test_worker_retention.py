# 매일 새벽 자동 정리(탈퇴 30일 회원 비식별, 30일 지난 인증번호 요청 삭제, 이체 완료한 환불의 남은 계좌정보 파기)와 관리자 실행을 실제 MariaDB로 확인하는 시험
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin import retention_service
from app.domain.admin.retention_types import RetentionTarget
from app.worker import retention
from tests.test_admin_refunds import refund
from tests.test_admin_retention_execute import cert_count, member_row, operator, otp, run, withdrawn
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

ACCOUNT: dict[str, Any] = {
    "RFND_BANK_CD": "004",
    "RFND_ACTNO_ENCPT_VL": "enc-account",
    "RFND_DPSTR_ENCPT_VL": "enc-holder",
}


def accounts(w: World, row: dict[str, Any]) -> tuple[Any, Any, Any]:
    got = w.db.execute(
        text(
            "SELECT RFND_BANK_CD b, RFND_ACTNO_ENCPT_VL a, RFND_DPSTR_ENCPT_VL h FROM TB_RFND WHERE RFND_SN=:r"
        ),
        {"r": row["RFND_SN"]},
    ).one()
    return got.b, got.a, got.h


def sweep(w: World) -> int:
    w.db.commit()  # 작업은 시험이 만든 데이터를 먼저 고정한 뒤 돈다
    return retention.purge_due(w.db, w.bundle, w.clock)


def jobs(w: World) -> list[Any]:
    return list(
        w.db.execute(
            text(
                "SELECT ACTR_TYPE_CD a, TRGT_TBL_NM t, TRGT_KEY_VL k, CHG_CN c, MNGR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='RETENTION_EXECUTE' ORDER BY JOB_HSTRY_SN"
            )
        ).mappings()
    )


# --- 이체 완료한 환불의 계좌정보 ------------------------------------------------------------------


def test_관리자가_이체_완료한_환불의_남은_계좌정보를_파기한다(world: World) -> None:
    gone1 = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=2), **ACCOUNT)
    gone2 = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=9), **ACCOUNT)
    pending = refund(world, status="RS.APPROVE", **ACCOUNT)  # 아직 이체 전이라 계좌정보가 필요하다
    clean = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1))  # 처음부터 계좌가 없다
    operator(world)
    res = run(world, 4, 2)
    assert res.status_code == 200, res.text
    assert accounts(world, gone1) == accounts(world, gone2) == (None, None, None)
    assert accounts(world, pending) == ("004", "enc-account", "enc-holder")
    assert accounts(world, clean) == (None, None, None)
    assert res.json()["executions"][0]["processed"] == 2 and res.json()["count"] == 0
    assert [j["t"] for j in jobs(world)] == ["TB_RFND"]


def test_계좌정보_파기_대상은_이체_완료한_환불의_남은_칸만이다(world: World) -> None:
    bank_only = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1), RFND_BANK_CD="004")
    account_only = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1), RFND_ACTNO_ENCPT_VL="a")
    holder_only = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1), RFND_DPSTR_ENCPT_VL="h")
    failed = refund(world, status="RS.FAIL", RFND_DT=START - timedelta(days=1), **ACCOUNT)  # 완료가 아니다
    future = refund(
        world, status="RS.DONE", RFND_DT=START + timedelta(hours=1), **ACCOUNT
    )  # 아직 완료 시각 전이다
    assert sweep(world) == 3  # 어느 칸 하나라도 남아 있으면 대상이다
    assert (
        accounts(world, bank_only)
        == accounts(world, account_only)
        == accounts(world, holder_only)
        == (None, None, None)
    )
    assert accounts(world, failed) == ("004", "enc-account", "enc-holder")
    assert accounts(world, future) == ("004", "enc-account", "enc-holder")


def test_다른_묶음에_대해서는_이_묶음의_계좌정보를_건드리지_않는다(world: World) -> None:
    done = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1), **ACCOUNT)
    other = world.factory.make("TB_OPER_BNDL")
    world.db.commit()
    purged = retention_service.purge_target(
        world.db,
        int(other["OPER_BNDL_SN"]),
        RetentionTarget.REFUND_ACCOUNT,
        now=START,
        request_id="worker-test-other-bundle",
    )
    assert purged == 0 and accounts(world, done) == ("004", "enc-account", "enc-holder")


def test_자동_정리는_종류마다_커밋해_되돌려도_남는다(world: World) -> None:
    old = withdrawn(world, "old", 45)
    otp(world, 40)
    assert sweep(world) == 2
    world.db.rollback()  # 커밋하지 않았다면 여기서 처리 결과가 사라진다
    assert member_row(world, old["MBR_SN"])["n"] == "탈퇴회원" and cert_count(world) == 0


# --- 매일 새벽 자동 정리 ------------------------------------------------------------------------


def test_자동_정리는_기간이_지난_세_종류를_처리하고_시스템_이력을_남긴다(world: World) -> None:
    old = withdrawn(world, "old", 45)
    young = withdrawn(world, "young", 10)
    active = make_member(world, "active", MBL_TELNO="01099998888")
    otp(world, 40)
    otp(world, 5)
    done = refund(world, status="RS.DONE", RFND_DT=START - timedelta(hours=1), **ACCOUNT)
    waiting = refund(world, status="RS.PENDING", **ACCOUNT)
    assert sweep(world) == 3  # 회원 1 + 인증번호 요청 1 + 환불 계좌 1
    assert member_row(world, old["MBR_SN"])["n"] == "탈퇴회원"
    assert member_row(world, young["MBR_SN"])["n"] == "이름young"
    assert member_row(world, active["MBR_SN"])["p"] == "01099998888"
    assert cert_count(world) == 1
    assert accounts(world, done) == (None, None, None)
    assert accounts(world, waiting) == ("004", "enc-account", "enc-holder")
    assert sorted((j["a"], j["t"], j["c"]) for j in jobs(world)) == [
        ("AK.SYSTEM", "TB_CERT_DMND", "처리 1건 [자동]"),
        ("AK.SYSTEM", "TB_MBR", "처리 1건 [자동]"),
        ("AK.SYSTEM", "TB_RFND", "처리 1건 [자동]"),
    ]
    assert all(j["m"] is None for j in jobs(world))  # 사람이 한 일이 아니다


def test_자동_정리를_다시_돌려도_이미_처리한_것은_건드리지_않는다(world: World) -> None:
    withdrawn(world, "old", 45)
    otp(world, 40)
    refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1), **ACCOUNT)
    assert sweep(world) == 3
    assert sweep(world) == 0
    assert len(jobs(world)) == 3  # 처리할 것이 없으면 이력도 남기지 않는다


def test_자동_정리는_다른_묶음의_자료를_건드리지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")
    foreign = withdrawn(world, "foreign", 60, OPER_BNDL_SN=other["OPER_BNDL_SN"])
    world.factory.make("TB_CERT_DMND", OPER_BNDL_SN=other["OPER_BNDL_SN"], REG_DT=START - timedelta(days=90))
    assert sweep(world) == 0
    assert member_row(world, foreign["MBR_SN"])["n"] == "이름foreign"


def test_자동_정리가_실행한_기록은_관리자_상세에_SYSTEM으로_보인다(world: World) -> None:
    from tests.test_admin_refunds import call

    withdrawn(world, "old", 45)
    operator(world)
    assert sweep(world) == 1
    detail = call(world, "GET", "/retention/1").json()
    assert detail["executions"][0]["by"] == "SYSTEM" and detail["executions"][0]["processed"] == 1
    assert detail["count"] == 0 and detail["canExecute"] is False


def test_한_종류가_실패해도_나머지는_처리하고_마지막에_실패를_알린다(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    withdrawn(world, "old", 45)
    otp(world, 40)
    real = retention_service.purge_target

    def flaky(db: Any, bundle: int, target: RetentionTarget, **kw: Any) -> int:
        if target is RetentionTarget.WITHDRAWN_MEMBER:
            raise RuntimeError("이름 홍길동 01012345678")  # 개인정보가 로그에 새지 않는지 본다
        return real(db, bundle, target, **kw)

    monkeypatch.setattr(retention_service, "purge_target", flaky)
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError, match="WITHDRAWN_MEMBER"):
        sweep(world)
    assert cert_count(world) == 0  # 인증번호 요청은 처리했다
    assert "홍길동" not in caplog.text and "01012345678" not in caplog.text
    assert "RuntimeError" in caplog.text  # 종류만 남긴다


def test_일정에_새벽_4시가_들어_있다(world: World) -> None:
    from app.adapters.scan.mock import MockScanner
    from app.worker.runner import build_jobs

    listed = build_jobs(world.settings, world.pg, world.sms, MockScanner(), world.bundle, world.clock)
    assert [(j.name, j.cron) for j in listed if j.name == "retention"] == [("retention", (4, 0))]
