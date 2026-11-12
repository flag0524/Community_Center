# 워커의 문자 발송이 동시에 돌아도 한 문자를 한 번만 보내는지 서로 다른 DB 연결로 확인하는 시험
import hashlib
import time

import pytest
from sqlalchemy import text

from app.adapters.sms.mock import MockSmsSender
from app.auth.crypto import encrypt
from app.db.session import open_session
from app.worker import jobs
from tests.arena import Arena, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

COUNT = 8


def run(arena: Arena, sender: MockSmsSender, bundle: int) -> int:
    with open_session(arena.engine) as db:
        return jobs.dispatch_sms(db, arena.settings, sender, bundle, lambda: START)


def seed(f: RowFactory, arena: Arena, count: int) -> int:
    bundle = f.bundle()
    for n in range(count):
        member = make_member(f, bundle, f"s{n}")
        request = f.make(
            "TB_SMS_DMND",
            OPER_BNDL_SN=bundle,
            DMND_TYPE_CD="SM.AUTO",
            DMND_MNGR_SN=None,  # 자동 문자는 담당자가 없다. 팩토리가 관리자를 만들어 남기지 않게 한다
            TRGT_TYPE_CD="SG.EVENT",
            DSPTCH_TELNO="0319400000",
            SMS_CN="안내",
            IDEM_KEY=f"promo-{n}",
            DMND_HASH_VL=hashlib.sha256(b"x").hexdigest(),
            SRC_EVENT_ID=f"PROMO:{n}",
        )
        f.make(
            "TB_SMS_TRGT",
            OPER_BNDL_SN=bundle,
            SMS_DMND_SN=request["SMS_DMND_SN"],
            MBR_SN=member,
            RCPTN_TELNO_ENCPT_VL=encrypt(arena.settings.secret_key, f"0101234{n:04d}"),
            TRGT_STTS_CD="SS.WAIT",
        )
    return bundle


def test_발송_호출_중에는_다른_연결에서도_시도와_결과_확인_중이_보인다(arena: Arena) -> None:
    bundle = arena.build(lambda f: seed(f, arena, 1))
    sender = MockSmsSender()
    seen: list[tuple[str, str]] = []
    original = sender.send

    def watch(**kwargs: object) -> object:
        [target] = arena.query("SELECT TRGT_STTS_CD s FROM TB_SMS_TRGT WHERE OPER_BNDL_SN=:b", b=bundle)
        [attempt] = arena.query(
            "SELECT PRCS_STTS_CD s FROM TB_SMS_SNDNG_HSTRY WHERE OPER_BNDL_SN=:b", b=bundle
        )
        seen.append((str(target["s"]), str(attempt["s"])))
        return original(**kwargs)  # type: ignore[arg-type]

    sender.send = watch  # type: ignore[method-assign,assignment]
    assert run(arena, sender, bundle) == 1
    assert seen == [("SS.UNKNOWN", "SS.UNKNOWN")]  # 호출 전에 커밋돼 있어 죽어도 새로 보내지 않고 조회한다


def test_다른_처리가_수신대상을_잡고_있으면_기다리지_않고_건너뛴다(arena: Arena) -> None:
    bundle = arena.build(lambda f: seed(f, arena, 2))
    sender = MockSmsSender()
    [first, _] = arena.query(
        "SELECT SMS_TRGT_SN s FROM TB_SMS_TRGT WHERE OPER_BNDL_SN=:b ORDER BY 1", b=bundle
    )
    with arena.migrated.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("SELECT SMS_TRGT_SN FROM TB_SMS_TRGT WHERE SMS_TRGT_SN=:t FOR UPDATE"), {"t": first["s"]}
        )
        started = time.monotonic()
        sent = run(arena, sender, bundle)
        elapsed = time.monotonic() - started
        tx.rollback()
    assert sent == 1 and len(sender.outbox) == 1 and elapsed < 5  # 잠긴 한 건은 건너뛰고 나머지를 보낸다
    assert run(arena, sender, bundle) == 1 and len(sender.outbox) == 2


def test_여러_워커가_동시에_보내도_문자마다_한_번만_나간다(arena: Arena) -> None:
    def build(f: RowFactory) -> int:
        bundle = f.bundle()
        for n in range(COUNT):
            member = make_member(f, bundle, f"s{n}")
            request = f.make(
                "TB_SMS_DMND",
                OPER_BNDL_SN=bundle,
                DMND_TYPE_CD="SM.AUTO",
                DMND_MNGR_SN=None,  # 자동 문자는 담당자가 없다. 팩토리가 관리자를 만들어 남기지 않게 한다
                TRGT_TYPE_CD="SG.EVENT",
                DSPTCH_TELNO="0319400000",
                SMS_CN="안내",
                IDEM_KEY=f"promo-{n}",
                DMND_HASH_VL=hashlib.sha256(b"x").hexdigest(),
                SRC_EVENT_ID=f"PROMO:{n}",
            )
            f.make(
                "TB_SMS_TRGT",
                OPER_BNDL_SN=bundle,
                SMS_DMND_SN=request["SMS_DMND_SN"],
                MBR_SN=member,
                RCPTN_TELNO_ENCPT_VL=encrypt(arena.settings.secret_key, f"0101234{n:04d}"),
                TRGT_STTS_CD="SS.WAIT",
            )
        return bundle

    bundle = arena.build(build)
    sender = MockSmsSender()
    for _ in range(4):
        results = parallel([lambda: run(arena, sender, bundle) for _ in range(4)])
        if not any(results):
            break
    assert sorted(m.to for m in sender.outbox) == [f"0101234{n:04d}" for n in range(COUNT)]  # 모두 한 번씩
    [rows] = arena.query(
        "SELECT COUNT(*) c, COUNT(DISTINCT SMS_TRGT_SN) d FROM TB_SMS_SNDNG_HSTRY WHERE OPER_BNDL_SN=:b",
        b=bundle,
    )
    assert (int(rows["c"]), int(rows["d"])) == (COUNT, COUNT)
    [states] = arena.query(
        "SELECT COUNT(*) c FROM TB_SMS_TRGT WHERE OPER_BNDL_SN=:b AND TRGT_STTS_CD='SS.SENDING'", b=bundle
    )
    assert int(states["c"]) == COUNT
