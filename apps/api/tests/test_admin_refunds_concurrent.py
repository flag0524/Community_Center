# 환불 집행·승인·접수의 동시성을 서로 다른 DB 연결로 확인하는 시험(집행 한 번, 한도 직렬화, 접수 경쟁, R14·ADR-043)
import time
from collections.abc import Callable
from typing import Any

import pytest

from tests.arena import (
    Arena,
    Staff,
    make_application,
    make_course,
    make_cycle,
    make_member,
    parallel,
)
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def paid_refund(
    f: RowFactory,
    bundle: int,
    member: int,
    course: dict[str, Any],
    status: str,
    amount: int,
    approver: int | None = None,
) -> tuple[int, int, int]:
    """결제완료 신청과 그 결제, 환불 한 건. (신청, 결제, 환불) 번호."""
    application = make_application(f, bundle, member, course, "ES.CANCEL")
    stlm = f.make(
        "TB_STLM",
        OPER_BNDL_SN=bundle,
        ATNLC_APLY_SN=application,
        STLM_STTS_CD="PS.PAID",
        STLM_AMT=30000,
        STLM_APRV_NO="A1",
        STLM_APRV_DT=START,
    )
    extra: dict[str, Any] = {} if approver is None else {"APRV_MNGR_SN": approver, "APRV_DT": START}
    refund = f.make(
        "TB_RFND",
        OPER_BNDL_SN=bundle,
        STLM_SN=stlm["STLM_SN"],
        RFND_AMT=amount,
        RFND_STTS_CD=status,
        RFND_DMND_DT=START,
        DMND_MBR_SN=member,
        **extra,
    )
    return application, int(stlm["STLM_SN"]), int(refund["RFND_SN"])


def post(who: Staff, path: str, body: dict[str, Any]) -> Callable[[], Any]:
    return lambda: who.client.request(
        "PUT" if path.endswith(("approve", "hold", "reject")) else "POST",
        f"{ADMIN}{path}",
        json=body,
        headers={"X-CSRF-Token": who.csrf},
    )


def test_같은_승인_건을_여러_담당자가_동시에_집행해도_PG_취소는_한_번이다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        return bundle, paid_refund(f, bundle, member, course, "RS.APPROVE", 30000)[2]

    bundle, refund = arena.build(build)
    arena.serve(bundle)
    approver = arena.staff(bundle, "approver", "AU.RFND_A")
    with arena.migrated.begin() as connection:
        connection.exec_driver_sql(
            f"UPDATE TB_RFND SET APRV_MNGR_SN={approver.admin_sn}, APRV_DT=NOW() WHERE RFND_SN={refund}"
        )
    executors = [arena.staff(bundle, f"exec{n}", "AU.RFND_X") for n in range(4)]
    arena.pg.cancel_delay_seconds = 0.3  # PG 응답이 늦어 다른 요청이 그 사이에 들어온다
    responses = parallel([post(e, f"/refunds/{refund}/execute", {"version": 1}) for e in executors])
    codes = sorted(("200" if r.status_code == 200 else r.json()["code"]) for r in responses)
    assert codes == ["200", "CONFLICT_STATE", "CONFLICT_STATE", "CONFLICT_STATE"], codes
    assert len(arena.pg.cancel_calls) == 1
    [row] = arena.query("SELECT RFND_STTS_CD s FROM TB_RFND WHERE RFND_SN=:r", r=refund)
    assert row["s"] == "RS.DONE"


def test_PG를_부르는_동안에는_이미_처리_중이_커밋되어_다른_연결에서_보인다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        return bundle, paid_refund(f, bundle, member, course, "RS.APPROVE", 30000)[2]

    bundle, refund = arena.build(build)
    arena.serve(bundle)
    approver = arena.staff(bundle, "approver", "AU.RFND_A")
    executor = arena.staff(bundle, "executor", "AU.RFND_X")
    with arena.migrated.begin() as connection:
        connection.exec_driver_sql(
            f"UPDATE TB_RFND SET APRV_MNGR_SN={approver.admin_sn}, APRV_DT=NOW() WHERE RFND_SN={refund}"
        )
    arena.pg.cancel_delay_seconds = 2.0  # 처음 바뀐 상태를 읽을 시간을 충분히 준다
    seen: list[str] = []

    def watch() -> Any:
        # 상태가 처음 바뀌는 순간을 본다. 집행 요청의 준비 시간은 부하에 따라 달라 고정 대기로는 맞출 수 없다
        for _ in range(160):
            now = str(arena.query("SELECT RFND_STTS_CD s FROM TB_RFND WHERE RFND_SN=:r", r=refund)[0]["s"])
            if now != "RS.APPROVE":
                seen.append(now)
                return
            time.sleep(0.05)

    run, _ = parallel([post(executor, f"/refunds/{refund}/execute", {"version": 1}), watch])
    assert run.status_code == 200 and run.json()["status"] == "DONE"
    assert seen == ["RS.PENDING"]  # 호출 중 서버가 죽어도 처리 중으로 남아 같은 키로 이어서 확인할 수 있다


def test_같은_결제의_환불_두_건을_동시에_승인해도_원결제_한도를_넘지_않는다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        _, stlm, first = paid_refund(f, bundle, member, course, "RS.REQUEST", 20000)
        second = f.make(
            "TB_RFND",
            OPER_BNDL_SN=bundle,
            STLM_SN=stlm,
            RFND_AMT=20000,
            RFND_STTS_CD="RS.REQUEST",
            RFND_DMND_DT=START,
            DMND_MBR_SN=member,
        )
        return bundle, first, int(second["RFND_SN"])

    bundle, first, second = arena.build(build)
    arena.serve(bundle)
    approvers = [arena.staff(bundle, f"appr{n}", "AU.RFND_A") for n in range(2)]
    responses = parallel(
        [
            post(approvers[0], f"/refunds/{first}/approve", {"amount": 20000, "version": 1}),
            post(approvers[1], f"/refunds/{second}/approve", {"amount": 20000, "version": 1}),
        ]
    )
    codes = sorted(("200" if r.status_code == 200 else r.json()["code"]) for r in responses)
    assert codes == ["200", "RFND_LIMIT_EXCEEDED"], codes
    [total] = arena.query("SELECT SUM(RFND_AMT) t FROM TB_RFND WHERE RFND_STTS_CD='RS.APPROVE'")
    assert int(total["t"]) == 20000


def test_같은_환불을_동시에_승인하면_한_번만_승인되고_나머지는_충돌이다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        return bundle, paid_refund(f, bundle, member, course, "RS.REQUEST", 30000)[2]

    bundle, refund = arena.build(build)
    arena.serve(bundle)
    approvers = [arena.staff(bundle, f"appr{n}", "AU.RFND_A") for n in range(4)]
    responses = parallel(
        [post(a, f"/refunds/{refund}/approve", {"amount": 30000, "version": 1}) for a in approvers]
    )
    codes = sorted(("200" if r.status_code == 200 else r.json()["code"]) for r in responses)
    assert codes == ["200", "CONFLICT_STATE", "CONFLICT_STATE", "CONFLICT_STATE"], codes


def test_회원_접수와_담당자_대리_접수가_겹쳐도_환불은_한_건만_생긴다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201", RCRT_NOPE=3)
        application = make_application(f, bundle, member, course, "ES.CONFIRM")
        f.make(
            "TB_STLM",
            OPER_BNDL_SN=bundle,
            ATNLC_APLY_SN=application,
            STLM_STTS_CD="PS.PAID",
            STLM_AMT=30000,
            STLM_APRV_NO="A1",
            STLM_APRV_DT=START,
        )
        return bundle, member, application

    bundle, member, application = arena.build(build)
    arena.serve(bundle)
    me = arena.applicant(member, bundle)
    boss = arena.staff(bundle, "boss", "AU.RFND_A")
    responses = parallel(
        [
            lambda: me.client.post(
                "/api/v1/me/refunds",
                json={"applicationId": str(application)},
                headers={"X-CSRF-Token": me.csrf, "Idempotency-Key": "member-refund-0001"},
            ),
            lambda: boss.client.post(
                f"{ADMIN}/refunds",
                json={"applicationNo": str(application), "requestedAmount": 30000, "reason": "방문"},
                headers={"X-CSRF-Token": boss.csrf, "Idempotency-Key": "admin-refund-0001"},
            ),
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_RFND")) == 1
    [row] = arena.query("SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a", a=application)
    assert row["s"] == "ES.CANCEL"
