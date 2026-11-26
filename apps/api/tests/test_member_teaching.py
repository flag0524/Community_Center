# 강사의 출석 입력(담당·회차, 가린 명단, 생성·수정, 저장 직전 재검증, 이력)을 실제 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import application, open_course, sign_in
from tests.world import MEMBER, START, World, make_admin, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)
# 시험 시각은 2026-11-09(월) 18:00 KST다
MON1, MON2, MON3, TODAY, NEXT = "2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09", "2026-11-16"
ROSTER_CHANGED = "명단이 변경되었습니다. 다시 불러온 뒤 저장하세요."


def key() -> str:
    return f"teach-key-{next(_n):06d}"


def rows(w: World, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in w.db.execute(text(sql), params).mappings()]


def instructor(w: World, member: dict[str, Any], state: str = "IS.APPROVE") -> dict[str, Any]:
    return w.factory.make(
        "TB_INSTR",
        MBR_SN=member["MBR_SN"],
        INSTR_STTS_CD=state,
        RLS_YN="N",
        APRV_DT=START,
        APRV_MNGR_SN=make_admin(w, f"ap{next(_n)}")["MNGR_SN"],
    )


def taught(w: World, who: dict[str, Any], **values: Any) -> dict[str, Any]:
    """월요일 10:00~12:00 정규 일정이 하나 있는 담당 강좌."""
    defaults = {"INSTR_SN": who["INSTR_SN"], "EDU_BGNG_YMD": "20261019", "EDU_END_YMD": "20261228"}
    course = open_course(w, **{**defaults, **values})
    course["schedule"] = schedule(w, course)
    return course


def schedule(w: World, course: dict[str, Any], start: str = "100000", end: str = "120000") -> dict[str, Any]:
    return w.factory.make(
        "TB_CORS_SCHDL",
        CORS_SN=course["CORS_SN"],
        DOW_CD="DW.MON",
        BGNG_TM=start,
        END_TM=end,
        APLCN_BGNG_YMD="20261019",
        APLCN_END_YMD="20261228",
    )


def changed(w: World, course: dict[str, Any], original: str, **values: Any) -> dict[str, Any]:
    defaults = {
        "CORS_SN": course["CORS_SN"],
        "CORS_SCHDL_SN": course["schedule"]["CORS_SCHDL_SN"],
        "ORGNL_LCTR_YMD": original,
        "CHG_TYPE_CD": "SC.CANCEL",
        "APLCN_YN": "Y",
    }
    return w.factory.make("TB_CORS_SCHDL_CHG", **{**defaults, **values})


def student(w: World, course: dict[str, Any], name: str, state: str = "ES.CONFIRM") -> str:
    member = make_member(w, f"s{next(_n)}", MBR_NM=name)
    return str(application(w, member, course, state)["ATNLC_APLY_SN"])


def me_teaching(w: World) -> tuple[dict[str, Any], dict[str, Any]]:
    """로그인한 승인 강사."""
    member = sign_in(w, f"teacher{next(_n)}", MBR_NM="박강사")
    return member, instructor(w, member)


def csrf(w: World) -> dict[str, str]:
    return {"X-CSRF-Token": str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])}


def courses(w: World) -> list[dict[str, Any]]:
    response = w.client.get(f"{MEMBER}/me/teaching/courses")
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def where(course: dict[str, Any], day: str, change: dict[str, Any] | None = None) -> dict[str, Any]:
    params = {
        "courseId": str(course["CORS_SN"]),
        "classDate": day,
        "scheduleId": str(course["schedule"]["CORS_SCHDL_SN"]),
    }
    if change is not None:
        params["changeId"] = str(change["CORS_SCHDL_CHG_SN"])
    return params


def sheet(w: World, course: dict[str, Any], day: str = TODAY, change: Any = None) -> Any:
    return w.client.get(f"{MEMBER}/me/teaching/attendance", params=where(course, day, change))


def marked(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"applicationId": a, "mark": m} for a, m in pairs]


def create(
    w: World,
    course: dict[str, Any],
    entries: list[dict[str, str]],
    day: str = TODAY,
    idem: str | None = None,
    change: Any = None,
    confirmed: bool = True,
) -> Any:
    body = {**where(course, day, change), "confirmed": confirmed, "marks": entries}
    return w.client.post(
        f"{MEMBER}/me/teaching/attendance",
        json=body,
        headers={**csrf(w), "Idempotency-Key": idem or key()},
    )


def update(
    w: World, attendance_id: str, version: int, entries: list[dict[str, str]], confirmed: bool = True
) -> Any:
    return w.client.put(
        f"{MEMBER}/me/teaching/attendance/{attendance_id}",
        json={"version": version, "confirmed": confirmed, "marks": entries},
        headers=csrf(w),
    )


def nothing_saved(w: World) -> bool:
    return not rows(w, "SELECT 1 FROM TB_CORS_ATND") and not rows(w, "SELECT 1 FROM TB_CORS_ATND_HSTRY")


# --- 담당 강좌와 회차 ---------------------------------------------------------------------------


def test_담당_강좌의_오늘까지의_수업_회차를_최근_것부터_보인다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    [item] = courses(world)
    assert (item["courseId"], item["courseName"]) == (str(course["CORS_SN"]), "요가")
    assert [s["classDate"] for s in item["sessions"]] == [TODAY, MON3, MON2, MON1]  # 다음 주는 없다
    first = item["sessions"][0]
    assert (first["session"], first["startTime"], first["endTime"]) == (1, "10:00", "12:00")
    assert (first["makeup"], first["status"], first["attendanceId"]) == (False, "NOT_STARTED", None)


def test_휴강한_날과_옮긴_원수업일은_빠지고_보강일이_들어온다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    changed(world, course, "20261026")  # 휴강
    makeup = changed(
        world,
        course,
        "20261102",
        CHG_TYPE_CD="SC.MAKEUP",
        CHG_LCTR_YMD="20261104",
        CHG_BGNG_TM="140000",
        CHG_END_TM="160000",
    )
    changed(  # 아직 오지 않은 보강은 입력할 수 없다
        world,
        course,
        "20261109",
        CHG_TYPE_CD="SC.MAKEUP",
        CHG_LCTR_YMD="20261111",
        CHG_BGNG_TM="140000",
        CHG_END_TM="160000",
    )
    [item] = courses(world)
    sessions = item["sessions"]
    assert [s["classDate"] for s in sessions] == ["2026-11-04", MON1]
    assert (sessions[0]["makeup"], sessions[0]["startTime"]) == (True, "14:00")
    assert sessions[0]["changeId"] == str(makeup["CORS_SCHDL_CHG_SN"])


def test_같은_날의_수업은_시작_시각_순으로_회차를_센다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    schedule(world, course, "080000", "090000")
    today = [s for s in courses(world)[0]["sessions"] if s["classDate"] == TODAY]
    assert [(s["session"], s["startTime"]) for s in today] == [(1, "08:00"), (2, "10:00")]


def test_로그인이_없으면_401이다(world: World) -> None:
    assert world.client.get(f"{MEMBER}/me/teaching/courses").status_code == 401


@pytest.mark.parametrize("state", ["IS.STOP", None])
def test_승인_강사가_아니면_담당_강좌가_없고_명단과_저장은_404다(world: World, state: str | None) -> None:
    member = sign_in(world, "plain")
    other = instructor(world, make_member(world, "other"))
    mine = instructor(world, member, state) if state else other
    course = taught(world, mine)
    a = student(world, course, "홍길동")
    world.db.commit()
    assert courses(world) == []
    assert sheet(world, course).status_code == 404
    assert create(world, course, marked((a, "PRESENT"))).status_code == 404
    assert nothing_saved(world)


def test_다른_강사의_강좌는_보이지_않고_404다(world: World) -> None:
    me_teaching(world)
    other = instructor(world, make_member(world, "other"))
    course = taught(world, other)
    a = student(world, course, "홍길동")
    world.db.commit()
    assert courses(world) == []
    assert sheet(world, course).status_code == 404
    assert create(world, course, marked((a, "PRESENT"))).status_code == 404


@pytest.mark.parametrize("status", ["CS.DRAFT", "CS.CANCEL"])
def test_작성중이거나_폐강한_강좌는_목록에_없고_저장할_수_없다(world: World, status: str) -> None:
    _, me = me_teaching(world)
    course = taught(world, me, CORS_STTS_CD=status)
    a = student(world, course, "홍길동")
    world.db.commit()
    assert courses(world) == []
    assert create(world, course, marked((a, "PRESENT"))).status_code == 409
    assert nothing_saved(world)


def test_종료한_강좌는_입력할_수_있다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me, CORS_STTS_CD="CS.END")
    a = student(world, course, "홍길동", "ES.COMPLETE")
    assert create(world, course, marked((a, "PRESENT"))).status_code == 201


# --- 명단 ---------------------------------------------------------------------------------------


def test_명단은_수강확정과_종료만이고_이름을_가려_미체크로_보인다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    confirmed = student(world, course, "홍길동")
    completed = student(world, course, "가나다", "ES.COMPLETE")
    for state in ("ES.HOLD", "ES.WAIT", "ES.CANCEL", "ES.EXPIRE"):
        student(world, course, "제외", state)
    body = sheet(world, course).json()
    assert body["roster"] == [
        {"applicationId": completed, "name": "가*다", "mark": "UNCHECKED"},
        {"applicationId": confirmed, "name": "홍*동", "mark": "UNCHECKED"},
    ]
    assert (body["attendanceId"], body["version"], body["status"]) == (None, None, "NOT_STARTED")
    assert (body["present"], body["absent"], body["unchecked"]) == (0, 0, 2)
    assert (body["courseName"], body["classDate"], body["session"]) == ("요가", TODAY, 1)


@pytest.mark.parametrize("day", [NEXT, "2026-11-08", "2026-10-12"])
def test_수업_회차가_아닌_날은_422다(world: World, day: str) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    world.db.commit()
    assert sheet(world, course, day).status_code == 422
    assert create(world, course, marked((a, "PRESENT")), day).status_code == 422
    assert nothing_saved(world)


def test_휴강한_날은_저장할_수_없다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    changed(world, course, "20261109")
    world.db.commit()
    assert create(world, course, marked((a, "PRESENT"))).status_code == 422
    assert nothing_saved(world)


# --- 생성 ---------------------------------------------------------------------------------------


def test_저장하면_합계를_계산하고_이력을_남긴다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a, b, c = (student(world, course, n) for n in ("가회원", "나회원", "다회원"))
    response = create(world, course, marked((a, "PRESENT"), (b, "ABSENT"), (c, "UNCHECKED")))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["present"], body["absent"], body["unchecked"]) == (1, 1, 1)
    assert (body["status"], body["version"]) == ("IN_PROGRESS", 1)
    [master] = rows(world, "SELECT * FROM TB_CORS_ATND")
    assert str(int(master["ATND_SN"])) == body["attendanceId"]
    assert (master["LCTR_YMD"], int(master["LCTR_SEQ"]), master["CMPTN_YN"]) == ("20261109", 1, "N")
    assert (int(master["INSTR_SN"]), master["CORS_SCHDL_CHG_SN"]) == (me["INSTR_SN"], None)
    assert len(rows(world, "SELECT * FROM TB_CORS_ATND_DTL")) == 3
    history = rows(world, "SELECT * FROM TB_CORS_ATND_HSTRY ORDER BY ATND_HSTRY_SN")
    assert len(history) == 4 and {h["ACTN_CD"].strip() for h in history} == {"AH.CREATE"}
    assert {int(h["ACTR_INSTR_SN"]) for h in history} == {me["INSTR_SN"]}
    assert len({h["DMND_ID"] for h in history}) == 1
    assert "가회원" not in str(history)  # 이력에 이름을 남기지 않는다
    [listed] = [s for s in courses(world)[0]["sessions"] if s["classDate"] == TODAY]
    assert (listed["status"], listed["attendanceId"]) == ("IN_PROGRESS", body["attendanceId"])


def test_미체크가_없으면_완료이고_관리자_현황에_보인다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    body = create(world, course, marked((a, "PRESENT"))).json()
    assert body["status"] == "DONE"
    use(world, staff(world, "att", "AU.ATND_R"))
    [row] = call(world, "GET", "/attendance").json()["items"]
    assert (row["instructorName"], row["present"], row["inputStatus"]) == ("박강사", 1, "DONE")


def test_보강일의_출석은_일정변경에_연결한다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    makeup = changed(
        world,
        course,
        "20261102",
        CHG_TYPE_CD="SC.MAKEUP",
        CHG_LCTR_YMD="20261104",
        CHG_BGNG_TM="140000",
        CHG_END_TM="160000",
    )
    response = create(world, course, marked((a, "PRESENT")), "2026-11-04", change=makeup)
    assert response.status_code == 201, response.text
    [master] = rows(world, "SELECT * FROM TB_CORS_ATND")
    assert int(master["CORS_SCHDL_CHG_SN"]) == makeup["CORS_SCHDL_CHG_SN"]


def test_확인하지_않으면_422이고_저장하지_않는다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    world.db.commit()
    response = create(world, course, marked((a, "PRESENT")), confirmed=False)
    assert response.status_code == 422 and "confirmed" in response.json()["fields"]
    assert nothing_saved(world)


@pytest.mark.parametrize("case", ["missing", "extra", "stranger"])
def test_보낸_명단이_지금_명단과_다르면_409다(world: World, case: str) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a, b = (student(world, course, n) for n in ("가회원", "나회원"))
    stranger = student(world, open_course(world, CORS_NM="다른강좌"), "남")
    world.db.commit()
    entries = {
        "missing": marked((a, "PRESENT")),
        "extra": marked((a, "PRESENT"), (b, "PRESENT"), (stranger, "PRESENT")),
        "stranger": marked((a, "PRESENT"), (stranger, "PRESENT")),
    }[case]
    response = create(world, course, entries)
    assert response.status_code == 409 and response.json()["message"] == ROSTER_CHANGED
    assert nothing_saved(world)


def test_같은_신청을_두_번_보내면_400이다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    world.db.commit()
    assert create(world, course, marked((a, "PRESENT"), (a, "ABSENT"))).status_code == 400


def test_수강생이_없으면_저장할_수_없다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    world.db.commit()
    assert create(world, course, []).status_code == 422
    assert nothing_saved(world)


def test_같은_키의_재전송은_같은_결과이고_내용이_다르면_409다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    first = create(world, course, marked((a, "PRESENT")), idem="same-key-0001")
    again = create(world, course, marked((a, "PRESENT")), idem="same-key-0001")
    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json()["attendanceId"] == again.json()["attendanceId"]
    assert len(rows(world, "SELECT 1 FROM TB_CORS_ATND_HSTRY")) == 2
    world.db.commit()
    different = create(world, course, marked((a, "ABSENT")), idem="same-key-0001")
    assert different.status_code == 409 and different.json()["code"] == "IDEMPOTENCY_CONFLICT"
    other_key = create(world, course, marked((a, "PRESENT")))
    assert other_key.status_code == 409 and other_key.json()["code"] == "CONFLICT_STATE"
    assert len(rows(world, "SELECT 1 FROM TB_CORS_ATND")) == 1


def test_CSRF_토큰이_없으면_403이다(world: World) -> None:
    _, me = me_teaching(world)
    course = taught(world, me)
    a = student(world, course, "홍길동")
    world.db.commit()
    body = {**where(course, TODAY), "confirmed": True, "marks": marked((a, "PRESENT"))}
    response = world.client.post(
        f"{MEMBER}/me/teaching/attendance", json=body, headers={"Idempotency-Key": key()}
    )
    assert response.status_code == 403 and nothing_saved(world)


# --- 수정 ---------------------------------------------------------------------------------------


def saved(w: World) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    """(강사, 강좌, 출석부 번호, 가회원 신청, 나회원 신청)"""
    _, me = me_teaching(w)
    course = taught(w, me)
    a, b = (student(w, course, n) for n in ("가회원", "나회원"))
    body = create(w, course, marked((a, "PRESENT"), (b, "UNCHECKED"))).json()
    return me, course, str(body["attendanceId"]), a, b


def test_수정하면_바뀐_사람의_전후를_이력에_남기고_버전을_올린다(world: World) -> None:
    _, _, sn, a, b = saved(world)
    response = update(world, sn, 1, marked((a, "PRESENT"), (b, "ABSENT")))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["version"], body["status"], body["absent"], body["unchecked"]) == (2, "DONE", 1, 0)
    changes = rows(
        world,
        "SELECT * FROM TB_CORS_ATND_HSTRY WHERE TRIM(ACTN_CD)='AH.UPDATE' AND ATND_DTL_SN IS NOT NULL",
    )
    [detail] = changes  # 바뀌지 않은 가회원은 남기지 않는다
    assert "AR.UNCHECKED" in detail["BFR_VL_CN"] and "AR.ABSENT" in detail["AFTR_VL_CN"]
    assert int(detail["TRGT_RCRD_VER"]) == 2


def test_읽은_버전이_다르면_409이고_바꾸지_않는다(world: World) -> None:
    _, _, sn, a, b = saved(world)
    assert update(world, sn, 1, marked((a, "ABSENT"), (b, "ABSENT"))).status_code == 200
    world.db.commit()
    stale = update(world, sn, 1, marked((a, "PRESENT"), (b, "PRESENT")))
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert int(rows(world, "SELECT ATND_NOPE n FROM TB_CORS_ATND")[0]["n"]) == 0


def test_취소한_수강생의_기록은_남고_새_수강생이_명단에_더해진다(world: World) -> None:
    _, course, sn, a, b = saved(world)
    cancel = (
        "UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CANCEL', RTRCN_DT=:n, RTRCN_RSN='취소'"
        " WHERE ATNLC_APLY_SN=:a"
    )
    world.db.execute(text(cancel), {"n": START, "a": int(a)})
    late = student(world, course, "다회원")
    world.db.commit()
    assert [r["applicationId"] for r in sheet(world, course).json()["roster"]] == [a, b, late]
    stale = update(world, sn, 1, marked((a, "PRESENT"), (b, "PRESENT")))
    assert stale.status_code == 409 and stale.json()["message"] == ROSTER_CHANGED
    done = update(world, sn, 1, marked((a, "PRESENT"), (b, "PRESENT"), (late, "ABSENT")))
    assert done.status_code == 200 and done.json()["present"] == 2
    assert len(rows(world, "SELECT 1 FROM TB_CORS_ATND_DTL")) == 3


def test_담당이_바뀌면_이전_강사는_404이고_새_강사가_이어서_입력한다(world: World) -> None:
    _, course, sn, a, b = saved(world)
    successor = instructor(world, make_member(world, "successor"))
    world.db.execute(
        text("UPDATE TB_CORS SET INSTR_SN=:i WHERE CORS_SN=:c"),
        {"i": successor["INSTR_SN"], "c": course["CORS_SN"]},
    )
    world.db.commit()
    assert update(world, sn, 1, marked((a, "PRESENT"), (b, "PRESENT"))).status_code == 404


def test_폐강한_뒤에는_고칠_수_없다(world: World) -> None:
    _, course, sn, a, b = saved(world)
    cancel = "UPDATE TB_CORS SET CORS_STTS_CD='CS.CANCEL' WHERE CORS_SN=:c"
    world.db.execute(text(cancel), {"c": course["CORS_SN"]})
    world.db.commit()
    assert update(world, sn, 1, marked((a, "PRESENT"), (b, "PRESENT"))).status_code == 409


def test_없는_출석부는_404다(world: World) -> None:
    me_teaching(world)
    assert update(world, "999999", 1, []).status_code == 404
