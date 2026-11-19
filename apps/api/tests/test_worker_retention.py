# 매일 새벽 자동 정리(탈퇴 30일 회원 비식별, 30일 지난 인증번호 요청 삭제, 이체 완료한 환불의 남은 계좌정보 파기)와 관리자 실행을 실제 MariaDB로 확인하는 시험
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.crypto import encrypt
from app.domain.admin import retention_service
from app.domain.admin.retention_types import RetentionTarget
from app.worker import retention
from tests.test_admin_refunds import refund
from tests.test_admin_retention import session_row
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


# --- 세션·로그인 실패 이력(기관 확정 2026-11-19) -------------------------------------------------


def test_새벽_정리가_끝난_지_30일이_지난_세션과_90일이_지난_로그인_실패를_지운다(world: World) -> None:
    me = make_member(world, "auto")
    session_row(
        world,
        me,
        "old",
        ISSU_DT=START - timedelta(days=80),
        LAST_ACT_DT=START - timedelta(days=50),
        EXPRY_DT=START - timedelta(days=40),
    )
    kept = session_row(
        world,
        me,
        "live",
        ISSU_DT=START - timedelta(days=2),
        LAST_ACT_DT=START,
        EXPRY_DT=START + timedelta(minutes=30),
    )
    for n, days in enumerate((120, 20)):
        world.factory.make(
            "TB_LGN_FAIL_HSTRY",
            OPER_BNDL_SN=world.bundle,
            MBR_SN=me["MBR_SN"],
            FAIL_DT=START - timedelta(days=days),
            DMND_ID=f"auto-{n}",
        )
    assert sweep(world) == 2
    sessions = [
        int(s)
        for s in world.db.execute(
            text("SELECT LGN_SSN_SN FROM TB_LGN_SSN WHERE MBR_SN=:m"), {"m": me["MBR_SN"]}
        ).scalars()
    ]
    fails = world.db.execute(
        text("SELECT COUNT(*) FROM TB_LGN_FAIL_HSTRY WHERE MBR_SN=:m"), {"m": me["MBR_SN"]}
    ).scalar()
    assert sessions == [int(kept["LGN_SSN_SN"])] and fails == 1
    assert sorted(j["t"] for j in jobs(world)) == ["TB_LGN_FAIL_HSTRY", "TB_LGN_SSN"]
    assert sweep(world) == 0


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


# --- 확정 때 파기하지 못하고 남은 문자 -------------------------------------------------------------


def sms(w: World, *states: str) -> tuple[int, list[int]]:
    """문안과 수신번호가 그대로 남은 문자 요청 한 건. 수신 대상 상태를 줄 수 있다."""
    request = w.factory.make("TB_SMS_DMND", OPER_BNDL_SN=w.bundle, SMS_CN="[조리읍] 안내")
    targets = [
        int(
            w.factory.make(
                "TB_SMS_TRGT",
                SMS_DMND_SN=request["SMS_DMND_SN"],
                MBR_SN=make_member(w, f"sr{i}-{request['SMS_DMND_SN']}")["MBR_SN"],
                RCPTN_TELNO_ENCPT_VL=encrypt(w.settings.secret_key, "01012345678"),
                TRGT_STTS_CD=state,
            )["SMS_TRGT_SN"]
        )
        for i, state in enumerate(states)
    ]
    return int(request["SMS_DMND_SN"]), targets


def sms_values(w: World, request: int) -> tuple[str, list[str]]:
    body = w.db.execute(text("SELECT SMS_CN FROM TB_SMS_DMND WHERE SMS_DMND_SN=:d"), {"d": request}).scalar()
    phones = w.db.execute(
        text("SELECT RCPTN_TELNO_ENCPT_VL FROM TB_SMS_TRGT WHERE SMS_DMND_SN=:d ORDER BY SMS_TRGT_SN"),
        {"d": request},
    ).scalars()
    return str(body), [str(p) == "PURGED" and "P" or "K" for p in phones]


def test_결과가_확정됐는데_남은_문자를_매일_새벽_파기한다(world: World) -> None:
    done, _ = sms(world, "SS.SENT", "SS.FAIL", "SS.SKIP")
    half, _ = sms(world, "SS.SENT", "SS.SENDING")  # 한 명은 아직 확정이 아니다
    waiting, _ = sms(world, "SS.WAIT", "SS.UNKNOWN")
    assert sweep(world) == 2
    assert sms_values(world, done) == ("(파기됨)", ["P", "P", "P"])
    assert sms_values(world, half) == ("[조리읍] 안내", ["P", "K"])  # 확정된 번호만 먼저 파기한다
    assert sms_values(world, waiting) == ("[조리읍] 안내", ["K", "K"])
    assert sweep(world) == 0  # 다시 돌려도 더 처리할 것이 없다
    assert [(j["a"], j["t"], j["c"]) for j in jobs(world)] == [
        ("AK.SYSTEM", "TB_SMS_DMND", "처리 2건 [자동]")
    ]


def test_다른_묶음의_문자와_수신_대상이_없는_요청은_건드리지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")
    foreign = world.factory.make("TB_SMS_DMND", OPER_BNDL_SN=other["OPER_BNDL_SN"], SMS_CN="남의 문안")
    world.factory.make(
        "TB_SMS_TRGT",
        OPER_BNDL_SN=other["OPER_BNDL_SN"],
        SMS_DMND_SN=foreign["SMS_DMND_SN"],
        MBR_SN=make_member(world, "foreign-sms", OPER_BNDL_SN=other["OPER_BNDL_SN"])["MBR_SN"],
        TRGT_STTS_CD="SS.SENT",
    )  # 결과는 확정됐지만 다른 묶음이다
    empty = world.factory.make("TB_SMS_DMND", OPER_BNDL_SN=world.bundle, SMS_CN="대상 없음")
    assert sweep(world) == 0
    for request, body in ((foreign, "남의 문안"), (empty, "대상 없음")):
        assert sms_values(world, int(request["SMS_DMND_SN"]))[0] == body


def test_관리자가_문자_항목을_실행하면_같은_방식으로_파기한다(world: World) -> None:
    done, _ = sms(world, "SS.SENT")
    open_, _ = sms(world, "SS.SENDING")
    operator(world)
    res = run(world, 5, 1)
    assert res.status_code == 200, res.text
    assert sms_values(world, done) == ("(파기됨)", ["P"]) and sms_values(world, open_)[1] == ["K"]
    assert res.json()["executions"][0]["processed"] == 1 and res.json()["count"] == 0
    assert run(world, 5, 1).status_code == 409  # 처리할 것이 없어졌으니 확인한 건수와 다르다
