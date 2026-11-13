# 같은 지원서를 두 담당자가 동시에 심사해도 한 번만 반영되고 강사 행이 하나만 생기는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app.domain.admin import instructor_review_service as service
from tests.arena import Arena, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def test_같은_지원서를_동시에_승인해도_한_번만_반영하고_강사는_하나다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        return bundle, make_member(f, bundle, "applicant")

    bundle, member = arena.build(build)
    arena.serve(bundle)
    one = arena.staff(bundle, "one", "AU.INSTR_W")
    two = arena.staff(bundle, "two", "AU.INSTR_W")
    with arena.migrated.begin() as connection:
        f = RowFactory(connection, arena.schema)
        board = f.make("TB_BBS", OPER_BNDL_SN=bundle)
        pst = f.make(
            "TB_PST",
            OPER_BNDL_SN=bundle,
            BBS_SN=board["BBS_SN"],
            PST_TTL="강사 모집",
            PST_CN="본문",
            REG_DT=START,
        )
        rcrt = f.make("TB_INSTR_RCRT", OPER_BNDL_SN=bundle, PST_SN=pst["PST_SN"])
        aply = f.make(
            "TB_INSTR_APLY",
            OPER_BNDL_SN=bundle,
            INSTR_RCRT_SN=rcrt["INSTR_RCRT_SN"],
            RCPT_CHNL_CD="IC.VISIT",
            MBR_SN=member,
            APLCT_NM="동시지원",
            TELNO_ENCPT_VL="x",
            HOPE_CORS_NM="서예",
            RLS_HOPE_YN="N",
            SBMSN_DT=START,
            SRNG_STTS_CD="IA.WAIT",
        )
    real = service._approve_instructor

    def slow(*args: Any) -> int:
        result = int(real(*args))
        time.sleep(
            0.5
        )  # 강사를 만들고 저장하기 전의 틈을 넓힌다. 지원서 행 잠금이 없으면 둘 다 이 틈에 들어온다
        return result

    monkeypatch.setattr(service, "_approve_instructor", slow)

    def decide(who: Any) -> Any:
        return lambda: who.client.put(
            f"{ADMIN}/instructor-applications/{aply['INSTR_APLY_SN']}",
            json={"status": "APPROVED", "reason": None, "isPublic": True, "memo": None, "version": 1},
            headers={"X-CSRF-Token": who.csrf},
        )

    responses = parallel([decide(one), decide(two)])
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_INSTR WHERE MBR_SN=:m", m=member)) == 1
    [state] = arena.query(
        "SELECT SRNG_STTS_CD s, RCRD_VER v FROM TB_INSTR_APLY WHERE INSTR_APLY_SN=:s", s=aply["INSTR_APLY_SN"]
    )
    assert (state["s"], state["v"]) == ("IA.APPROVE", 2)
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_REVIEW'")) == 1
