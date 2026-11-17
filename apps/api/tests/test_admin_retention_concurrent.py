# 같은 대상의 파기 실행이 동시에 와도 한 번만 처리되는지 서로 다른 DB 연결로 확인하는 시험
import time
from datetime import timedelta
from typing import Any

import pytest

from app.domain.admin import retention_service
from tests.arena import Arena, Staff, parallel
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


def send(who: Staff, key: str, count: int) -> Any:
    return who.client.post(
        "/api/admin/v1/retention/1/execute",
        json={"expectedCount": count},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key},
    )


def test_다른_키로_동시에_실행해도_한_번만_처리하고_나머지는_409이다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = arena.build(build)
    arena.serve(bundle)
    real = retention_service._replayed

    def slow(*args: Any) -> Any:
        time.sleep(0.5)  # 잠근 뒤에 머물러 두 요청이 모두 안에 들어와 있게 한다
        return real(*args)

    monkeypatch.setattr(retention_service, "_replayed", slow)
    one, two = (arena.staff(bundle, f"r{n}", "AU.LOG_R", "AU.GRANT_W") for n in range(2))
    responses = parallel(
        [lambda: send(one, "retention-conc-0001", 3), lambda: send(two, "retention-conc-0002", 3)]
    )
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    done = arena.query("SELECT COUNT(*) n FROM TB_MBR WHERE OPER_BNDL_SN=:b AND MBR_NM='탈퇴회원'", b=bundle)
    jobs = arena.query(
        "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='RETENTION_EXECUTE'", b=bundle
    )
    assert (done[0]["n"], jobs[0]["n"]) == (3, 1)
