# 폐강이 신청·다른 폐강과 겹쳐도 어긋나지 않는지 서로 다른 DB 연결로 확인하는 시험(ADR-047)
from typing import Any

import pytest

from tests.arena import Arena, Staff, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> tuple[int, dict[str, Any], list[int]]:
    bundle = f.bundle()
    course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201", RCRT_NOPE=10)
    members = [make_member(f, bundle, f"m{n}") for n in range(6)]
    paid = make_application(f, bundle, make_member(f, bundle, "paid"), course, "ES.CONFIRM")
    f.make(
        "TB_STLM",
        OPER_BNDL_SN=bundle,
        ATNLC_APLY_SN=paid,
        STLM_STTS_CD="PS.PAID",
        STLM_AMT=30000,
        STLM_APRV_NO="A1",
        STLM_APRV_DT=START,
    )
    return bundle, course, members


def cancel_call(who: Staff, course_sn: int) -> Any:
    return lambda: who.client.post(
        f"{ADMIN}/courses/{course_sn}/cancel-course",
        json={"reason": "정원 미달"},
        headers={"X-CSRF-Token": who.csrf},
    )


def apply_call(who: Any, course_sn: int, n: int) -> Any:
    return lambda: who.client.post(
        "/api/v1/me/applications",
        json={"courseId": str(course_sn)},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": f"edu-apply-{n}-{course_sn}"},
    )


def test_폐강과_신청이_겹쳐도_폐강_뒤에는_유효한_신청이_남지_않는다(arena: Arena) -> None:
    bundle, course, members = arena.build(build)
    arena.serve(bundle)
    sn = int(course["CORS_SN"])
    boss = arena.staff(bundle, "boss", "AU.CORS_R", "AU.CORS_W")
    applicants = [arena.applicant(m, bundle) for m in members]
    responses = parallel([cancel_call(boss, sn)] + [apply_call(a, sn, n) for n, a in enumerate(applicants)])
    assert responses[0].status_code == 200, responses[0].text
    [left] = arena.query(
        "SELECT COUNT(*) c FROM TB_ATNLC_APLY WHERE CORS_SN=:c AND APLY_STTS_CD IN ('ES.WAIT','ES.HOLD','ES.CONFIRM')",
        c=sn,
    )
    assert int(left["c"]) == 0  # 강좌 행 잠금이 둘을 직렬화한다. 폐강 뒤의 신청은 접수 중이 아니라 거절된다
    [state] = arena.query("SELECT CORS_STTS_CD s FROM TB_CORS WHERE CORS_SN=:c", c=sn)
    assert state["s"] == "CS.CANCEL"
    assert len(arena.query("SELECT 1 FROM TB_RFND WHERE RFND_STTS_CD='RS.REQUEST'")) == 1


def test_같은_강좌를_동시에_폐강해도_환불은_한_번만_접수한다(arena: Arena) -> None:
    bundle, course, _ = arena.build(build)
    arena.serve(bundle)
    sn = int(course["CORS_SN"])
    staffs = [arena.staff(bundle, f"boss{n}", "AU.CORS_R", "AU.CORS_W") for n in range(4)]
    responses = parallel([cancel_call(s, sn) for s in staffs])
    codes = sorted(("200" if r.status_code == 200 else r.json()["code"]) for r in responses)
    assert codes == ["200", "CONFLICT_STATE", "CONFLICT_STATE", "CONFLICT_STATE"], codes
    assert len(arena.query("SELECT 1 FROM TB_RFND")) == 1
