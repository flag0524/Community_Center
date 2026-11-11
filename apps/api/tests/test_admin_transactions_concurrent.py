# 결과 확인 중인 거래를 여러 담당자가 동시에 재조회·대사해도 한 번만 반영되는지 서로 다른 DB 연결로 확인하는 시험
from typing import Any

import pytest

from app.adapters.pg.base import ApproveOutcome, ApproveResult
from tests.arena import Arena, Staff, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build_pending(f: RowFactory) -> tuple[int, int, str]:
    bundle = f.bundle()
    member = make_member(f, bundle, "payer")
    course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
    application = make_application(f, bundle, member, course, "ES.HOLD")
    stlm = f.make(
        "TB_STLM", OPER_BNDL_SN=bundle, ATNLC_APLY_SN=application, STLM_STTS_CD="PS.PENDING", STLM_AMT=30000
    )
    return bundle, int(stlm["STLM_SN"]), str(stlm["STLM_NO"])


def post(who: Staff, path: str, body: dict[str, Any] | None = None) -> Any:
    return lambda: who.client.post(f"{ADMIN}{path}", json=body, headers={"X-CSRF-Token": who.csrf})


def test_여러_담당자가_동시에_재조회해도_결제는_한_번만_확정되고_사건은_한_건이다(arena: Arena) -> None:
    bundle, stlm, order_no = arena.build(build_pending)
    arena.serve(bundle)
    arena.pg.lookup_results[order_no] = ApproveResult(
        ApproveOutcome.APPROVED,
        transaction_id="tx",
        approval_no="A1",
        approved_at=START,
        order_no=order_no,
        amount=30000,
        merchant_id=arena.pg.merchant_id,
        currency="KRW",
    )
    staffs = [arena.staff(bundle, f"s{n}", "AU.STLM_R", "AU.STLM_W") for n in range(4)]
    responses = parallel([post(s, f"/transactions/{stlm}/recheck") for s in staffs])
    codes = sorted(("200" if r.status_code == 200 else r.json()["code"]) for r in responses)
    assert "200" in codes and set(codes) <= {"200", "CONFLICT_STATE"}, codes
    assert [r["s"] for r in arena.query("SELECT STLM_STTS_CD s FROM TB_STLM WHERE STLM_SN=:s", s=stlm)] == [
        "PS.PAID"
    ]
    assert (
        len(arena.query("SELECT 1 FROM TB_STLM_EVENT WHERE STLM_SN=:s AND EVENT_TYPE_CD='ET.RECON'", s=stlm))
        == 1
    )
    [row] = arena.query("SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE OPER_BNDL_SN=:b", b=bundle)
    assert row["s"] == "ES.CONFIRM"


def test_재조회와_수동_대사가_겹쳐도_한쪽만_반영된다(arena: Arena) -> None:
    bundle, stlm, order_no = arena.build(build_pending)
    arena.serve(bundle)
    arena.pg.lookup_results[order_no] = ApproveResult(ApproveOutcome.REJECTED, failure_code="X")
    first = arena.staff(bundle, "s1", "AU.STLM_R", "AU.STLM_W")
    second = arena.staff(bundle, "s2", "AU.STLM_R", "AU.STLM_W")
    body = {"outcome": "PAID", "approvalNo": "A9", "evidence": "PG 화면에서 확인함", "version": 1}
    responses = parallel(
        [
            post(first, f"/transactions/{stlm}/recheck"),
            post(second, f"/transactions/{stlm}/manual-reconcile", body),
        ]
    )
    [row] = arena.query("SELECT STLM_STTS_CD s FROM TB_STLM WHERE STLM_SN=:s", s=stlm)
    assert row["s"] in ("PS.PAID", "PS.FAIL")
    assert (
        len(arena.query("SELECT 1 FROM TB_STLM_EVENT WHERE STLM_SN=:s AND EVENT_TYPE_CD='ET.RECON'", s=stlm))
        == 1
    )
    assert sorted(r.status_code for r in responses)[0] == 200
