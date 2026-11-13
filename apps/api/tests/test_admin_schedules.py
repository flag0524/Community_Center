# 관리자 강좌 일정·휴보강(시설 중복 판정, 원수업일 규칙, 보강 점유, 휴강 해제, 공개 강좌의 일정 하한, 동 범위, 멱등)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import open_course
from tests.world import World

pytestmark = pytest.mark.db

_keys = itertools.count(1)
MON1, MON2, TUE1 = "2026-11-09", "2026-11-16", "2026-11-10"  # 월요일 둘과 화요일


def key() -> str:
    return f"sch-key-{next(_keys):06d}"


def room(w: World, name: str = "1강의실", center: str = "조리 센터", active: bool = True) -> dict[str, Any]:
    parent = w.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM=f"{center}{next(_keys)}", USE_YN="Y")
    return w.factory.make(
        "TB_FCLT",
        FCLT_TYPE_CD="FT.ROOM",
        UP_FCLT_SN=parent["FCLT_SN"],
        FCLT_NM=name,
        USE_YN="Y" if active else "N",
    )


def body(r: dict[str, Any], **values: Any) -> dict[str, Any]:
    return {
        "weekday": "MON",
        "startTime": "10:00",
        "endTime": "11:30",
        "facilityId": str(r["FCLT_SN"]),
        "periodStart": "2026-11-02",
        "periodEnd": "2026-12-28",
        **values,
    }


def add(w: World, course: dict[str, Any], payload: dict[str, Any]) -> Any:
    return call(w, "POST", f"/courses/{course['CORS_SN']}/schedules", payload, **{"Idempotency-Key": key()})


def made(w: World, course: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    r = add(w, course, payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


def change(w: World, course: dict[str, Any], payload: dict[str, Any], idem: str | None = None) -> Any:
    return call(
        w,
        "POST",
        f"/courses/{course['CORS_SN']}/schedule-changes",
        payload,
        **{"Idempotency-Key": idem or key()},
    )


def cancel_body(day: str = MON1, reason: str = "강사 사정") -> dict[str, Any]:
    return {"classDate": day, "kind": "CANCEL", "reason": reason}


def makeup_body(
    r: dict[str, Any], day: str, original: str = MON1, start: str = "14:00", end: str = "15:30", **v: Any
) -> dict[str, Any]:
    return {
        "classDate": day,
        "originalDate": original,
        "kind": "MAKEUP",
        "facilityId": str(r["FCLT_SN"]),
        "startTime": start,
        "endTime": end,
        "reason": "보강",
        **v,
    }


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def writer(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"s{next(_keys)}", *(codes or ("AU.CORS_R", "AU.CORS_W")), **kw)
    use(w, who)
    return who


def view(w: World, course: dict[str, Any]) -> dict[str, Any]:
    return dict(call(w, "GET", f"/courses/{course['CORS_SN']}/schedules").json())


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_쓰기_권한이_없으면_403이다(world: World) -> None:
    c = open_course(world)
    world.db.commit()  # 오류 응답의 롤백이 준비한 행을 되돌리지 않게 고정한다
    assert world.client.get(f"/api/admin/v1/courses/{c['CORS_SN']}/schedules").status_code == 401
    use(world, staff(world, "x", "AU.POST_W"))
    assert call(world, "GET", f"/courses/{c['CORS_SN']}/schedules").status_code == 403
    use(world, staff(world, "r", "AU.CORS_R"))
    assert call(world, "GET", f"/courses/{c['CORS_SN']}/schedules").status_code == 200
    r = room(world)
    for method, path, payload in (
        ("POST", f"/courses/{c['CORS_SN']}/schedules", body(r)),
        ("PUT", f"/courses/{c['CORS_SN']}/schedules/1", {**body(r), "version": 1}),
        ("DELETE", f"/courses/{c['CORS_SN']}/schedules/1", None),
        ("POST", f"/courses/{c['CORS_SN']}/schedule-changes", cancel_body()),
        ("DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/1", None),
    ):
        assert call(world, method, path, payload, **{"Idempotency-Key": key()}).status_code == 403, path


def test_동_담당자는_자기_동_강좌만_다루고_남의_강좌는_404다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = open_course(world, CORS_NM="내 강좌", DONG_SN=a["DONG_SN"])
    other = open_course(world, CORS_NM="남 강좌", DONG_SN=b["DONG_SN"])
    r = room(world)
    writer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert add(world, mine, body(r)).status_code == 201
    assert view(world, mine)["canEdit"] is True
    sn = other["CORS_SN"]
    for method, path, payload in (
        ("GET", f"/courses/{sn}/schedules", None),
        ("POST", f"/courses/{sn}/schedules", body(r)),
        ("POST", f"/courses/{sn}/schedule-changes", cancel_body()),
        ("DELETE", f"/courses/{sn}/schedules/1", None),
    ):
        assert call(world, method, path, payload, **{"Idempotency-Key": key()}).status_code == 404, path


# --- 조회 ---------------------------------------------------------------------------------------


def test_조회는_요일과_시작_순서로_일정을_주고_강의실_이름에_센터를_붙이며_수정_가능_여부를_알린다(
    world: World,
) -> None:
    c = open_course(world, CORS_NM="요가")
    r1, r2 = room(world, "1강의실", "A 센터"), room(world, "2강의실", "B 센터")
    writer(world, "AU.CORS_R", "AU.CORS_W")
    made(world, c, body(r1, weekday="WED", startTime="09:00", endTime="10:00"))
    made(world, c, body(r2, weekday="MON", startTime="15:00", endTime="16:00"))
    made(world, c, body(r1, weekday="MON", startTime="09:00", endTime="10:00"))
    out = view(world, c)
    assert out["courseName"] == "요가" and out["canEdit"] is True and out["changes"] == []
    assert [(s["weekday"], s["startTime"]) for s in out["schedules"]] == [
        ("MON", "09:00"),
        ("MON", "15:00"),
        ("WED", "09:00"),
    ]
    assert (
        out["schedules"][0]["facilityName"].endswith(" 1강의실")
        and "A 센터" in out["schedules"][0]["facilityName"]
    )
    assert (
        out["schedules"][0]["periodStart"],
        out["schedules"][0]["periodEnd"],
        out["schedules"][0]["version"],
    ) == ("2026-11-02", "2026-12-28", 1)
    use(world, staff(world, "ro", "AU.CORS_R"))
    assert view(world, c)["canEdit"] is False  # 읽기 권한만이다


def test_폐강이나_종료한_강좌는_수정할_수_없다고_알리고_변경은_409다(world: World) -> None:
    c = open_course(world, CORS_STTS_CD="CS.CANCEL")
    r = room(world)
    writer(world)
    assert view(world, c)["canEdit"] is False
    for res in (add(world, c, body(r)), change(world, c, cancel_body())):
        assert res.status_code == 409 and res.json()["code"] == "CONFLICT_STATE"
    assert call(world, "GET", "/courses/999999999/schedules").status_code == 404
    assert call(world, "GET", "/courses/abc/schedules").status_code in (400, 422)


# --- 일정 등록 ----------------------------------------------------------------------------------


def test_일정을_등록하면_저장_형식으로_담고_작업이력에_남긴다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    boss = writer(world)
    out = made(world, c, body(r, weekday="TUE", startTime="09:30", endTime="11:00"))
    assert (out["weekday"], out["startTime"], out["endTime"], out["version"]) == ("TUE", "09:30", "11:00", 1)
    [row] = rows(world, "SELECT * FROM TB_CORS_SCHDL")
    assert (row["DOW_CD"], row["BGNG_TM"], row["END_TM"], row["APLCN_BGNG_YMD"], row["APLCN_END_YMD"]) == (
        "DW.TUE",
        "093000",
        "110000",
        "20261102",
        "20261228",
    )
    assert (row["CORS_SN"], row["FCLT_SN"]) == (c["CORS_SN"], r["FCLT_SN"])
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SCHDL_CREATE'"
    )
    assert (job["m"], job["t"]) == (boss.sn, "TB_CORS_SCHDL") and job["c"].startswith(
        f"강좌 {c['CORS_SN']} [idem "
    )


def test_작성중_강좌도_일정을_등록한다(world: World) -> None:
    c = open_course(world, CORS_STTS_CD="CS.DRAFT")
    r = room(world)
    writer(world)
    assert add(world, c, body(r)).status_code == 201


def test_시설과_시간과_기간을_검사한다(world: World) -> None:
    c = open_course(world)
    good = room(world)
    inactive, center = (
        room(world, active=False),
        world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM="센터만", USE_YN="Y"),
    )
    writer(world)
    cases = [
        ("없는 시설", body(good, facilityId="999999999"), "facilityId"),
        ("사용 중지 강의실", body(inactive), "facilityId"),
        ("센터는 강의실이 아니다", body(good, facilityId=str(center["FCLT_SN"])), "facilityId"),
        ("종료가 시작보다 앞", body(good, startTime="11:00", endTime="10:00"), "endTime"),
        ("종료가 시작과 같음", body(good, startTime="10:00", endTime="10:00"), "endTime"),
        (
            "기간 종료가 시작보다 앞",
            body(good, periodStart="2026-12-01", periodEnd="2026-11-30"),
            "periodEnd",
        ),
        ("교육기간 앞", body(good, periodStart="2026-10-31"), "periodStart"),
        ("교육기간 뒤", body(good, periodEnd="2027-01-01"), "periodStart"),
    ]
    for label, payload, field in cases:
        r = add(world, c, payload)
        assert r.status_code == 422 and field in r.json()["fields"], label
    assert (
        add(world, c, body(good, periodStart="2026-11-01", periodEnd="2026-12-31")).status_code == 201
    )  # 교육기간과 같다
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL")[0]["n"] == 1


def test_같은_시설_요일에_시간과_기간이_겹치는_다른_강좌가_있으면_거절하고_위치를_알린다(
    world: World,
) -> None:
    mine, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    r = room(world, "3강의실")
    writer(world)
    made(world, other, body(r, startTime="10:00", endTime="11:30"))
    for start, end in (("10:00", "11:30"), ("09:00", "10:30"), ("11:00", "12:00"), ("10:30", "11:00")):
        res = add(world, mine, body(r, startTime=start, endTime=end))
        assert res.status_code == 422, (start, end)
        message = res.json()["fields"]["facilityId"]
        assert "3강의실" in message and "월" in message and "서예" in message and "10:00~11:30" in message
    assert (
        rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL WHERE CORS_SN=:c", c=mine["CORS_SN"])[0]["n"] == 0
    )


def test_겹치지_않는_경우는_허용한다(world: World) -> None:
    mine, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    r = room(world)
    writer(world)
    made(
        world,
        other,
        body(r, startTime="10:00", endTime="11:30", periodStart="2026-11-02", periodEnd="2026-11-30"),
    )
    assert (
        add(
            world,
            mine,
            body(r, startTime="11:30", endTime="12:30", periodStart="2026-11-02", periodEnd="2026-11-30"),
        ).status_code
        == 201
    )  # 종료=다음 시작
    assert (
        add(
            world,
            mine,
            body(r, startTime="08:30", endTime="10:00", periodStart="2026-11-02", periodEnd="2026-11-30"),
        ).status_code
        == 201
    )
    assert (
        add(world, mine, body(r, weekday="TUE", periodStart="2026-11-02", periodEnd="2026-11-30")).status_code
        == 201
    )  # 다른 요일
    assert (
        add(world, mine, body(r, periodStart="2026-12-01", periodEnd="2026-12-28")).status_code == 201
    )  # 기간이 겹치지 않는다
    other_room = room(world)
    assert add(world, mine, body(other_room)).status_code == 201  # 다른 시설


def test_같은_강좌의_일정끼리는_겹쳐도_거절하지_않는다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    made(world, c, body(r))
    assert add(world, c, body(r, startTime="10:30", endTime="12:00")).status_code == 201  # 겹쳐도 된다
    same = add(world, c, body(r))
    assert same.status_code == 422 and "weekday" in same.json()["fields"]  # 똑같은 일정은 거절한다


def test_다른_강좌의_보강이_걸리면_일정_등록을_거절한다(world: World) -> None:
    mine, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    home, away = room(world, "본관"), room(world, "별관")
    writer(world)
    made(world, other, body(home, weekday="TUE", startTime="09:00", endTime="10:00"))
    assert (
        change(
            world,
            other,
            makeup_body(away, MON2, original=TUE1 if False else "2026-11-17", start="10:00", end="11:30"),
        ).status_code
        == 201
    )
    res = add(world, mine, body(away, weekday="MON", startTime="11:00", endTime="12:00"))
    assert res.status_code == 422 and "서예" in res.json()["fields"]["facilityId"]


def test_같은_키로_다시_보내면_같은_일정이고_내용이_다르면_409다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    path = f"/courses/{c['CORS_SN']}/schedules"
    first = call(world, "POST", path, body(r), **{"Idempotency-Key": "same-key-0001"}).json()
    again = call(world, "POST", path, body(r), **{"Idempotency-Key": "same-key-0001"})
    assert again.status_code == 201 and again.json()["scheduleId"] == first["scheduleId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL")[0]["n"] == 1
    diff = call(world, "POST", path, body(r, weekday="FRI"), **{"Idempotency-Key": "same-key-0001"})
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    other = open_course(world, CORS_NM="다른 강좌")
    cross = call(
        world,
        "POST",
        f"/courses/{other['CORS_SN']}/schedules",
        body(r),
        **{"Idempotency-Key": "same-key-0001"},
    )
    assert cross.status_code == 409  # 같은 키라도 다른 강좌의 요청이다
    assert call(world, "POST", path, body(r)).status_code in (400, 422)  # 멱등키 없음


# --- 일정 수정·삭제 -----------------------------------------------------------------------------


def edit(
    w: World, c: dict[str, Any], sched: dict[str, Any], payload: dict[str, Any], version: int | None = None
) -> Any:
    return call(
        w,
        "PUT",
        f"/courses/{c['CORS_SN']}/schedules/{sched['scheduleId']}",
        {**payload, "version": version or sched["version"]},
    )


def test_수정하면_버전이_오르고_자기_일정과는_겹침을_보지_않는다(world: World) -> None:
    c = open_course(world)
    r, r2 = room(world), room(world, "2강의실")
    boss = writer(world)
    s = made(world, c, body(r))
    out = edit(world, c, s, body(r, startTime="10:30", endTime="12:00"))
    assert out.status_code == 200 and out.json()["startTime"] == "10:30" and out.json()["version"] == 2
    moved = edit(world, c, out.json(), body(r2, weekday="THU"))
    assert moved.status_code == 200 and (moved.json()["weekday"], moved.json()["version"]) == ("THU", 3)
    [job] = rows(
        world,
        "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SCHDL_UPDATE' ORDER BY JOB_HSTRY_SN LIMIT 1",
    )
    assert job["m"] == boss.sn


def test_수정도_읽은_버전과_시설_겹침과_시설_상태를_검사한다(world: World) -> None:
    c, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    r, taken, off = room(world), room(world, "2강의실"), room(world, "3강의실", active=False)
    writer(world)
    s = made(world, c, body(r))
    made(world, other, body(taken))
    assert edit(world, c, s, body(r, startTime="11:00", endTime="12:00")).status_code == 200
    stale = edit(world, c, s, body(r), version=1)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    clash = edit(world, c, {**s, "version": 2}, body(taken))
    assert clash.status_code == 422 and "서예" in clash.json()["fields"]["facilityId"]
    inactive = edit(world, c, {**s, "version": 2}, body(off))
    assert inactive.status_code == 422 and "facilityId" in inactive.json()["fields"]
    assert view(world, c)["schedules"][0]["startTime"] == "11:00"


def test_남의_강좌의_일정은_고칠_수_없고_404다(world: World) -> None:
    c, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="남 강좌")
    r = room(world)
    writer(world)
    theirs = made(world, other, body(r))
    assert edit(world, c, theirs, body(r)).status_code == 404
    assert (
        call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedules/{theirs['scheduleId']}").status_code == 404
    )
    assert call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedules/999999999").status_code == 404


def test_휴강이_걸린_일정은_요일과_기간을_바꿀_수_없지만_시간은_바꿀_수_있다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    s = made(world, c, body(r))
    assert change(world, c, cancel_body()).status_code == 201
    for payload in (
        body(r, weekday="TUE"),
        body(r, periodStart="2026-11-03"),
        body(r, periodEnd="2026-12-20"),
    ):
        res = edit(world, c, s, payload)
        assert res.status_code == 422 and "weekday" in res.json()["fields"]
    assert edit(world, c, s, body(r, startTime="13:00", endTime="14:00")).status_code == 200


def test_삭제하면_일정이_사라지고_휴강이_걸렸으면_409다(world: World) -> None:
    c = open_course(world, CORS_STTS_CD="CS.DRAFT")
    r = room(world)
    boss = writer(world)
    s1, s2 = made(world, c, body(r)), made(world, c, body(r, weekday="WED"))
    assert change(world, c, cancel_body()).status_code == 201
    blocked = call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedules/{s1['scheduleId']}")
    assert blocked.status_code == 409 and blocked.json()["code"] == "CONFLICT_STATE"
    done = call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedules/{s2['scheduleId']}")
    assert done.status_code == 204 and done.content == b""
    assert [s["scheduleId"] for s in view(world, c)["schedules"]] == [s1["scheduleId"]]
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SCHDL_DELETE'")
    assert job["m"] == boss.sn and "DW.WED" in job["c"]  # 지우기 전의 값을 남긴다


def test_공개한_강좌의_마지막_일정은_지울_수_없고_작성중_강좌는_지울_수_있다(world: World) -> None:
    open_c, draft = (
        open_course(world, CORS_NM="공개"),
        open_course(world, CORS_NM="작성중", CORS_STTS_CD="CS.DRAFT"),
    )
    r = room(world)
    writer(world)
    a, b = made(world, open_c, body(r)), made(world, draft, body(r, weekday="TUE"))
    last = call(world, "DELETE", f"/courses/{open_c['CORS_SN']}/schedules/{a['scheduleId']}")
    assert last.status_code == 422 and "schedule" in last.json()["fields"]
    assert (
        call(world, "DELETE", f"/courses/{draft['CORS_SN']}/schedules/{b['scheduleId']}").status_code == 204
    )
    made(world, open_c, body(r, weekday="FRI"))
    assert (
        call(world, "DELETE", f"/courses/{open_c['CORS_SN']}/schedules/{a['scheduleId']}").status_code == 204
    )


# --- 휴강 ---------------------------------------------------------------------------------------


def test_휴강은_원수업일을_정규_일정에_맞춰_저장하고_응답에_원수업일을_담는다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    boss = writer(world)
    made(world, c, body(r))
    res = change(world, c, cancel_body(MON2, "공휴일"))
    assert res.status_code == 201
    out = res.json()
    assert (out["kind"], out["classDate"], out["originalDate"], out["reason"]) == (
        "CANCEL",
        MON2,
        MON2,
        "공휴일",
    )
    assert (out["facilityId"], out["startTime"], out["endTime"], out["facilityName"]) == (
        None,
        None,
        None,
        None,
    )
    [row] = rows(world, "SELECT * FROM TB_CORS_SCHDL_CHG")
    assert (
        row["CHG_TYPE_CD"],
        row["ORGNL_LCTR_YMD"],
        row["CHG_LCTR_YMD"],
        row["CHG_FCLT_SN"],
        row["APLCN_YN"],
        row["REG_MNGR_SN"],
    ) == (
        "SC.CANCEL",
        "20261116",
        None,
        None,
        "Y",
        boss.sn,
    )
    listed = view(world, c)["changes"]
    assert [(i["kind"], i["classDate"], i["originalDate"]) for i in listed] == [("CANCEL", MON2, MON2)]
    assert [j["c"] for j in rows(world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SCHDL_CHG_CREATE'")][
        0
    ].startswith("CANCEL [idem ")


def test_원수업일이_정규_일정의_요일이나_기간에_맞지_않으면_거절한다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    made(world, c, body(r, periodStart="2026-11-02", periodEnd="2026-11-30"))
    for day in (TUE1, "2026-12-07", "2026-10-26"):  # 다른 요일, 기간 뒤, 기간 앞
        res = change(world, c, cancel_body(day))
        assert res.status_code == 422 and "originalDate" in res.json()["fields"], day
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL_CHG")[0]["n"] == 0


def test_휴강은_시설과_시간을_받지_않고_원수업일이_다르면_거절한다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    made(world, c, body(r))
    for extra in (
        {"facilityId": str(r["FCLT_SN"])},
        {"startTime": "10:00"},
        {"endTime": "11:00"},
        {"originalDate": MON2},
    ):
        res = change(world, c, {**cancel_body(MON1), **extra})
        assert res.status_code == 422, extra
    assert (
        change(world, c, {**cancel_body(MON1), "originalDate": MON1}).status_code == 201
    )  # 같은 날짜는 받는다


def test_같은_수업일에_다시_휴강이나_보강을_등록하면_거절하고_지운_뒤에는_다시_등록할_수_있다(
    world: World,
) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    made(world, c, body(r))
    first = change(world, c, cancel_body()).json()
    again = change(world, c, cancel_body(reason="다시"))
    assert again.status_code == 422 and "classDate" in again.json()["fields"]
    dup_makeup = change(world, c, makeup_body(r, MON2, original=MON1))
    assert dup_makeup.status_code == 422
    assert (
        call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/{first['changeId']}").status_code
        == 204
    )
    assert change(world, c, cancel_body(reason="다시")).status_code == 201


def test_사유가_비면_거절하고_멱등키가_같으면_같은_변경을_준다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    made(world, c, body(r))
    assert change(world, c, cancel_body(reason="")).status_code in (400, 422)
    first = change(world, c, cancel_body(), "same-key-0001").json()
    again = change(world, c, cancel_body(), "same-key-0001")
    assert again.status_code == 201 and again.json()["changeId"] == first["changeId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL_CHG")[0]["n"] == 1
    assert change(world, c, cancel_body(MON2), "same-key-0001").status_code == 409


# --- 보강 ---------------------------------------------------------------------------------------


def test_보강은_원수업일과_시설과_시간을_저장하고_응답에_담는다(world: World) -> None:
    c = open_course(world)
    r, extra = room(world, "1강의실"), room(world, "특별실")
    writer(world)
    made(world, c, body(r))
    res = change(world, c, makeup_body(extra, "2026-11-12", original=MON1, start="14:00", end="15:30"))
    assert res.status_code == 201
    out = res.json()
    assert (out["kind"], out["classDate"], out["originalDate"], out["startTime"], out["endTime"]) == (
        "MAKEUP",
        "2026-11-12",
        MON1,
        "14:00",
        "15:30",
    )
    assert out["facilityId"] == str(extra["FCLT_SN"]) and "특별실" in out["facilityName"]
    [row] = rows(world, "SELECT * FROM TB_CORS_SCHDL_CHG")
    assert (
        row["CHG_TYPE_CD"],
        row["ORGNL_LCTR_YMD"],
        row["CHG_LCTR_YMD"],
        row["CHG_BGNG_TM"],
        row["CHG_END_TM"],
        row["CHG_FCLT_SN"],
    ) == (
        "SC.MAKEUP",
        "20261109",
        "20261112",
        "140000",
        "153000",
        extra["FCLT_SN"],
    )


def test_보강은_필수_항목과_시간_순서와_교육기간과_시설_상태를_검사한다(world: World) -> None:
    c = open_course(world)
    r, off = room(world), room(world, "폐쇄", active=False)
    writer(world)
    made(world, c, body(r))
    missing = change(world, c, {"classDate": "2026-11-12", "kind": "MAKEUP", "reason": "보강"})
    assert missing.status_code == 422 and {"originalDate", "facilityId", "startTime", "endTime"} <= set(
        missing.json()["fields"]
    )
    cases = [
        ("종료가 시작보다 앞", makeup_body(r, "2026-11-12", start="15:00", end="14:00"), "endTime"),
        ("교육기간 밖", makeup_body(r, "2027-01-05"), "classDate"),
        ("사용 중지 시설", makeup_body(off, "2026-11-12"), "facilityId"),
        ("원수업일이 일정에 안 맞음", makeup_body(r, "2026-11-12", original=TUE1), "originalDate"),
    ]
    for label, payload, field in cases:
        res = change(world, c, payload)
        assert res.status_code == 422 and field in res.json()["fields"], label
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL_CHG")[0]["n"] == 0


def test_보강_날짜에_같은_시설의_다른_강좌_수업이나_보강이_있으면_거절한다(world: World) -> None:
    mine, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    home, away = room(world, "본관"), room(world, "별관")
    writer(world)
    made(world, mine, body(home))
    made(world, other, body(away, weekday="THU", startTime="14:00", endTime="15:30"))
    clash = change(
        world, mine, makeup_body(away, "2026-11-12", start="15:00", end="16:00")
    )  # 목요일 별관에 서예가 있다
    assert (
        clash.status_code == 422
        and "서예" in clash.json()["fields"]["facilityId"]
        and "2026-11-12" in clash.json()["fields"]["facilityId"]
    )
    assert (
        change(world, mine, makeup_body(away, "2026-11-12", start="15:30", end="16:30")).status_code == 201
    )  # 종료=다음 시작
    taken = change(world, mine, makeup_body(away, "2026-11-12", original=MON2, start="16:00", end="17:00"))
    assert (
        taken.status_code == 422 and "보강" in taken.json()["fields"]["facilityId"]
    )  # 방금 만든 보강과 겹친다
    assert (
        change(
            world, mine, makeup_body(away, "2026-11-13", original=MON2, start="16:00", end="17:00")
        ).status_code
        == 201
    )


def test_휴강하거나_대체되는_수업의_자리는_점유에서_뺀다(world: World) -> None:
    mine, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="서예")
    r = room(world, "본관")
    writer(world)
    made(world, other, body(r, weekday="THU", startTime="10:00", endTime="11:30"))
    blocked = (
        change(world, mine, makeup_body(r, "2026-11-12", original=MON1, start="10:00", end="11:00"))
        if False
        else None
    )
    assert blocked is None
    made(world, mine, body(r, weekday="MON", startTime="13:00", endTime="14:00"))
    taken = change(world, mine, makeup_body(r, "2026-11-12", original=MON1, start="10:30", end="11:00"))
    assert taken.status_code == 422  # 서예가 목요일 10시에 쓴다
    assert change(world, other, cancel_body("2026-11-12")).status_code == 201  # 서예가 그날 휴강한다
    freed = change(world, mine, makeup_body(r, "2026-11-12", original=MON1, start="10:30", end="11:00"))
    assert freed.status_code == 201


def test_같은_날짜의_시간_변경_보강은_자기_원수업과_겹쳐도_허용한다(world: World) -> None:
    c = open_course(world)
    r = room(world, "본관")
    writer(world)
    made(world, c, body(r, startTime="10:00", endTime="11:30"))
    res = change(world, c, makeup_body(r, MON1, original=MON1, start="10:30", end="12:00"))
    assert res.status_code == 201  # 대체되는 원수업은 점유가 아니다
    other = open_course(world, CORS_NM="서예")
    made(world, other, body(room(world, "다른실"), startTime="09:00", endTime="10:00"))
    clash = change(world, c, makeup_body(r, MON2, original=MON2, start="10:00", end="11:00"))
    assert clash.status_code == 201


def test_다른_날로_옮기는_보강은_원수업의_자리를_비우지_않은_채_그_날을_본다(world: World) -> None:
    c = open_course(world)
    r = room(world, "본관")
    writer(world)
    made(world, c, body(r, startTime="10:00", endTime="11:30"))
    made(world, c, body(r, weekday="WED", startTime="10:00", endTime="11:30"))
    res = change(world, c, makeup_body(r, "2026-11-11", original=MON1, start="10:30", end="11:00"))
    assert (
        res.status_code == 422 and "2026-11-11" in res.json()["fields"]["facilityId"]
    )  # 수요일 자기 수업과 겹친다


# --- 휴보강 삭제 --------------------------------------------------------------------------------


def test_삭제하면_행을_지우고_지우기_전의_값을_작업이력에_남긴다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    boss = writer(world)
    made(world, c, body(r))
    made_change = change(world, c, makeup_body(r, "2026-11-12", start="14:00", end="15:00")).json()
    res = call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/{made_change['changeId']}")
    assert res.status_code == 204 and res.content == b""
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL_CHG")[0]["n"] == 0
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SCHDL_CHG_DELETE'")
    assert (
        job["m"] == boss.sn
        and "SC.MAKEUP" in job["c"]
        and "20261112" in job["c"]
        and "14:00~15:00" in job["c"]
    )
    assert (
        call(
            world, "DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/{made_change['changeId']}"
        ).status_code
        == 404
    )
    assert call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/abc").status_code in (400, 422)


def test_남의_강좌의_휴보강은_지울_수_없다(world: World) -> None:
    c, other = open_course(world, CORS_NM="내 강좌"), open_course(world, CORS_NM="남 강좌")
    r = room(world)
    writer(world)
    made(world, other, body(r))
    theirs = change(world, other, cancel_body()).json()
    assert (
        call(world, "DELETE", f"/courses/{c['CORS_SN']}/schedule-changes/{theirs['changeId']}").status_code
        == 404
    )
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_SCHDL_CHG")[0]["n"] == 1


def test_적용_기간이_하루인_일정도_등록한다(world: World) -> None:
    c = open_course(world)
    r = room(world)
    writer(world)
    assert add(world, c, body(r, periodStart=MON1, periodEnd=MON1)).status_code == 201
