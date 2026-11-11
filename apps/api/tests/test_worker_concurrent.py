# 워커의 결제기한 만료가 동시에 돌거나 다른 처리와 겹쳐도 한 번만, 정원을 지키며 처리되는지 서로 다른 DB 연결로 확인하는 시험
import time
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.db.session import open_session
from app.worker import jobs
from tests.arena import Arena, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

LATER = START + timedelta(hours=1)  # 모든 결제기한이 지난 뒤


def build(f: RowFactory) -> tuple[int, dict[str, Any], list[int], list[int]]:
    bundle = f.bundle()
    course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201", RCRT_NOPE=3)
    holders = [
        make_application(f, bundle, make_member(f, bundle, f"h{n}"), course, "ES.HOLD") for n in range(3)
    ]
    waiters = [
        make_application(f, bundle, make_member(f, bundle, f"w{n}"), course, "ES.WAIT", seq=n + 1)
        for n in range(3)
    ]
    return bundle, course, holders, waiters


def run(arena: Arena, bundle: int) -> int:
    with open_session(arena.engine) as db:
        return jobs.expire_payments(db, arena.settings, bundle, lambda: LATER)


def states(arena: Arena, sns: list[int]) -> list[str]:
    rows = [
        arena.query("SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a", a=sn)[0] for sn in sns
    ]
    return [str(r["s"]) for r in rows]


def test_여러_워커가_동시에_돌아도_만료와_승격은_신청마다_한_번이고_정원을_지킨다(arena: Arena) -> None:
    bundle, course, holders, waiters = arena.build(build)
    arena.serve(bundle)
    totals = 0
    for _ in range(6):  # 강좌 행이 잠긴 동안 건너뛴 것은 다음 주기가 이어서 처리한다
        results = parallel([lambda: run(arena, bundle) for _ in range(4)])
        totals += sum(results)
        if not any(results):
            break
    assert totals == 3
    assert states(arena, holders) == ["ES.EXPIRE"] * 3 and states(arena, waiters) == ["ES.HOLD"] * 3
    [occupied] = arena.query(
        "SELECT COUNT(*) c FROM TB_ATNLC_APLY WHERE CORS_SN=:c AND APLY_STTS_CD IN ('ES.HOLD','ES.CONFIRM')",
        c=int(course["CORS_SN"]),
    )
    assert int(occupied["c"]) == 3
    for kind in ("APLY_EXPIRE", "APLY_PROMOTE"):
        jobs_done = arena.query(
            "SELECT TRGT_KEY_VL k FROM TB_JOB_HSTRY WHERE JOB_CD=:j AND OPER_BNDL_SN=:b", j=kind, b=bundle
        )
        keys = [r["k"] for r in jobs_done]
        assert len(keys) == 3 and len(set(keys)) == 3, (kind, keys)  # 같은 신청을 두 번 처리하지 않았다


def test_다른_처리가_강좌를_잡고_있으면_기다리지_않고_건너뛰었다가_다음_주기에_처리한다(arena: Arena) -> None:
    bundle, course, holders, _ = arena.build(build)
    arena.serve(bundle)
    with arena.migrated.connect() as holder_conn:
        tx = holder_conn.begin()
        holder_conn.execute(
            text("SELECT CORS_SN FROM TB_CORS WHERE CORS_SN=:c FOR UPDATE"), {"c": int(course["CORS_SN"])}
        )
        started = time.monotonic()
        skipped = run(arena, bundle)
        elapsed = time.monotonic() - started
        tx.rollback()
    assert skipped == 0 and elapsed < 5  # 잠금 대기 시간(기본 50초)을 기다리지 않는다
    assert states(arena, holders) == ["ES.HOLD"] * 3
    assert run(arena, bundle) == 3 and states(arena, holders) == ["ES.EXPIRE"] * 3
