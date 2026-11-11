# 관리자 교육기수·강좌 관리(권한·범위, 검증, 멱등, 공개·마감·폐강과 환불 접수)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import Actor, call, staff, use
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_courses_public import course as make_course
from tests.test_courses_public import cycle as make_cycle
from tests.world import START, World, make_admin, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
_keys = itertools.count(1)


def key() -> str:
    return f"edu-{next(_keys):08d}"


def instructor(w: World, status: str = "IS.APPROVE") -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if status == "IS.APPROVE":
        extra["APRV_DT"] = START
        extra["APRV_MNGR_SN"] = make_admin(w, f"ap{next(_keys)}")["MNGR_SN"]
    if status == "IS.REJECT":
        extra["RJCT_RSN"] = "반려"
    member = make_member(w, f"i{next(_keys)}", MBR_NM="강사님", **RESIDENT)
    return w.factory.make("TB_INSTR", MBR_SN=member["MBR_SN"], INSTR_STTS_CD=status, RLS_YN="Y", **extra)


def category(w: World, name: str = "생활체육") -> dict[str, Any]:
    return w.factory.make(
        "TB_CORS_CLSF", CORS_CLSF_NM=name, CLSF_NM_KEY=f"{name}{next(_keys)}", USE_YN="Y", DEL_YN="N"
    )


class Kit:
    """강좌 등록에 필요한 기준 정보(동·분류·강사·기수)."""

    def __init__(self, w: World) -> None:
        self.w = w
        self.dong = dong(w, "조리읍")
        self.category = category(w)
        self.instructor = instructor(w)
        self.cycle = make_cycle(w, EDU_CYCL=next(_keys) + 10)

    def body(self, **over: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "cycleId": str(self.cycle["EDU_CYCL_SN"]),
            "dongId": str(self.dong["DONG_SN"]),
            "classId": str(self.category["CORS_CLSF_SN"]),
            "name": "건강요가",
            "instructorId": str(self.instructor["INSTR_SN"]),
            "capacity": 10,
            "waitCapacity": 3,
            "tuition": 30000,
            "receptionStart": (START - DAY).isoformat() + "+00:00",
            "receptionEnd": (START + 20 * DAY).isoformat() + "+00:00",
            "outsideReceptionStart": None,
            "educationStart": "2026-11-15",
            "educationEnd": "2026-12-20",
            "description": "설명",
        }
        return {**base, **over}


def boss(w: World, *codes: str, **kw: Any) -> Actor:
    who = staff(w, f"e{next(_keys)}", *(codes or ("AU.CORS_R", "AU.CORS_W", "AU.CONF_W")), **kw)
    use(w, who)
    return who


def post_course(w: World, body: dict[str, Any], idem: str | None = None) -> Any:
    return call(w, "POST", "/courses", body, **{"Idempotency-Key": idem or key()})


def row(w: World, sql: str, **params: Any) -> Any:
    return w.db.execute(text(sql), params).mappings().one()


def cycle_body(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "2027년 제1기",
        "year": 2027,
        "order": 1,
        "receptionStart": "2026-12-01",
        "receptionEnd": "2026-12-10",
        "educationStart": "2027-01-04",
        "educationEnd": "2027-03-31",
        "status": "ACTIVE",
    }
    return {**base, **over}


def post_cycle(w: World, body: dict[str, Any], idem: str | None = None) -> Any:
    return call(w, "POST", "/cycles", body, **{"Idempotency-Key": idem or key()})


# --- 교육기수 ----------------------------------------------------------------------------------


def test_기수는_묶음_전체_설정_권한이_있어야_다룬다(world: World) -> None:
    use(world, staff(world, "x", "AU.CORS_R", "AU.CORS_W"))
    assert call(world, "GET", "/cycles").status_code == 403
    assert post_cycle(world, cycle_body()).status_code == 403
    mine = dong(world, "가동")
    use(world, staff(world, "d", "AU.CONF_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert call(world, "GET", "/cycles").status_code == 403  # 동 담당자는 묶음 공통 기수를 바꿀 수 없다(R28)
    assert post_cycle(world, cycle_body()).status_code == 403


def test_기수를_등록하면_모집_종료일은_그날_끝까지_포함해_읽힌다(world: World) -> None:
    boss(world)
    r = post_cycle(world, cycle_body())
    assert r.status_code == 201
    body = r.json()
    assert (body["receptionStart"], body["receptionEnd"], body["status"], body["courseCount"]) == (
        "2026-12-01",
        "2026-12-10",
        "ACTIVE",
        0,
    )
    saved = row(
        world,
        "SELECT RCPT_BGNG_DT, RCPT_END_DT, USE_YN FROM TB_EDU_CYCL WHERE EDU_CYCL_SN=:c",
        c=body["cycleId"],
    )
    assert (
        str(saved["RCPT_BGNG_DT"]) == "2026-11-30 15:00:00"
        and str(saved["RCPT_END_DT"]) == "2026-12-10 15:00:00"
    )
    assert saved["USE_YN"] == "Y"


def test_작성중과_사용중지는_연결_강좌_유무로_가른다(world: World) -> None:
    boss(world)
    first = post_cycle(world, cycle_body(status="DRAFT")).json()
    assert first["status"] == "DRAFT"
    cyc = post_cycle(world, cycle_body(order=2, status="INACTIVE")).json()
    assert cyc["status"] == "DRAFT"  # 강좌가 없으면 사용중이 아닌 기수는 작성중이다
    make_course(world, {"EDU_CYCL_SN": int(cyc["cycleId"])}, "연결")
    assert call(world, "GET", f"/cycles/{cyc['cycleId']}").json()["status"] == "INACTIVE"


def test_같은_연도_차수는_등록할_수_없다(world: World) -> None:
    boss(world)
    assert post_cycle(world, cycle_body()).status_code == 201
    dup = post_cycle(world, cycle_body(name="다른 이름"))
    assert dup.status_code == 422 and "order" in dup.json()["fields"]


def test_날짜_순서가_틀리면_필드별로_알린다(world: World) -> None:
    boss(world)
    r = post_cycle(
        world,
        cycle_body(
            receptionStart="2026-12-10",
            receptionEnd="2026-12-01",
            educationEnd="2026-12-31",
            educationStart="2027-01-04",
        ),
    )
    assert r.status_code == 422 and set(r.json()["fields"]) == {"receptionEnd", "educationEnd"}
    assert row(world, "SELECT COUNT(*) c FROM TB_EDU_CYCL")["c"] == 0


def test_기수_등록의_같은_키는_이전_결과이고_다른_내용이면_충돌이다(world: World) -> None:
    boss(world)
    idem = key()
    a, b = post_cycle(world, cycle_body(), idem), post_cycle(world, cycle_body(), idem)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["cycleId"] == b.json()["cycleId"]
    assert row(world, "SELECT COUNT(*) c FROM TB_EDU_CYCL")["c"] == 1
    clash = post_cycle(world, cycle_body(name="다른 기수"), idem)
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_기수_수정은_버전이_맞아야_하고_바뀐_내용이_읽힌다(world: World) -> None:
    boss(world)
    made = post_cycle(world, cycle_body()).json()
    stale = call(world, "PUT", f"/cycles/{made['cycleId']}", {**cycle_body(name="수정"), "version": 9})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    ok = call(
        world,
        "PUT",
        f"/cycles/{made['cycleId']}",
        {**cycle_body(name="수정", status="INACTIVE"), "version": 1},
    )
    assert ok.status_code == 200 and ok.json()["name"] == "수정" and ok.json()["version"] == 2
    assert row(world, "SELECT USE_YN u FROM TB_EDU_CYCL WHERE EDU_CYCL_SN=:c", c=made["cycleId"])["u"] == "N"
    assert call(world, "GET", "/cycles/99999999").status_code == 404


def test_기수_목록은_최근_연도와_차수가_먼저다(world: World) -> None:
    boss(world)
    for year, order in ((2026, 4), (2027, 1), (2026, 1)):
        post_cycle(world, cycle_body(year=year, order=order, name=f"{year}-{order}"))
    names = [c["name"] for c in call(world, "GET", "/cycles").json()["items"]]
    assert names == ["2027-1", "2026-4", "2026-1"]


# --- 강좌 등록·수정 -----------------------------------------------------------------------------


def test_강좌를_등록하면_작성중이고_기본값이_채워진다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    r = post_course(world, kit.body())
    assert r.status_code == 201
    body = r.json()
    assert (body["status"], body["capacity"], body["waitCapacity"], body["scheduleCount"]) == (
        "DRAFT",
        10,
        3,
        0,
    )
    assert body["actions"] == {
        "canEdit": True,
        "canPublish": True,
        "canCloseReception": False,
        "canCancel": False,
    }
    assert body["officialCapacity"] is None and body["occupied"] == 0
    saved = row(
        world,
        "SELECT STLM_WTNG_MINUTE m, CORS_STTS_CD s, EDU_BGNG_YMD b FROM TB_CORS WHERE CORS_SN=:c",
        c=body["courseId"],
    )
    assert (saved["m"], saved["s"], saved["b"]) == (10, "CS.DRAFT", "20261115")


def test_강좌_등록_권한이_없거나_범위_밖_동이면_거절한다(world: World) -> None:
    kit = Kit(world)
    other = dong(world, "나동")
    use(world, staff(world, "r", "AU.CORS_R"))
    assert post_course(world, kit.body()).status_code == 403
    use(world, staff(world, "d", "AU.CORS_R", "AU.CORS_W", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    assert post_course(world, kit.body(dongId=str(other["DONG_SN"]))).status_code == 403
    assert post_course(world, kit.body()).status_code == 201
    assert row(world, "SELECT COUNT(*) c FROM TB_CORS")["c"] == 1


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"cycleId": "99999"}, "cycleId"),
        ({"dongId": "99999"}, "dongId"),
        ({"classId": "99999"}, "classId"),
        ({"instructorId": "99999"}, "instructorId"),
        ({"receptionEnd": "2026-11-01T00:00:00+00:00"}, "receptionEnd"),
        ({"outsideReceptionStart": "2026-11-01T00:00:00+00:00"}, "outsideReceptionStart"),
        ({"educationEnd": "2026-11-01"}, "educationEnd"),
        ({"educationStart": "2026-10-01"}, "educationStart"),
        ({"educationEnd": "2027-02-01"}, "educationStart"),
    ],
    ids=[
        "기수없음",
        "동없음",
        "분류없음",
        "강사없음",
        "접수순서",
        "관외시작",
        "교육순서",
        "기수앞",
        "기수뒤",
    ],
)
def test_틀린_입력은_해당_필드의_사유로_거절한다(world: World, over: dict[str, Any], field: str) -> None:
    kit = Kit(world)
    boss(world)
    r = post_course(world, kit.body(**over))
    assert r.status_code == 422 and field in r.json()["fields"]
    assert row(world, "SELECT COUNT(*) c FROM TB_CORS")["c"] == 0


@pytest.mark.parametrize("status", ["IS.APPLY", "IS.REJECT", "IS.STOP"])
def test_승인되지_않은_강사는_배정할_수_없다(world: World, status: str) -> None:
    kit = Kit(world)
    kit.instructor = instructor(world, status)
    boss(world)
    r = post_course(world, kit.body())
    assert r.status_code == 422 and "instructorId" in r.json()["fields"]


def test_접수_종료는_접수_시작보다_뒤여야_하고_같으면_거절한다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    same = (START + DAY).isoformat() + "+00:00"
    r = post_course(world, kit.body(receptionStart=same, receptionEnd=same))
    assert r.status_code == 422 and "receptionEnd" in r.json()["fields"]


def test_접수기간이_끝난_공개_강좌는_수동_접수마감을_할_수_없다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    add_schedule(world, sn)
    call(world, "POST", f"/courses/{sn}/publish")
    world.db.execute(
        text("UPDATE TB_CORS SET RCPT_END_DT=:t WHERE CORS_SN=:c"),
        {"t": START - timedelta(minutes=1), "c": sn},
    )
    world.db.commit()
    shown = call(world, "GET", f"/courses/{sn}").json()
    assert shown["receptionState"] == "CLOSED" and shown["actions"]["canCloseReception"] is False
    r = call(world, "POST", f"/courses/{sn}/close-reception")
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"


def test_관외_접수_시작은_접수_시작_이상_종료_미만이면_받는다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    start, end = (START - DAY), (START + 20 * DAY)
    at_start = post_course(world, kit.body(outsideReceptionStart=start.isoformat() + "+00:00"))
    assert at_start.status_code == 201
    at_end = post_course(world, kit.body(outsideReceptionStart=end.isoformat() + "+00:00"))
    assert at_end.status_code == 422


def test_강좌_등록의_같은_키는_이전_결과이고_다른_내용이면_충돌이다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    idem = key()
    a, b = post_course(world, kit.body(), idem), post_course(world, kit.body(), idem)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["courseId"] == b.json()["courseId"]
    assert row(world, "SELECT COUNT(*) c FROM TB_CORS")["c"] == 1
    clash = post_course(world, kit.body(name="다른 강좌"), idem)
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_정원은_현재_점유보다_작게_줄일_수_없다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    made = post_course(world, kit.body()).json()
    sn = int(made["courseId"])
    for n in range(3):
        application(world, make_member(world, f"a{n}", **RESIDENT), {"CORS_SN": sn}, "ES.CONFIRM")
    world.db.commit()
    low = call(world, "PUT", f"/courses/{sn}", {**kit.body(capacity=2), "version": 1})
    assert low.status_code == 422 and "capacity" in low.json()["fields"]
    edge = call(world, "PUT", f"/courses/{sn}", {**kit.body(capacity=3), "version": 1})
    assert edge.status_code == 200 and edge.json()["capacity"] == 3 and edge.json()["occupied"] == 3


def test_결제대기와_수강확정만_점유로_세고_대기와_취소는_세지_않는다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    for state, extra in (
        ("ES.HOLD", {}),
        ("ES.CONFIRM", {}),
        ("ES.CANCEL", {}),
        ("ES.WAIT", {"WTNG_SEQ": 1}),
    ):
        application(world, make_member(world, f"a{next(_keys)}", **RESIDENT), {"CORS_SN": sn}, state, **extra)
    world.db.commit()
    assert call(world, "PUT", f"/courses/{sn}", {**kit.body(capacity=2), "version": 1}).status_code == 200
    assert call(world, "PUT", f"/courses/{sn}", {**kit.body(capacity=1), "version": 2}).status_code == 422


def test_강좌_수정은_버전이_맞아야_하고_폐강한_강좌는_고칠_수_없다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    stale = call(world, "PUT", f"/courses/{sn}", {**kit.body(name="수정"), "version": 5})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    world.db.execute(text("UPDATE TB_CORS SET CORS_STTS_CD='CS.CANCEL' WHERE CORS_SN=:c"), {"c": sn})
    world.db.commit()
    done = call(world, "PUT", f"/courses/{sn}", {**kit.body(name="수정"), "version": 1})
    assert done.status_code == 409 and done.json()["code"] == "CONFLICT_STATE"


def test_동_담당자는_강좌를_자기_범위_밖_동으로_옮길_수_없다(world: World) -> None:
    kit = Kit(world)
    other = dong(world, "나동")
    use(world, staff(world, "d", "AU.CORS_R", "AU.CORS_W", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    sn = int(post_course(world, kit.body()).json()["courseId"])
    moved = call(world, "PUT", f"/courses/{sn}", {**kit.body(dongId=str(other["DONG_SN"])), "version": 1})
    assert moved.status_code == 403
    assert row(world, "SELECT DONG_SN d FROM TB_CORS WHERE CORS_SN=:c", c=sn)["d"] == kit.dong["DONG_SN"]


# --- 공개·접수마감 ------------------------------------------------------------------------------


def add_schedule(w: World, sn: int) -> None:
    room = w.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.ROOM", FCLT_NM="1강의실", USE_YN="Y")
    w.factory.make(
        "TB_CORS_SCHDL",
        CORS_SN=sn,
        FCLT_SN=room["FCLT_SN"],
        DOW_CD="DW.MON",
        BGNG_TM="100000",
        END_TM="110000",
        APLCN_BGNG_YMD="20261115",
        APLCN_END_YMD="20261220",
    )


def test_공개_요청은_일정이_있어야_하고_성공하면_공개_상태가_된다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    no_schedule = call(world, "POST", f"/courses/{sn}/publish")
    assert no_schedule.status_code == 422 and "schedule" in no_schedule.json()["fields"]
    add_schedule(world, sn)
    ok = call(world, "POST", f"/courses/{sn}/publish")
    assert ok.status_code == 200 and ok.json()["status"] == "PUBLISHED" and ok.json()["scheduleCount"] == 1
    assert row(world, "SELECT CORS_STTS_CD s FROM TB_CORS WHERE CORS_SN=:c", c=sn)["s"] == "CS.OPEN"
    again = call(world, "POST", f"/courses/{sn}/publish")
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"


def test_공개_요청은_공개_시점에_강사_승인과_기간을_다시_검사한다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    add_schedule(world, sn)
    world.db.execute(
        text("UPDATE TB_INSTR SET INSTR_STTS_CD='IS.STOP' WHERE INSTR_SN=:i"),
        {"i": kit.instructor["INSTR_SN"]},
    )
    world.db.execute(text("UPDATE TB_CORS SET RCPT_END_DT=:t WHERE CORS_SN=:c"), {"t": START - DAY, "c": sn})
    world.db.commit()
    r = call(world, "POST", f"/courses/{sn}/publish")
    assert r.status_code == 422 and set(r.json()["fields"]) == {"instructorId", "receptionEnd"}
    assert row(world, "SELECT CORS_STTS_CD s FROM TB_CORS WHERE CORS_SN=:c", c=sn)["s"] == "CS.DRAFT"


def test_접수마감은_접수중인_공개_강좌만_할_수_있다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    assert call(world, "POST", f"/courses/{sn}/close-reception").status_code == 409  # 작성중
    add_schedule(world, sn)
    call(world, "POST", f"/courses/{sn}/publish")
    shown = call(world, "GET", f"/courses/{sn}").json()
    assert shown["actions"]["canCloseReception"] is True and shown["receptionState"] == "OPEN"
    closed = call(world, "POST", f"/courses/{sn}/close-reception")
    assert closed.status_code == 200 and closed.json()["status"] == "RECEPTION_CLOSED"
    assert (
        closed.json()["receptionState"] == "CLOSED" and closed.json()["actions"]["canCloseReception"] is False
    )
    assert call(world, "POST", f"/courses/{sn}/close-reception").status_code == 409


def test_읽기_권한만_있으면_조회는_되고_변경_버튼은_꺼진다(world: World) -> None:
    kit = Kit(world)
    boss(world)
    sn = int(post_course(world, kit.body()).json()["courseId"])
    use(world, staff(world, "reader", "AU.CORS_R"))
    shown = call(world, "GET", f"/courses/{sn}").json()
    assert shown["actions"] == {
        "canEdit": False,
        "canPublish": False,
        "canCloseReception": False,
        "canCancel": False,
    }
    assert call(world, "POST", f"/courses/{sn}/publish").status_code == 403
    assert call(world, "PUT", f"/courses/{sn}", {**kit.body(), "version": 1}).status_code == 403
    assert call(world, "POST", f"/courses/{sn}/cancel-course", {"reason": "x"}).status_code == 403


# --- 목록·선택지 --------------------------------------------------------------------------------


def test_목록은_범위_안의_강좌만_보이고_조건으로_거른다(world: World) -> None:
    kit = Kit(world)
    other = dong(world, "나동")
    cyc2 = make_cycle(world, "2기", EDU_CYCL=21)
    mine = make_course(
        world,
        kit.cycle,
        "요가",
        DONG_SN=kit.dong["DONG_SN"],
        CORS_CLSF_SN=kit.category["CORS_CLSF_SN"],
        INSTR_SN=kit.instructor["INSTR_SN"],
    )
    outside = make_course(world, cyc2, "탁구", DONG_SN=other["DONG_SN"])
    common = make_course(world, cyc2, "공통")
    use(world, staff(world, "d", "AU.CORS_R", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    items = call(world, "GET", "/courses").json()["items"]
    assert [i["courseId"] for i in items] == [str(mine["CORS_SN"])]
    assert (items[0]["cycleName"], items[0]["className"], items[0]["instructorName"]) == (
        kit.cycle["EDU_CYCL_NM"],
        "생활체육",
        "강사님",
    )
    assert call(world, "GET", f"/courses/{outside['CORS_SN']}").status_code == 404
    assert call(world, "GET", f"/courses/{common['CORS_SN']}").status_code == 404
    boss(world)

    def ids(query: str) -> list[str]:
        return [i["courseId"] for i in call(world, "GET", f"/courses?{query}").json()["items"]]

    assert len(ids("")) == 3
    assert ids("q=탁") == [str(outside["CORS_SN"])] and ids("q=%25") == []
    assert ids(f"cycleId={cyc2['EDU_CYCL_SN']}") == [str(common["CORS_SN"]), str(outside["CORS_SN"])]
    assert ids(f"dongId={other['DONG_SN']}") == [str(outside["CORS_SN"])]
    assert ids(f"classId={kit.category['CORS_CLSF_SN']}") == [str(mine["CORS_SN"])]
    assert ids("status=PUBLISHED") == [str(common["CORS_SN"]), str(outside["CORS_SN"]), str(mine["CORS_SN"])]
    assert ids("status=DRAFT") == []


def test_선택지는_승인_강사와_사용_중인_값만_담고_강좌는_범위_안만_담는다(world: World) -> None:
    kit = Kit(world)
    instructor(world, "IS.STOP")
    off = world.factory.make("TB_DONG", DONG_NM="폐지동", USE_YN="N")
    other = dong(world, "나동")
    center = world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.CENTER", FCLT_NM="조리센터", USE_YN="Y")
    world.factory.make(
        "TB_FCLT", FCLT_TYPE_CD="FT.ROOM", FCLT_NM="1강의실", UP_FCLT_SN=center["FCLT_SN"], USE_YN="Y"
    )
    world.factory.make("TB_FCLT", FCLT_TYPE_CD="FT.ROOM", FCLT_NM="중지실", USE_YN="N")
    mine = make_course(world, kit.cycle, "내강좌", DONG_SN=kit.dong["DONG_SN"])
    make_course(world, kit.cycle, "남의강좌", DONG_SN=other["DONG_SN"])
    use(world, staff(world, "d", "AU.CORS_R", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    options = call(world, "GET", "/course-options").json()
    assert [o["id"] for o in options["instructors"]] == [str(kit.instructor["INSTR_SN"])]
    assert str(off["DONG_SN"]) not in [o["id"] for o in options["dongs"]]
    assert [o["id"] for o in options["courses"]] == [str(mine["CORS_SN"])]
    assert [o["name"] for o in options["rooms"]] == ["조리센터 1강의실"]
    stopped = world.factory.make(
        "TB_CORS_CLSF", CORS_CLSF_NM="중지분류", CLSF_NM_KEY="stop", USE_YN="N", DEL_YN="N"
    )
    deleted = world.factory.make(
        "TB_CORS_CLSF", CORS_CLSF_NM="삭제분류", CLSF_NM_KEY="del", USE_YN="Y", DEL_YN="Y", DEL_DT=START
    )
    use(world, staff(world, "x", "AU.CORS_R"))
    listed = [o["id"] for o in call(world, "GET", "/course-options").json()["classes"]]
    assert listed == [str(kit.category["CORS_CLSF_SN"])]
    assert str(stopped["CORS_CLSF_SN"]) not in listed and str(deleted["CORS_CLSF_SN"]) not in listed
    use(world, staff(world, "y", "AU.STLM_R"))
    assert call(world, "GET", "/course-options").status_code == 403


# --- 폐강 ---------------------------------------------------------------------------------------


def open_course(kit: Kit, **values: Any) -> dict[str, Any]:
    return make_course(
        kit.w,
        kit.cycle,
        "폐강대상",
        DONG_SN=kit.dong["DONG_SN"],
        CORS_CLSF_SN=kit.category["CORS_CLSF_SN"],
        INSTR_SN=kit.instructor["INSTR_SN"],
        EDU_BGNG_YMD="20261201",
        EDU_END_YMD="20261231",
        **values,
    )


def applicant(
    w: World, row_: dict[str, Any], state: str, paid: str | None = None, amount: int = 30000, **values: Any
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    app = application(
        w,
        make_member(w, f"c{next(_keys)}", **RESIDENT),
        row_,
        state,
        TTCHG_AMT=amount,
        STLM_PRNMNT_AMT=amount,
        **values,
    )
    pay = payment(w, app, paid, STLM_AMT=amount) if paid else None
    return app, pay


def paid_app(
    w: World, row_: dict[str, Any], state: str, paid: str = "PS.PAID", amount: int = 30000
) -> tuple[dict[str, Any], dict[str, Any]]:
    app, pay = applicant(w, row_, state, paid, amount)
    assert pay is not None
    return app, pay


def states(w: World, row_: dict[str, Any]) -> dict[int, str]:
    rows = (
        w.db.execute(
            text("SELECT ATNLC_APLY_SN a, APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE CORS_SN=:c"),
            {"c": row_["CORS_SN"]},
        )
        .mappings()
        .all()
    )
    return {int(r["a"]): str(r["s"]) for r in rows}


def test_폐강_미리보기는_유효한_신청과_결제_건수를_준다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit)
    applicant(world, target, "ES.CONFIRM", "PS.PAID")
    applicant(world, target, "ES.HOLD", "PS.READY")
    applicant(world, target, "ES.WAIT", WTNG_SEQ=1)
    applicant(world, target, "ES.CANCEL", "PS.PAID")  # 이미 취소된 신청은 세지 않는다
    boss(world)
    assert call(world, "GET", f"/courses/{target['CORS_SN']}/cancel-preview").json() == {
        "applicationCount": 3,
        "paidCount": 1,
    }


def test_폐강하면_신청을_모두_취소하고_결제한_건은_전액_환불을_접수한다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit, RCRT_NOPE=2)
    confirmed, paid = paid_app(world, target, "ES.CONFIRM", "PS.PAID", 45000)
    holding, ready = paid_app(world, target, "ES.HOLD", "PS.READY")
    waiting, _ = applicant(world, target, "ES.WAIT", WTNG_SEQ=1)
    free, _ = applicant(world, target, "ES.CONFIRM", None, 0)
    who = boss(world)
    r = call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "정원 미달"})
    assert (
        r.status_code == 200
        and r.json()["status"] == "CANCELLED"
        and r.json()["actions"]["canCancel"] is False
    )
    assert set(states(world, target).values()) == {"ES.CANCEL"}
    refund = row(world, "SELECT * FROM TB_RFND")
    assert (refund["RFND_AMT"], refund["RFND_STTS_CD"], refund["STLM_SN"]) == (
        45000,
        "RS.REQUEST",
        paid["STLM_SN"],
    )
    assert (
        refund["DMND_MNGR_SN"] == who.sn
        and refund["DMND_MBR_SN"] is None
        and "정원 미달" in refund["RFND_RSN"]
    )
    assert (
        row(world, "SELECT STLM_STTS_CD s FROM TB_STLM WHERE STLM_SN=:s", s=ready["STLM_SN"])["s"]
        == "PS.CANCEL"
    )
    assert (
        row(world, "SELECT STLM_STTS_CD s FROM TB_STLM WHERE STLM_SN=:s", s=paid["STLM_SN"])["s"] == "PS.PAID"
    )  # 원결제는 그대로
    reason = row(
        world, "SELECT RTRCN_RSN r FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a", a=confirmed["ATNLC_APLY_SN"]
    )["r"]
    assert reason == "폐강" and holding and waiting and free
    job = row(world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CORS_CANCEL'")["c"]
    assert "신청 취소 4건" in job and "환불 접수 1건" in job


def test_폐강한_강좌는_대기자를_승격하지_않고_이미_취소된_신청은_그대로다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit, RCRT_NOPE=1)
    applicant(world, target, "ES.CONFIRM", "PS.PAID")
    applicant(world, target, "ES.WAIT", WTNG_SEQ=1)
    gone, _ = applicant(world, target, "ES.EXPIRE", RTRCN_DT=START, RTRCN_RSN="만료")
    boss(world)
    assert (
        call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "사유"}).status_code
        == 200
    )
    after = states(world, target)
    assert "ES.HOLD" not in after.values() and after[int(gone["ATNLC_APLY_SN"])] == "ES.EXPIRE"
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_SMS_DMND")).scalar() == 0


def test_결제_결과를_확인_중인_신청이_있으면_폐강을_막고_아무것도_바꾸지_않는다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit)
    applicant(world, target, "ES.CONFIRM", "PS.PAID")
    applicant(world, target, "ES.HOLD", "PS.PENDING")
    boss(world)
    r = call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "사유"})
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE" and "확인 중" in r.json()["message"]
    assert set(states(world, target).values()) == {"ES.CONFIRM", "ES.HOLD"}
    assert row(world, "SELECT COUNT(*) c FROM TB_RFND")["c"] == 0
    assert (
        row(world, "SELECT CORS_STTS_CD s FROM TB_CORS WHERE CORS_SN=:c", c=target["CORS_SN"])["s"]
        == "CS.OPEN"
    )


def test_이미_환불이_잡힌_결제는_남은_금액만_접수하고_다_잡혔으면_접수하지_않는다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit)
    partial, pay_a = paid_app(world, target, "ES.CONFIRM", "PS.PAID", 30000)
    full, pay_b = paid_app(world, target, "ES.CONFIRM", "PS.PAID", 20000)
    world.factory.make(
        "TB_RFND", STLM_SN=pay_a["STLM_SN"], RFND_AMT=12000, RFND_STTS_CD="RS.DONE", RFND_DT=START
    )
    world.factory.make(
        "TB_RFND", STLM_SN=pay_b["STLM_SN"], RFND_AMT=20000, RFND_STTS_CD="RS.DONE", RFND_DT=START
    )
    boss(world)
    assert (
        call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "사유"}).status_code
        == 200
    )
    amounts = sorted(
        r[0] for r in world.db.execute(text("SELECT RFND_AMT FROM TB_RFND WHERE RFND_STTS_CD='RS.REQUEST'"))
    )
    assert amounts == [18000] and partial and full


@pytest.mark.parametrize("code", ["CS.DRAFT", "CS.CANCEL", "CS.END"])
def test_공개_전이나_이미_폐강_종료된_강좌는_폐강할_수_없다(world: World, code: str) -> None:
    kit = Kit(world)
    target = open_course(kit, CORS_STTS_CD=code)
    boss(world)
    r = call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "사유"})
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"


def test_폐강_사유가_없으면_400이거나_422이고_바뀌지_않는다(world: World) -> None:
    kit = Kit(world)
    target = open_course(kit)
    applicant(world, target, "ES.CONFIRM", "PS.PAID")
    boss(world)
    for reason in ("", "   "):
        r = call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": reason})
        assert r.status_code in (400, 422)
    assert (
        row(world, "SELECT CORS_STTS_CD s FROM TB_CORS WHERE CORS_SN=:c", c=target["CORS_SN"])["s"]
        == "CS.OPEN"
    )


def test_범위_밖_강좌는_폐강할_수_없다(world: World) -> None:
    kit = Kit(world)
    other = dong(world, "나동")
    target = make_course(world, kit.cycle, "남의강좌", DONG_SN=other["DONG_SN"])
    use(world, staff(world, "d", "AU.CORS_R", "AU.CORS_W", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    assert (
        call(world, "POST", f"/courses/{target['CORS_SN']}/cancel-course", {"reason": "사유"}).status_code
        == 404
    )
    assert call(world, "GET", f"/courses/{target['CORS_SN']}/cancel-preview").status_code == 404
