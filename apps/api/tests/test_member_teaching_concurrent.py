# 같은 회차의 출석을 서로 다른 DB 연결로 동시에 저장해도 출석부가 하나이고 한 수정만 반영되는지 확인하는 시험
from collections.abc import Callable
from typing import Any

import pytest

from tests.arena import (
    Applicant,
    Arena,
    make_application,
    make_course,
    make_cycle,
    make_member,
    parallel,
)
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ROUNDS = 6
URL = "/api/v1/me/teaching/attendance"


def prepare(arena: Arena) -> tuple[int, int, list[tuple[dict[str, Any], str]]]:
    """승인 강사 한 명과, 회차마다 쓸 강좌(수강생 한 명, 월요일 일정)들. (묶음, 강사 회원, [(요청, 신청)])"""

    def make(f: RowFactory) -> tuple[int, int, list[tuple[dict[str, Any], str]]]:
        bundle = f.bundle()
        member = make_member(f, bundle, "teacher")
        approver = int(
            f.make("TB_MNGR", LGN_ID="att-approver", PSWD_HASH_VL="x" * 20, MNGR_NM="승인")["MNGR_SN"]
        )
        arena.admins.append(approver)
        instructor = f.make(
            "TB_INSTR",
            OPER_BNDL_SN=bundle,
            MBR_SN=member,
            INSTR_STTS_CD="IS.APPROVE",
            APRV_DT=START,
            APRV_MNGR_SN=approver,
        )
        cycle = make_cycle(f, bundle)
        lessons = []
        for n in range(ROUNDS):
            course = make_course(f, bundle, cycle, f"강좌{n}", INSTR_SN=instructor["INSTR_SN"])
            schedule = f.make(
                "TB_CORS_SCHDL",
                OPER_BNDL_SN=bundle,
                CORS_SN=course["CORS_SN"],
                DOW_CD="DW.MON",
                BGNG_TM="100000",
                END_TM="120000",
                APLCN_BGNG_YMD="20261102",
                APLCN_END_YMD="20261228",
            )
            student = make_member(f, bundle, f"student{n}")
            application = make_application(f, bundle, student, course, "ES.CONFIRM")
            body = {
                "courseId": str(course["CORS_SN"]),
                "scheduleId": str(schedule["CORS_SCHDL_SN"]),
                "classDate": "2026-11-09",
                "confirmed": True,
            }
            lessons.append((body, str(application)))
        return bundle, member, lessons

    result: tuple[int, int, list[tuple[dict[str, Any], str]]] = arena.build(make)
    return result


def creating(
    who: Applicant, body: dict[str, Any], application: str, mark: str, idem: str
) -> Callable[[], Any]:
    payload = {**body, "marks": [{"applicationId": application, "mark": mark}]}
    headers = {"X-CSRF-Token": who.csrf, "Idempotency-Key": idem}
    return lambda: who.client.post(URL, json=payload, headers=headers)


def updating(who: Applicant, sheet: str, application: str, mark: str) -> Callable[[], Any]:
    payload = {"version": 1, "confirmed": True, "marks": [{"applicationId": application, "mark": mark}]}
    return lambda: who.client.put(f"{URL}/{sheet}", json=payload, headers={"X-CSRF-Token": who.csrf})


def test_같은_회차를_동시에_저장해도_출석부는_하나이고_수정은_한_번만_반영한다(arena: Arena) -> None:
    bundle, member, lessons = prepare(arena)
    arena.serve(bundle)
    first, second = arena.applicant(member, bundle), arena.applicant(member, bundle)
    for n, (body, application) in enumerate(lessons):
        made = parallel(
            [
                creating(first, body, application, "PRESENT", f"att-{n}-a-0001"),
                creating(second, body, application, "ABSENT", f"att-{n}-b-0001"),
            ]
        )
        assert sorted(r.status_code for r in made) == [201, 409], [r.text for r in made]
        sheet = next(r.json()["attendanceId"] for r in made if r.status_code == 201)
        changed = parallel(
            [updating(first, sheet, application, "PRESENT"), updating(second, sheet, application, "ABSENT")]
        )
        assert sorted(r.status_code for r in changed) == [200, 409], [r.text for r in changed]
        [row] = arena.query("SELECT RCRD_VER v FROM TB_CORS_ATND WHERE ATND_SN = :s", s=int(sheet))
        assert int(row["v"]) == 2
    assert len(arena.query("SELECT 1 FROM TB_CORS_ATND")) == ROUNDS


def test_같은_키로_동시에_보내면_같은_출석부를_돌려준다(arena: Arena) -> None:
    bundle, member, lessons = prepare(arena)
    arena.serve(bundle)
    devices = [arena.applicant(member, bundle) for _ in range(4)]
    body, application = lessons[0]
    made = parallel([creating(d, body, application, "PRESENT", "att-same-0001") for d in devices])
    assert {r.status_code for r in made} == {201}, [r.text for r in made]
    assert len({r.json()["attendanceId"] for r in made}) == 1
    assert len(arena.query("SELECT 1 FROM TB_CORS_ATND_DTL")) == 1
