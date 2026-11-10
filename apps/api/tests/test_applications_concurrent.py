# 수강신청 생성·취소의 동시성을 서로 다른 DB 연결 여러 개로 확인하는 시험(정원 초과·이중 신청·감면 중복 0건, ADR-028·038·039)
from typing import Any

import pytest
from sqlalchemy import text

from tests.arena import (
    Arena,
    attempt,
    cancel_call,
    make_application,
    make_course,
    make_cycle,
    make_member,
    outcome,
    parallel,
)
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db


def test_운영_엔진은_READ_COMMITTED로_연결한다(arena: Arena) -> None:
    with arena.engine.connect() as connection:
        level = connection.execute(text("SELECT @@tx_isolation")).scalar_one()
    assert level == "READ-COMMITTED"


def test_정원보다_많은_사람이_동시에_신청해도_정원을_넘기지_않고_대기도_넘기지_않는다(arena: Arena) -> None:
    people, rounds, capacity, waiting = 12, 4, 3, 4

    def make(f: RowFactory) -> tuple[int, list[int], list[dict[str, Any]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        courses = [
            make_course(f, bundle, cycle, f"강좌{n}", RCRT_NOPE=capacity, WTNG_NOPE=waiting)
            for n in range(rounds)
        ]
        return bundle, [make_member(f, bundle, f"m{n}") for n in range(people)], courses

    bundle, members, courses = arena.build(make)
    arena.serve(bundle)
    applicants = [arena.applicant(sn, bundle) for sn in members]
    for round_number, course in enumerate(courses):
        responses = parallel(
            [
                attempt(who, course["CORS_SN"], f"r{round_number}-p{n}-key-0001")
                for n, who in enumerate(applicants)
            ]
        )
        codes = [outcome(r) for r in responses]
        assert codes.count("201") == capacity + waiting, codes
        assert codes.count("APLY_FULL") == people - capacity - waiting, codes
        rows = arena.query(
            "SELECT APLY_STTS_CD, WTNG_SEQ FROM TB_ATNLC_APLY WHERE CORS_SN = :c", c=course["CORS_SN"]
        )
        seated = [r for r in rows if r["APLY_STTS_CD"] in ("ES.HOLD", "ES.CONFIRM")]
        queued = sorted(int(r["WTNG_SEQ"]) for r in rows if r["APLY_STTS_CD"] == "ES.WAIT")
        assert len(seated) == capacity  # 정원 초과·이중 배정 0건
        assert queued == list(range(1, waiting + 1))  # 대기 순서는 겹치지 않고 빈틈이 없다


def test_한_사람이_다른_키로_연타해도_신청은_하나만_생긴다(arena: Arena) -> None:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌")
        return bundle, make_member(f, bundle, "single"), int(course["CORS_SN"])

    bundle, member, course_sn = arena.build(make)
    arena.serve(bundle)
    devices = [arena.applicant(member, bundle) for _ in range(8)]  # 요청마다 다른 기기(세션)
    responses = parallel([attempt(d, course_sn, f"click-{n}-key-0001") for n, d in enumerate(devices)])
    codes = sorted(outcome(r) for r in responses)
    assert codes == ["201"] + ["APLY_ALREADY_APPLIED"] * 7
    assert len(arena.query("SELECT 1 FROM TB_ATNLC_APLY")) == 1


def test_같은_키로_동시에_재전송하면_모두_같은_결과이고_신청은_하나다(arena: Arena) -> None:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌")
        return bundle, make_member(f, bundle, "retry"), int(course["CORS_SN"])

    bundle, member, course_sn = arena.build(make)
    arena.serve(bundle)
    devices = [arena.applicant(member, bundle) for _ in range(8)]
    responses = parallel([attempt(d, course_sn, "same-key-0001") for d in devices])
    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["applicationId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_ATNLC_APLY")) == 1
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_CREATE'")) == 1


def test_같은_키를_다른_강좌에_동시에_쓰면_하나만_성공하고_하나는_409다(arena: Arena) -> None:
    rounds = 5

    def make(f: RowFactory) -> tuple[int, int, list[tuple[int, int]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        pairs = [
            (
                int(make_course(f, bundle, cycle, f"가{n}")["CORS_SN"]),
                int(make_course(f, bundle, cycle, f"나{n}")["CORS_SN"]),
            )
            for n in range(rounds)
        ]
        return bundle, make_member(f, bundle, "twin"), pairs

    bundle, member, pairs = arena.build(make)
    arena.serve(bundle)
    phone, laptop = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, (one, two) in enumerate(pairs):
        key = f"shared-{n}-key-0001"
        responses = parallel([attempt(phone, one, key), attempt(laptop, two, key)])
        codes = sorted(outcome(r) for r in responses)
        assert codes == ["201", "IDEMPOTENCY_CONFLICT"], codes
    assert len(arena.query("SELECT 1 FROM TB_ATNLC_APLY")) == rounds


def test_서로_다른_회원이_다른_강좌에_같은_키를_동시에_쓰면_하나만_성공한다(arena: Arena) -> None:
    rounds = 8

    def make(f: RowFactory) -> tuple[int, list[int], list[tuple[int, int]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        pairs = [
            (
                int(make_course(f, bundle, cycle, f"가{n}")["CORS_SN"]),
                int(make_course(f, bundle, cycle, f"나{n}")["CORS_SN"]),
            )
            for n in range(rounds)
        ]
        return bundle, [make_member(f, bundle, "alice"), make_member(f, bundle, "bob")], pairs

    bundle, (alice, bob), pairs = arena.build(make)
    arena.serve(bundle)
    first, second = arena.applicant(alice, bundle), arena.applicant(bob, bundle)
    for n, (one, two) in enumerate(pairs):
        # 회원도 강좌도 달라 잠금이 겹치지 않는다. 멱등키 유일키(DB)가 마지막으로 막아야 한다
        key = f"cross-{n}-key-0001"
        responses = parallel([attempt(first, one, key), attempt(second, two, key)])
        assert sorted(outcome(r) for r in responses) == ["201", "IDEMPOTENCY_CONFLICT"]
    assert len(arena.query("SELECT 1 FROM TB_ATNLC_APLY")) == rounds


def test_같은_회원이_같은_기수의_두_강좌에_동시에_신청해도_감면은_한_번만_쓴다(arena: Arena) -> None:
    rounds = 12

    def make(f: RowFactory) -> tuple[int, int, list[tuple[int, int]]]:
        bundle = f.bundle()
        member = make_member(f, bundle, "reduced")
        admin = int(
            f.make("TB_MNGR", LGN_ID="conc-reviewer", PSWD_HASH_VL="x" * 20, MNGR_NM="심사")["MNGR_SN"]
        )
        arena.admins.append(admin)
        pairs = []
        for n in range(rounds):
            cycle = make_cycle(f, bundle, number=10 + n)
            f.make(
                "TB_RDCT_BFHD_SRNG",
                OPER_BNDL_SN=bundle,
                MBR_SN=member,
                EDU_CYCL_SN=cycle["EDU_CYCL_SN"],
                RDCT_TYPE_CD="DR.LIVELIHD",
                SRNG_STTS_CD="DS.APPROVED",
                SRNG_MNGR_SN=admin,
                SRNG_DT=START,
            )
            pairs.append(
                (
                    int(make_course(f, bundle, cycle, f"가{n}", TTCHG=100000)["CORS_SN"]),
                    int(make_course(f, bundle, cycle, f"나{n}", TTCHG=100000)["CORS_SN"]),
                )
            )
        return bundle, member, pairs

    bundle, member, pairs = arena.build(make)
    arena.serve(bundle)
    # 같은 회원의 서로 다른 기기(세션). 한 세션이면 세션 행 갱신이 요청을 먼저 직렬화해 경쟁이 가려진다
    phone, laptop = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, (one, two) in enumerate(pairs):
        responses = parallel(
            [
                attempt(phone, one, f"red-{n}-a-key-0001"),
                attempt(laptop, two, f"red-{n}-b-key-0001"),
            ]
        )
        assert {r.status_code for r in responses} == {201}
        payable = sorted(r.json()["payableAmount"] for r in responses)
        assert payable == [50000, 100000], payable  # 한 강좌만 감면을 받는다
    assert len(arena.query("SELECT 1 FROM TB_RDCT_HSTRY WHERE DCSN_RSLT_CD = 'DR.APPROVE'")) == rounds


# --- 취소와 승격 --------------------------------------------------------------------------------


def test_두_보유자가_동시에_취소하면_대기자_둘이_순서대로_승격하고_정원을_넘기지_않는다(arena: Arena) -> None:
    rounds, capacity = 6, 2

    def make(
        f: RowFactory,
    ) -> tuple[int, list[int], list[int], list[tuple[dict[str, Any], list[int], list[int]]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        holders = [make_member(f, bundle, f"h{n}") for n in range(capacity)]
        waiters = [make_member(f, bundle, f"w{n}") for n in range(4)]
        courses = []
        for n in range(rounds):
            course = make_course(
                f, bundle, cycle, f"강좌{n}", RCRT_NOPE=capacity, WTNG_NOPE=5, EDU_BGNG_YMD="20261201"
            )
            held = [make_application(f, bundle, m, course, "ES.HOLD") for m in holders]
            queue = [
                make_application(f, bundle, m, course, "ES.WAIT", seq) for seq, m in enumerate(waiters, 1)
            ]
            courses.append((course, held, queue))
        return bundle, holders, waiters, courses

    bundle, holders, _, courses = arena.build(make)
    arena.serve(bundle)
    devices = [arena.applicant(m, bundle) for m in holders]
    for course, held, queue in courses:
        responses = parallel([cancel_call(d, sn) for d, sn in zip(devices, held, strict=True)])
        assert {r.status_code for r in responses} == {200}
        rows = {
            int(r["ATNLC_APLY_SN"]): r["APLY_STTS_CD"]
            for r in arena.query(
                "SELECT ATNLC_APLY_SN, APLY_STTS_CD FROM TB_ATNLC_APLY WHERE CORS_SN = :c",
                c=course["CORS_SN"],
            )
        }
        assert [rows[sn] for sn in queue] == ["ES.HOLD", "ES.HOLD", "ES.WAIT", "ES.WAIT"]  # 순서대로 둘만
        assert sum(1 for s in rows.values() if s in ("ES.HOLD", "ES.CONFIRM")) == capacity
    events = arena.query("SELECT SRC_EVENT_ID FROM TB_SMS_DMND")
    assert len(events) == 2 * rounds and len({e["SRC_EVENT_ID"] for e in events}) == 2 * rounds


def test_같은_신청을_여러_기기에서_동시에_취소해도_한_번만_반환하고_승격도_한_번이다(arena: Arena) -> None:
    def make(f: RowFactory) -> tuple[int, int, int, list[int]]:
        bundle = f.bundle()
        course = make_course(
            f, bundle, make_cycle(f, bundle), "강좌", RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261201"
        )
        holder = make_member(f, bundle, "holder")
        held = make_application(f, bundle, holder, course, "ES.HOLD")
        queue = [
            make_application(f, bundle, make_member(f, bundle, f"w{n}"), course, "ES.WAIT", n)
            for n in range(1, 4)
        ]
        return bundle, holder, held, queue

    bundle, holder, held, queue = arena.build(make)
    arena.serve(bundle)
    devices = [arena.applicant(holder, bundle) for _ in range(8)]
    responses = parallel([cancel_call(d, held) for d in devices])
    assert {r.status_code for r in responses} == {200}
    states = {int(r["ATNLC_APLY_SN"]): r["APLY_STTS_CD"] for r in arena.query("SELECT * FROM TB_ATNLC_APLY")}
    assert [states[sn] for sn in queue] == ["ES.HOLD", "ES.WAIT", "ES.WAIT"]
    assert len(arena.query("SELECT 1 FROM TB_SMS_DMND")) == 1
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_CANCEL'")) == 1


def test_취소하는_동안_새로_신청한_사람은_대기자를_앞지르지_못한다(arena: Arena) -> None:
    rounds, newcomers = 4, 5

    def make(f: RowFactory) -> tuple[int, int, list[int], list[tuple[dict[str, Any], int, int]]]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        holder, first = make_member(f, bundle, "holder"), make_member(f, bundle, "first")
        others = [make_member(f, bundle, f"new{n}") for n in range(newcomers)]
        courses = []
        for n in range(rounds):
            course = make_course(
                f, bundle, cycle, f"강좌{n}", RCRT_NOPE=1, WTNG_NOPE=10, EDU_BGNG_YMD="20261201"
            )
            courses.append(
                (
                    course,
                    make_application(f, bundle, holder, course, "ES.HOLD"),
                    make_application(f, bundle, first, course, "ES.WAIT", 1),
                )
            )
        return bundle, holder, others, courses

    bundle, holder, others, courses = arena.build(make)
    arena.serve(bundle)
    holder_device = arena.applicant(holder, bundle)
    devices = [arena.applicant(m, bundle) for m in others]
    for n, (course, held, first_wait) in enumerate(courses):
        calls = [cancel_call(holder_device, held)] + [
            attempt(d, int(course["CORS_SN"]), f"race-{n}-{i}-key-0001") for i, d in enumerate(devices)
        ]
        responses = parallel(calls)
        assert responses[0].status_code == 200
        assert {r.status_code for r in responses[1:]} == {201}  # 대기 정원이 넉넉해 모두 대기로 들어간다
        rows = arena.query(
            "SELECT ATNLC_APLY_SN, APLY_STTS_CD, WTNG_SEQ FROM TB_ATNLC_APLY WHERE CORS_SN = :c",
            c=course["CORS_SN"],
        )
        seated = [int(r["ATNLC_APLY_SN"]) for r in rows if r["APLY_STTS_CD"] in ("ES.HOLD", "ES.CONFIRM")]
        assert seated == [first_wait]  # 자리는 먼저 기다린 사람이 가진다
        queued = sorted(int(r["WTNG_SEQ"]) for r in rows if r["APLY_STTS_CD"] == "ES.WAIT")
        assert (
            len(queued) == newcomers and len(set(queued)) == newcomers
        )  # 새로 들어온 사람 모두 순서가 겹치지 않는다
