# 워커의 문자 발송(아웃박스 발송, 접수·결과 불명 문자의 조회, 재발송 금지)을 실제 MariaDB로 확인하는 시험
import hashlib
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.sms.base import DeliveryState, SendOutcome, SmsLookup
from app.auth.crypto import encrypt
from app.worker import jobs
from tests.test_applications_read import RESIDENT
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_keys = itertools.count(1)
PHONE = "01012345678"


def dispatch(w: World) -> int:
    w.db.commit()  # 작업은 처음에 트랜잭션을 닫으므로 시험이 만든 데이터를 먼저 고정한다
    return jobs.dispatch_sms(w.db, w.settings, w.sms, w.bundle, w.clock)


def recheck(w: World) -> int:
    w.db.commit()
    return jobs.recheck_sms(w.db, w.sms, w.bundle, w.clock)


def outbox(
    w: World, body: str = "[조리읍] 수강이 확정되었습니다.", event: str | None = None, phone: str = PHONE
) -> int:
    """아웃박스에 쌓인 문자 한 건(요청 + 수신대상). 수신대상 번호를 돌려준다."""
    n = next(_keys)
    member = make_member(w, f"s{n}", **RESIDENT)
    request = w.factory.make(
        "TB_SMS_DMND",
        DMND_TYPE_CD="SM.AUTO",
        TRGT_TYPE_CD="SG.EVENT",
        DSPTCH_TELNO="0319400000",
        SMS_CN=body,
        IDEM_KEY=f"promo-{n}",
        DMND_HASH_VL=hashlib.sha256(body.encode()).hexdigest(),
        SRC_EVENT_ID=event or f"PROMO:{n}:t",
    )
    target = w.factory.make(
        "TB_SMS_TRGT",
        SMS_DMND_SN=request["SMS_DMND_SN"],
        MBR_SN=member["MBR_SN"],
        RCPTN_TELNO_ENCPT_VL=encrypt(w.settings.secret_key, phone),
        TRGT_STTS_CD="SS.WAIT",
    )
    return int(target["SMS_TRGT_SN"])


def state(w: World, trgt: int) -> str:
    return str(
        w.db.execute(text("SELECT TRGT_STTS_CD FROM TB_SMS_TRGT WHERE SMS_TRGT_SN=:t"), {"t": trgt}).scalar()
    )


def attempts(w: World, trgt: int) -> list[Any]:
    return list(
        w.db.execute(
            text("SELECT * FROM TB_SMS_SNDNG_HSTRY WHERE SMS_TRGT_SN=:t ORDER BY SNDNG_SEQ"), {"t": trgt}
        )
        .mappings()
        .all()
    )


# --- 발송 ---------------------------------------------------------------------------------------


def test_아웃박스의_문자를_보내면_공급자_접수로_기록한다(world: World) -> None:
    trgt = outbox(world)
    assert dispatch(world) == 1
    [message] = world.sms.outbox
    assert (message.to, message.text, message.sender) == (
        PHONE,
        "[조리읍] 수강이 확정되었습니다.",
        "0319400000",
    )
    assert state(world, trgt) == "SS.SENDING"
    [attempt] = attempts(world, trgt)
    assert (attempt["SNDNG_SEQ"], attempt["PRCS_STTS_CD"], attempt["SPLR_MSG_ID"]) == (
        1,
        "SS.SENDING",
        "mock-1",
    )
    assert attempt["IDEM_KEY"] == f"sms-{trgt}-1" == message.idempotency_key
    assert attempt["SPLR_NM"] == "mock" and attempt["RSLT_IDNTY_DT"] is None


def test_공급자가_거절하면_실패로_남기고_자동으로_다시_보내지_않는다(world: World) -> None:
    trgt = outbox(world)
    world.sms.next_outcome = SendOutcome.REJECTED
    assert dispatch(world) == 1
    assert state(world, trgt) == "SS.FAIL" and world.sms.outbox == []
    [attempt] = attempts(world, trgt)
    assert (attempt["PRCS_STTS_CD"], attempt["FAIL_CD"], attempt["RSLT_IDNTY_DT"]) == (
        "SS.FAIL",
        "MOCK_REJECTED",
        world.clock(),
    )
    assert dispatch(world) == 0 and len(attempts(world, trgt)) == 1


@pytest.mark.parametrize("how", ["timeout", "exception"])
def test_결과를_모르면_결과_확인_중으로_두고_새로_보내지_않는다(world: World, how: str) -> None:
    trgt = outbox(world)
    if how == "timeout":
        world.sms.next_outcome = SendOutcome.UNKNOWN
    else:
        world.sms.raises = True
    assert dispatch(world) == 1
    assert state(world, trgt) == "SS.UNKNOWN"
    world.sms.raises = False
    assert dispatch(world) == 0 and len(attempts(world, trgt)) == 1  # 같은 문자를 다시 보내지 않는다


def test_OTP_문자는_API가_직접_보내므로_워커가_건드리지_않는다(world: World) -> None:
    trgt = outbox(world, event="CERT:77")
    assert dispatch(world) == 0 and state(world, trgt) == "SS.WAIT" and world.sms.outbox == []


@pytest.mark.parametrize("status", ["SS.SENDING", "SS.SENT", "SS.FAIL", "SS.UNKNOWN", "SS.SKIP"])
def test_발송대기가_아닌_수신대상은_보내지_않는다(world: World, status: str) -> None:
    trgt = outbox(world)
    world.db.execute(
        text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD=:s WHERE SMS_TRGT_SN=:t"), {"s": status, "t": trgt}
    )
    assert dispatch(world) == 0 and world.sms.outbox == []


def test_여러_건을_순서대로_보내고_한_번에_집는_수를_넘으면_다음_주기가_잇는다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [outbox(world, phone=f"0101234567{n}") for n in range(3)]
    monkeypatch.setattr(jobs, "BATCH", 2)
    assert dispatch(world) == 2
    assert [state(world, t) for t in targets] == ["SS.SENDING", "SS.SENDING", "SS.WAIT"]
    assert [m.to for m in world.sms.outbox] == ["01012345670", "01012345671"]
    assert dispatch(world) == 1 and state(world, targets[2]) == "SS.SENDING"


def test_보내기_전에_시도가_먼저_확정된다(world: World) -> None:
    trgt = outbox(world)
    seen: list[tuple[str, str]] = []
    original = world.sms.send

    def watch(**kwargs: Any) -> Any:
        rows = attempts(world, trgt)
        seen.append((state(world, trgt), f"{len(rows)}:{rows[0]['PRCS_STTS_CD']}"))
        return original(**kwargs)

    world.sms.send = watch  # type: ignore[method-assign]
    dispatch(world)
    assert seen == [("SS.UNKNOWN", "1:SS.UNKNOWN")]  # 호출 시점에 이미 시도 행과 결과 확인 중이 있다


def test_후보를_읽은_뒤_다른_처리가_먼저_처리했으면_보내지_않는다(world: World) -> None:
    trgt = outbox(world)
    world.db.commit()
    taken = {"done": False}

    def clock_that_races() -> Any:
        # 항목을 잠그기 직전의 시계 호출에서 다른 처리가 같은 문자를 먼저 끝낸다
        if not taken["done"]:
            taken["done"] = True
            world.db.execute(
                text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.SENT' WHERE SMS_TRGT_SN=:t"), {"t": trgt}
            )
        return world.clock()

    assert jobs.dispatch_sms(world.db, world.settings, world.sms, world.bundle, clock_that_races) == 0
    assert world.sms.outbox == [] and attempts(world, trgt) == []


# --- 결과 조회 ----------------------------------------------------------------------------------


def sent(w: World, outcome: SendOutcome = SendOutcome.ACCEPTED) -> int:
    trgt = outbox(w)
    w.sms.next_outcome = outcome
    dispatch(w)
    w.clock.advance(minutes=1)  # 요청 직후 유예를 지난다
    return trgt


def test_조회하는_사이_다른_처리가_먼저_정했으면_덮어쓰지_않는다(world: World) -> None:
    trgt = sent(world)
    world.sms.deliveries[f"sms-{trgt}-1"] = SmsLookup(DeliveryState.DELIVERED)
    original = world.sms.lookup

    def failed_elsewhere(**kwargs: Any) -> Any:
        world.db.execute(
            text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.FAIL' WHERE SMS_TRGT_SN=:t"), {"t": trgt}
        )
        return original(**kwargs)

    world.sms.lookup = failed_elsewhere  # type: ignore[method-assign]
    recheck(world)
    # 먼저 정한 쪽을 덮어쓰지 않는다. 건너뛰는 경로의 되돌림으로 시험이 심은 변경은 사라져 SS.SENT로만 바뀌지 않으면 된다
    assert state(world, trgt) != "SS.SENT" and attempts(world, trgt)[0]["PRCS_STTS_CD"] == "SS.SENDING"


def test_접수한_문자가_전달_확인되면_발송_성공으로_바꾼다(world: World) -> None:
    trgt = sent(world)
    world.sms.deliveries[f"sms-{trgt}-1"] = SmsLookup(DeliveryState.DELIVERED)
    assert recheck(world) == 1 and state(world, trgt) == "SS.SENT"
    [attempt] = attempts(world, trgt)
    assert (
        attempt["PRCS_STTS_CD"] == "SS.SENT"
        and attempt["RSLT_IDNTY_DT"] == world.clock()
        and attempt["FAIL_CD"] is None
    )
    assert recheck(world) == 0  # 확정된 문자는 다시 조회하지 않는다


def test_전달_실패가_확인되면_실패로_바꾸고_사유를_남긴다(world: World) -> None:
    trgt = sent(world)
    world.sms.deliveries[f"sms-{trgt}-1"] = SmsLookup(DeliveryState.FAILED, "NO_SERVICE")
    assert recheck(world) == 1 and state(world, trgt) == "SS.FAIL"
    assert attempts(world, trgt)[0]["FAIL_CD"] == "NO_SERVICE"


def test_결과_불명_문자도_같은_키로_조회해_확정하고_새로_보내지_않는다(world: World) -> None:
    trgt = sent(world, SendOutcome.UNKNOWN)
    assert state(world, trgt) == "SS.UNKNOWN"
    world.sms.deliveries[f"sms-{trgt}-1"] = SmsLookup(DeliveryState.DELIVERED)
    assert recheck(world) == 1 and state(world, trgt) == "SS.SENT"
    assert len(world.sms.outbox) == 1 and world.sms.lookups == [f"sms-{trgt}-1"]


@pytest.mark.parametrize("found", [DeliveryState.PENDING, DeliveryState.UNKNOWN])
def test_아직_모르면_그대로_두고_다음에_다시_조회한다(world: World, found: DeliveryState) -> None:
    trgt = sent(world)
    world.sms.deliveries[f"sms-{trgt}-1"] = SmsLookup(found)
    assert recheck(world) == 1 and state(world, trgt) == "SS.SENDING"
    assert recheck(world) == 1 and len(world.sms.outbox) == 1


def test_조회가_실패해도_상태를_바꾸지_않는다(world: World) -> None:
    trgt = sent(world)
    world.sms.lookup_raises = True
    assert recheck(world) == 1 and state(world, trgt) == "SS.SENDING"


def test_요청_직후의_문자와_이미_확정된_문자는_조회하지_않는다(world: World) -> None:
    fresh = outbox(world)
    dispatch(world)
    world.clock.advance(seconds=29)
    assert recheck(world) == 0 and world.sms.lookups == []
    world.clock.advance(seconds=1)
    world.sms.deliveries[f"sms-{fresh}-1"] = SmsLookup(DeliveryState.DELIVERED)
    assert recheck(world) == 1
    done = outbox(world)
    world.db.execute(text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.SENT' WHERE SMS_TRGT_SN=:t"), {"t": done})
    assert recheck(world) == 0


def test_OTP_문자의_조회는_하지_않는다(world: World) -> None:
    trgt = outbox(world, event="CERT:5")
    world.db.execute(
        text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.SENDING' WHERE SMS_TRGT_SN=:t"), {"t": trgt}
    )
    world.db.execute(
        text(
            "INSERT INTO TB_SMS_SNDNG_HSTRY (OPER_BNDL_SN, SMS_TRGT_SN, SNDNG_SEQ, SPLR_NM, SPLR_ACNT_ID, IDEM_KEY, PRCS_STTS_CD, SNDNG_DMND_DT, RCRD_VER) "
            "VALUES (:b, :t, 1, 'mock', 'mock', 'otp-x', 'SS.SENDING', :d, 1)"
        ),
        {"b": world.bundle, "t": trgt, "d": START - timedelta(minutes=5)},
    )
    assert recheck(world) == 0 and world.sms.lookups == []


def test_개인정보는_문자_상태_기록에_남기지_않는다(world: World) -> None:
    trgt = outbox(world)
    dispatch(world)
    dumped = str(attempts(world, trgt)) + str(world.db.execute(text("SELECT * FROM TB_JOB_HSTRY")).all())
    assert PHONE not in dumped
