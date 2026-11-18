# 매일 새벽 자동 정리가 동시에 두 번 돌아도 같은 대상을 두 번 처리하지 않는지 서로 다른 DB 연결로 확인하는 시험
import time
from datetime import timedelta
from typing import Any

import pytest

from app.db.session import open_session
from app.domain.admin import retention_service
from app.worker import retention
from tests.arena import Arena, parallel
from tests.world import START

pytestmark = pytest.mark.db


def build(f: Any) -> int:
    bundle = int(f.bundle())
    for n in range(3):
        f.make(
            "TB_MBR",
            OPER_BNDL_SN=bundle,
            LGN_ID=f"gone{n}",
            PSWD_HASH_VL="x" * 20,
            MBR_NM="탈퇴자",
            MBL_TELNO="01012345678",
            MBR_STTS_CD="MS.WITHDRAW",
            WHDWL_DT=START - timedelta(days=60),
        )
    return bundle


def test_동시에_두_번_돌아도_한_번만_처리하고_이력도_한_건이다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = arena.build(build)
    real = retention_service._apply

    def slow(*args: Any) -> Any:
        real(*args)
        time.sleep(0.5)  # 처리한 뒤 커밋 전에 머물러 두 번째 실행이 같은 행을 보게 한다

    monkeypatch.setattr(retention_service, "_apply", slow)

    def once() -> int:
        with open_session(arena.engine) as session:
            return retention.purge_due(session, bundle, lambda: START)

    first, second = parallel([once, once])
    assert sorted([first, second]) == [0, 3]  # 행 잠금이 있어 한쪽만 처리한다
    jobs = arena.query(
        "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='RETENTION_EXECUTE'", b=bundle
    )
    done = arena.query("SELECT COUNT(*) n FROM TB_MBR WHERE OPER_BNDL_SN=:b AND MBR_NM='탈퇴회원'", b=bundle)
    assert (jobs[0]["n"], done[0]["n"]) == (1, 3)
