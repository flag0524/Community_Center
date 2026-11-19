# 회원 환불 접수의 동시성을 서로 다른 DB 연결로 확인하는 시험(같은 신청 중복 접수, 같은 멱등키 재전송, 다른 신청 독립, R14·ADR-042)
from collections.abc import Callable
from typing import Any

import pytest

from tests.arena import Applicant, Arena, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db


def paid_application(f: RowFactory, bundle: int, member: int, course: dict[str, Any]) -> int:
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
    return application


def refund_call(me: Applicant, application: int, key: str) -> Callable[[], Any]:
    return lambda: me.client.post(
        "/api/v1/me/refunds",
        json={"applicationId": str(application)},
        headers={"X-CSRF-Token": me.csrf, "Idempotency-Key": key},
    )


def test_같은_신청에_다른_멱등키로_동시에_접수해도_환불은_한_건이다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        return bundle, member, paid_application(f, bundle, member, course)

    bundle, member, application = arena.build(build)
    arena.serve(bundle)
    me = arena.applicant(member, bundle)
    responses = parallel([refund_call(me, application, f"member-refund-{n:04d}") for n in range(5)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 422, 422, 422, 422], [r.text for r in responses]
    assert {r.json()["code"] for r in responses if r.status_code == 422} == {"RFND_NOT_ALLOWED"}
    [refund] = arena.query("SELECT RFND_AMT a, RFND_STTS_CD s FROM TB_RFND")
    assert (int(refund["a"]), refund["s"]) == (30000, "RS.REQUEST")
    [row] = arena.query("SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a", a=application)
    assert row["s"] == "ES.CANCEL"
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='RFND_REQUEST'")) == 1


def test_같은_멱등키를_동시에_다시_보내도_같은_환불을_돌려주고_한_건만_생긴다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
        return bundle, member, paid_application(f, bundle, member, course)

    bundle, member, application = arena.build(build)
    arena.serve(bundle)
    me = arena.applicant(member, bundle)
    responses = parallel([refund_call(me, application, "member-refund-same") for _ in range(5)])
    assert [r.status_code for r in responses] == [201] * 5, [r.text for r in responses]
    assert len({r.json()["refundId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_RFND")) == 1
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='RFND_REQUEST'")) == 1


def test_서로_다른_신청의_환불_접수는_서로_막지_않는다(arena: Arena) -> None:
    def build(f: RowFactory) -> tuple[int, int, list[int]]:
        bundle = f.bundle()
        member = make_member(f, bundle, "payer")
        cycle = make_cycle(f, bundle)
        applications = [
            paid_application(
                f, bundle, member, make_course(f, bundle, cycle, f"강좌{n}", EDU_BGNG_YMD="20261201")
            )
            for n in range(3)
        ]
        return bundle, member, applications

    bundle, member, applications = arena.build(build)
    arena.serve(bundle)
    me = arena.applicant(member, bundle)
    responses = parallel([refund_call(me, a, f"member-refund-{n:04d}") for n, a in enumerate(applications)])
    assert [r.status_code for r in responses] == [201, 201, 201], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_RFND")) == 3
    assert {r["s"] for r in arena.query("SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY")} == {"ES.CANCEL"}
