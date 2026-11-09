# 강좌 분야·목록·상세·강의계획 공개 조회를 실제 앱과 MariaDB로 확인하는 시험
from datetime import datetime, timedelta
from typing import Any

import pytest

from tests.world import MEMBER, START, World, make_admin, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)


def cycle(w: World, name: str = "2026년 4분기", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "EDU_YR": "2026",
        "EDU_CYCL": 4,
        "EDU_CYCL_NM": name,
        "EDU_BGNG_YMD": "20261101",
        "EDU_END_YMD": "20261231",
        "RCPT_BGNG_DT": START - 10 * DAY,
        "RCPT_END_DT": START + 20 * DAY,
        "USE_YN": "Y",
    }
    return w.factory.make("TB_EDU_CYCL", **{**defaults, **values})


def course(w: World, cyc: dict[str, Any], name: str = "요가", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "EDU_CYCL_SN": cyc["EDU_CYCL_SN"],
        "CORS_NM": name,
        "CORS_STTS_CD": "CS.OPEN",
        "RCRT_NOPE": 10,
        "WTNG_NOPE": 5,
        "TTCHG": 30000,
        "RCPT_BGNG_DT": START - 5 * DAY,
        "RCPT_END_DT": START + 5 * DAY,
        "EDU_BGNG_YMD": "20261101",
        "EDU_END_YMD": "20261231",
        "STLM_WTNG_MINUTE": 10,
    }
    return w.factory.make("TB_CORS", **{**defaults, **values})


def get(w: World, path: str, **params: Any) -> Any:
    return w.client.get(f"{MEMBER}{path}", params=params)


def names(w: World, **params: Any) -> list[str]:
    body = get(w, "/courses", **params).json()
    return [item["name"] for item in body["items"]]


_applicants = iter(range(1, 10_000))


def apply(w: World, course_row: dict[str, Any], state: str, **values: Any) -> None:
    number = next(_applicants)
    member = make_member(w, f"app{number}")
    extra: dict[str, Any] = {}
    if state == "ES.WAIT":
        extra["WTNG_SEQ"] = number
    if state == "ES.HOLD":
        extra.update(SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START + timedelta(minutes=10))
    if state in ("ES.CONFIRM", "ES.COMPLETE"):
        extra["SEAT_ALTMNT_DT"] = START
    if state in ("ES.CANCEL", "ES.EXPIRE"):
        extra.update(RTRCN_DT=START, RTRCN_RSN="취소")
    w.factory.make(
        "TB_ATNLC_APLY",
        CORS_SN=course_row["CORS_SN"],
        MBR_SN=member["MBR_SN"],
        APLY_STTS_CD=state,
        **{**extra, **values},
    )


def instructor(w: World, name: str, *, status: str = "IS.APPROVE", public: str = "Y") -> dict[str, Any]:
    member = make_member(w, f"instr-{name}", MBR_NM=name)
    extra: dict[str, Any] = {}
    if status == "IS.APPROVE":
        extra.update(APRV_DT=START, APRV_MNGR_SN=make_admin(w, f"adm-{name}")["MNGR_SN"])
    return w.factory.make("TB_INSTR", MBR_SN=member["MBR_SN"], INSTR_STTS_CD=status, RLS_YN=public, **extra)


def schedule(
    w: World, course_row: dict[str, Any], day: str, start: str, end: str, room: str = "1강의실", **v: Any
) -> None:
    facility = w.factory.make("TB_FCLT", FCLT_NM=room)
    defaults: dict[str, Any] = {
        "CORS_SN": course_row["CORS_SN"],
        "FCLT_SN": facility["FCLT_SN"],
        "DOW_CD": f"DW.{day}",
        "BGNG_TM": start,
        "END_TM": end,
        "APLCN_BGNG_YMD": "20261101",
        "APLCN_END_YMD": "20261231",
    }
    w.factory.make("TB_CORS_SCHDL", **{**defaults, **v})  # 시험이 넘긴 값이 기본값을 이긴다


# --- 분야 ----------------------------------------------------------------------


def test_분야는_사용_중이고_삭제되지_않은_것만_정렬_순서로_준다(world: World) -> None:
    admin = make_admin(world)["MNGR_SN"]

    def category(name: str, key: str, order: int, **v: Any) -> dict[str, Any]:
        return world.factory.make(
            "TB_CORS_CLSF", CORS_CLSF_NM=name, CLSF_NM_KEY=key, SORT_SEQ=order, REG_MNGR_SN=admin, **v
        )

    second = category("건강", "건강", 2)
    first = category("문화", "문화", 1)
    category("쉬는분야", "쉬는분야", 3, USE_YN="N")
    category("지운분야", "지운분야", 4, DEL_YN="Y", DEL_DT=START)
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    world.factory.make(
        "TB_CORS_CLSF", OPER_BNDL_SN=other, CORS_CLSF_NM="남의분야", CLSF_NM_KEY="남의분야", REG_MNGR_SN=admin
    )
    assert get(world, "/categories").json() == {
        "items": [
            {"categoryId": str(first["CORS_CLSF_SN"]), "name": "문화"},
            {"categoryId": str(second["CORS_CLSF_SN"]), "name": "건강"},
        ]
    }


# --- 목록: 기준 기수와 공개 범위 -------------------------------------------------------


def test_기수가_없으면_빈_목록이고_기준_기수도_비어_있다(world: World) -> None:
    body = get(world, "/courses").json()
    assert body["items"] == [] and body["total"] == 0 and body["criteria"]["cycle"] is None
    assert body["criteria"]["basisAt"].startswith("2026-11-09T09:00:00")


def test_기준_기수는_교육이_끝나지_않은_기수_중_가장_이른_것이다(world: World) -> None:
    past = cycle(world, "지난 기수", EDU_CYCL=1, EDU_BGNG_YMD="20260101", EDU_END_YMD="20260331")
    now = cycle(world, "이번 기수", EDU_CYCL=4)
    later = cycle(
        world, "다음 기수", EDU_CYCL=5, EDU_YR="2027", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331"
    )
    course(world, past, "지난 강좌", EDU_BGNG_YMD="20260101", EDU_END_YMD="20260331")
    course(world, now, "이번 강좌")
    course(world, later, "다음 강좌", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331")
    body = get(world, "/courses").json()
    assert [i["name"] for i in body["items"]] == ["이번 강좌"]
    assert body["criteria"]["cycle"]["name"] == "이번 기수"


def test_모든_기수가_끝났으면_가장_최근에_끝난_기수를_기준으로_한다(world: World) -> None:
    old = cycle(world, "옛 기수", EDU_CYCL=1, EDU_BGNG_YMD="20250101", EDU_END_YMD="20250331")
    recent = cycle(world, "최근 기수", EDU_CYCL=2, EDU_BGNG_YMD="20260101", EDU_END_YMD="20260331")
    course(world, old, "옛 강좌", EDU_BGNG_YMD="20250101", EDU_END_YMD="20250331")
    course(world, recent, "최근 강좌", EDU_BGNG_YMD="20260101", EDU_END_YMD="20260331")
    assert names(world) == ["최근 강좌"]


def test_교육_종료일_당일까지는_그_기수가_기준이다(world: World) -> None:
    # 한국 날짜 기준이다. START는 한국 시각 11월 9일 18시다
    ending = cycle(world, "오늘 끝나는 기수", EDU_CYCL=1, EDU_BGNG_YMD="20260901", EDU_END_YMD="20261109")
    cycle(world, "다음 기수", EDU_CYCL=2, EDU_BGNG_YMD="20261201", EDU_END_YMD="20261231")
    course(world, ending, "마지막 날 강좌", EDU_BGNG_YMD="20260901", EDU_END_YMD="20261109")
    assert get(world, "/courses").json()["criteria"]["cycle"]["name"] == "오늘 끝나는 기수"


def test_사용하지_않는_기수는_기준이_되지_않는다(world: World) -> None:
    unused = cycle(world, "중지 기수", USE_YN="N")
    course(world, unused, "중지 강좌")
    assert get(world, "/courses").json()["criteria"]["cycle"] is None


def test_작성중_종료_폐강_강좌는_보이지_않고_공개_마감_운영중은_보인다(world: World) -> None:
    cyc = cycle(world)
    for state, name in [
        ("CS.DRAFT", "작성중"),
        ("CS.OPEN", "공개"),
        ("CS.CLOSE", "마감"),
        ("CS.RUN", "운영중"),
        ("CS.END", "종료"),
        ("CS.CANCEL", "폐강"),
    ]:
        course(world, cyc, name, CORS_STTS_CD=state)
    assert names(world) == ["공개", "마감", "운영중"]
    assert get(world, "/courses").json()["total"] == 3


def test_다른_운영묶음의_강좌는_보이지_않는다(world: World) -> None:
    cyc = cycle(world)
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    other_cycle = cycle(world, OPER_BNDL_SN=other)
    course(world, cyc, "우리 강좌")
    course(world, other_cycle, "남의 강좌", OPER_BNDL_SN=other)
    assert names(world) == ["우리 강좌"]


# --- 목록: 항목 내용 -----------------------------------------------------------------


def test_목록_항목은_정원_수강료_기간과_두_가지_상태를_담는다(world: World) -> None:
    cyc = cycle(world)
    row = course(world, cyc, "요가", TTCHG=45000, RCRT_NOPE=12)
    item = get(world, "/courses").json()["items"][0]
    assert item["courseId"] == str(row["CORS_SN"]) and item["name"] == "요가"
    assert item["fee"] == 45000 and item["capacity"] == 12 and item["remainingSeats"] == 12
    assert item["waitingCount"] == 0
    assert item["educationStart"] == "2026-11-01" and item["educationEnd"] == "2026-12-31"
    assert item["receptionState"] == "OPEN" and item["educationState"] == "ONGOING"
    assert item["receptionStart"].startswith("2026-11-04T09:00:00")
    assert item["receptionEnd"].startswith("2026-11-14T09:00:00")
    assert item["category"] is None and item["instructorName"] is None
    assert item["schedules"] == [] and item["room"] is None


def test_잔여석은_보류와_확정만_세고_대기_취소_만료는_세지_않는다(world: World) -> None:
    cyc = cycle(world)
    row = course(world, cyc, "요가", RCRT_NOPE=10)
    for state in ["ES.HOLD", "ES.HOLD", "ES.CONFIRM", "ES.COMPLETE", "ES.WAIT", "ES.CANCEL", "ES.EXPIRE"]:
        apply(world, row, state)
    item = get(world, "/courses").json()["items"][0]
    # 문서의 점유 상태는 ES.HOLD·ES.CONFIRM이다(ADR-028). 수강 완료 신청은 정원을 차지하지 않는다
    assert item["remainingSeats"] == 7 and item["waitingCount"] == 1


def test_잔여석은_0_밑으로_내려가지_않는다(world: World) -> None:
    cyc = cycle(world)
    row = course(world, cyc, "요가", RCRT_NOPE=1)
    apply(world, row, "ES.CONFIRM")
    apply(world, row, "ES.HOLD")
    assert get(world, "/courses").json()["items"][0]["remainingSeats"] == 0


def test_다른_강좌의_신청은_세지_않는다(world: World) -> None:
    cyc = cycle(world)
    a = course(world, cyc, "가")
    b = course(world, cyc, "나")
    apply(world, a, "ES.CONFIRM")
    apply(world, a, "ES.WAIT")
    items = {i["name"]: i for i in get(world, "/courses").json()["items"]}
    assert items["가"]["remainingSeats"] == 9 and items["가"]["waitingCount"] == 1
    assert items["나"]["remainingSeats"] == 10 and items["나"]["waitingCount"] == 0
    assert b["CORS_SN"] != a["CORS_SN"]


def test_분류와_공개_강사는_이름이_나가고_숨긴_강사는_나가지_않는다(world: World) -> None:
    cyc = cycle(world)
    admin = make_admin(world)["MNGR_SN"]
    clsf = world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="건강", CLSF_NM_KEY="건강", REG_MNGR_SN=admin)
    shown = instructor(world, "공개강사")
    hidden = instructor(world, "비공개강사", public="N")
    pending = instructor(world, "미승인강사", status="IS.APPLY")
    course(world, cyc, "가", INSTR_SN=shown["INSTR_SN"], CORS_CLSF_SN=clsf["CORS_CLSF_SN"])
    course(world, cyc, "나", INSTR_SN=hidden["INSTR_SN"])
    course(world, cyc, "다", INSTR_SN=pending["INSTR_SN"])
    items = {i["name"]: i for i in get(world, "/courses").json()["items"]}
    assert items["가"]["instructorName"] == "공개강사"
    assert items["가"]["category"] == {"categoryId": str(clsf["CORS_CLSF_SN"]), "name": "건강"}
    assert items["나"]["instructorName"] is None and items["다"]["instructorName"] is None


def test_사용_중지하거나_삭제한_분류는_강좌에_붙어_있어도_나가지_않는다(world: World) -> None:
    cyc = cycle(world)
    admin = make_admin(world)["MNGR_SN"]
    stopped = world.factory.make(
        "TB_CORS_CLSF", CORS_CLSF_NM="중지", CLSF_NM_KEY="중지", REG_MNGR_SN=admin, USE_YN="N"
    )
    course(world, cyc, "가", CORS_CLSF_SN=stopped["CORS_CLSF_SN"])
    assert get(world, "/courses").json()["items"][0]["category"] is None


def test_일정은_같은_시간대의_요일을_한_줄로_묶고_요일_순으로_준다(world: World) -> None:
    cyc = cycle(world)
    row = course(world, cyc, "요가")
    schedule(world, row, "WED", "090000", "100000", "1강의실")
    schedule(world, row, "MON", "090000", "100000", "1강의실")
    schedule(world, row, "FRI", "140000", "153000", "2강의실")
    item = get(world, "/courses").json()["items"][0]
    assert item["schedules"] == [
        {"days": ["MON", "WED"], "startTime": "09:00", "endTime": "10:00", "label": None},
        {"days": ["FRI"], "startTime": "14:00", "endTime": "15:30", "label": None},
    ]
    assert item["room"] == "1강의실, 2강의실"


def test_적용_기간이_끝난_일정은_보이지_않는다(world: World) -> None:
    cyc = cycle(world)
    row = course(world, cyc, "요가")
    schedule(
        world, row, "MON", "090000", "100000", APLCN_BGNG_YMD="20261101", APLCN_END_YMD="20261108"
    )  # 어제 종료
    schedule(
        world, row, "TUE", "090000", "100000", "2강의실", APLCN_BGNG_YMD="20261101", APLCN_END_YMD="20261109"
    )  # 오늘 종료
    item = get(world, "/courses").json()["items"][0]
    assert [slot["days"] for slot in item["schedules"]] == [["TUE"]]


# --- 목록: 검색과 거름 -----------------------------------------------------------------


def test_검색어는_강좌명이나_공개_강사명에_맞는다(world: World) -> None:
    cyc = cycle(world)
    teacher = instructor(world, "김선생")
    hidden = instructor(world, "박숨김", public="N")
    course(world, cyc, "요가 초급")
    course(world, cyc, "라인댄스", INSTR_SN=teacher["INSTR_SN"])
    course(world, cyc, "서예", INSTR_SN=hidden["INSTR_SN"])
    assert names(world, q="요가") == ["요가 초급"]
    assert names(world, q="김선") == ["라인댄스"]
    assert names(world, q="박숨김") == []  # 숨긴 강사의 이름으로는 찾을 수 없다
    assert names(world, q="  요가  ") == ["요가 초급"]
    assert names(world, q="   ") == ["요가 초급", "라인댄스", "서예"]


def test_검색어의_퍼센트와_밑줄은_글자로_취급한다(world: World) -> None:
    cyc = cycle(world)
    course(world, cyc, "요가")
    course(world, cyc, "100% 건강")
    course(world, cyc, "a_b")
    assert names(world, q="%") == ["100% 건강"]
    assert names(world, q="_") == ["a_b"]


def test_분야로_거른다(world: World) -> None:
    cyc = cycle(world)
    admin = make_admin(world)["MNGR_SN"]
    a = world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="가", CLSF_NM_KEY="가", REG_MNGR_SN=admin)
    b = world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="나", CLSF_NM_KEY="나", REG_MNGR_SN=admin)
    course(world, cyc, "A강좌", CORS_CLSF_SN=a["CORS_CLSF_SN"])
    course(world, cyc, "B강좌", CORS_CLSF_SN=b["CORS_CLSF_SN"])
    course(world, cyc, "무분류")
    assert names(world, categoryId=str(a["CORS_CLSF_SN"])) == ["A강좌"]


def test_요일로_거른다(world: World) -> None:
    cyc = cycle(world)
    mon = course(world, cyc, "월요강좌")
    tue = course(world, cyc, "화요강좌")
    schedule(world, mon, "MON", "090000", "100000")
    schedule(world, tue, "TUE", "090000", "100000")
    schedule(world, tue, "MON", "090000", "100000", "2강의실", APLCN_END_YMD="20261108")  # 이미 끝난 월요일
    assert names(world, day="MON") == ["월요강좌"]
    assert names(world, day="TUE") == ["화요강좌"]
    assert names(world, day="SUN") == []


def test_접수_상태로_거르고_상태_판정은_경계에서_정확하다(world: World) -> None:
    cyc = cycle(world)
    course(world, cyc, "접수전", RCPT_BGNG_DT=START + timedelta(seconds=1), RCPT_END_DT=START + 5 * DAY)
    course(world, cyc, "시작정각", RCPT_BGNG_DT=START, RCPT_END_DT=START + 5 * DAY)
    course(world, cyc, "종료정각", RCPT_BGNG_DT=START - 5 * DAY, RCPT_END_DT=START)
    course(world, cyc, "종료직전", RCPT_BGNG_DT=START - 5 * DAY, RCPT_END_DT=START + timedelta(seconds=1))
    course(world, cyc, "수동마감", CORS_STTS_CD="CS.CLOSE")
    course(world, cyc, "운영중", CORS_STTS_CD="CS.RUN")
    assert names(world, status="UPCOMING") == ["접수전"]
    assert names(world, status="OPEN") == ["시작정각", "종료직전"]
    assert names(world, status="CLOSED") == ["종료정각", "수동마감", "운영중"]
    states = {i["name"]: i["receptionState"] for i in get(world, "/courses").json()["items"]}
    assert states == {
        "접수전": "UPCOMING",
        "시작정각": "OPEN",
        "종료정각": "CLOSED",
        "종료직전": "OPEN",
        "수동마감": "CLOSED",
        "운영중": "CLOSED",
    }


def test_조건은_함께_적용된다(world: World) -> None:
    cyc = cycle(world)
    a = course(world, cyc, "요가 월")
    b = course(world, cyc, "요가 화")
    schedule(world, a, "MON", "090000", "100000")
    schedule(world, b, "TUE", "090000", "100000")
    assert names(world, q="요가", day="MON", status="OPEN") == ["요가 월"]
    assert names(world, q="요가", day="MON", status="CLOSED") == []


def test_쪽_나누기는_번호_순이고_전체_건수는_쪽과_무관하다(world: World) -> None:
    cyc = cycle(world)
    for index in range(1, 6):
        course(world, cyc, f"강좌{index}")
    first = get(world, "/courses", size=2).json()
    second = get(world, "/courses", size=2, page=2).json()
    last = get(world, "/courses", size=2, page=3).json()
    beyond = get(world, "/courses", size=2, page=4).json()
    assert [i["name"] for i in first["items"]] == ["강좌1", "강좌2"]
    assert [i["name"] for i in second["items"]] == ["강좌3", "강좌4"]
    assert [i["name"] for i in last["items"]] == ["강좌5"] and beyond["items"] == []
    assert first["total"] == second["total"] == last["total"] == beyond["total"] == 5
    assert (first["page"], first["size"]) == (1, 2)
    assert len(get(world, "/courses").json()["items"]) == 5  # 기본 10건


def test_쪽_번호와_크기가_범위를_벗어나면_400이다(world: World) -> None:
    for params in (
        {"page": 0},
        {"size": 0},
        {"size": 51},
        {"day": "XXX"},
        {"status": "NOPE"},
        {"categoryId": "abc"},
    ):
        assert get(world, "/courses", **params).status_code == 400


def test_기준_기수_정보는_접수_상태까지_담는다(world: World) -> None:
    cycle(world, "이번 기수", RCPT_BGNG_DT=START + DAY, RCPT_END_DT=START + 9 * DAY)
    info = get(world, "/courses").json()["criteria"]["cycle"]
    assert info["name"] == "이번 기수" and info["receptionState"] == "UPCOMING"
    assert info["educationStart"] == "2026-11-01" and info["educationEnd"] == "2026-12-31"
    assert info["receptionStart"].startswith("2026-11-10T09:00:00")


# --- 상세 ----------------------------------------------------------------------------


def test_상세는_목록_항목에_기수_대기_정원_관외_개방_설명을_더한다(world: World) -> None:
    cyc = cycle(world, "2026년 4분기")
    row = course(
        world,
        cyc,
        "요가",
        WTNG_NOPE=7,
        LCTR_CN="몸을 풉니다.",
        OTSD_RGN_RCPT_BGNG_DT=START + DAY,
    )
    body = get(world, f"/courses/{row['CORS_SN']}").json()
    assert body["name"] == "요가" and body["cycleName"] == "2026년 4분기" and body["waitCapacity"] == 7
    assert body["description"] == "몸을 풉니다."
    assert body["outOfAreaReceptionStart"].startswith("2026-11-10T09:00:00")
    assert body["serverNow"].startswith("2026-11-09T09:00:00")
    assert body["hasPlan"] is False and body["receptionState"] == "OPEN"


def test_상세는_관외_개방이_없으면_null이고_설명이_없으면_null이다(world: World) -> None:
    row = course(world, cycle(world), "요가")
    body = get(world, f"/courses/{row['CORS_SN']}").json()
    assert body["outOfAreaReceptionStart"] is None and body["description"] is None


def test_상세의_잔여석과_대기는_목록과_같다(world: World) -> None:
    row = course(world, cycle(world), "요가", RCRT_NOPE=4)
    apply(world, row, "ES.CONFIRM")
    apply(world, row, "ES.WAIT")
    body = get(world, f"/courses/{row['CORS_SN']}").json()
    listed = get(world, "/courses").json()["items"][0]
    assert body["remainingSeats"] == listed["remainingSeats"] == 3
    assert body["waitingCount"] == listed["waitingCount"] == 1


def test_상세는_기준_기수가_아닌_강좌도_보여_준다(world: World) -> None:
    cycle(world, "이번 기수")
    later = cycle(
        world, "다음 기수", EDU_CYCL=5, EDU_YR="2027", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331"
    )
    row = course(world, later, "다음 강좌", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331")
    body = get(world, f"/courses/{row['CORS_SN']}").json()
    assert body["cycleName"] == "다음 기수" and body["educationState"] == "UPCOMING"


@pytest.mark.parametrize("state", ["CS.DRAFT", "CS.END", "CS.CANCEL"])
def test_작성중_종료_폐강_강좌의_상세와_계획은_404다(world: World, state: str) -> None:
    row = course(world, cycle(world), "숨김", CORS_STTS_CD=state)
    assert get(world, f"/courses/{row['CORS_SN']}").status_code == 404
    assert get(world, f"/courses/{row['CORS_SN']}/plan").status_code == 404


def test_없거나_다른_운영묶음의_강좌는_404다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    row = course(world, cycle(world, OPER_BNDL_SN=other), "남의 강좌", OPER_BNDL_SN=other)
    assert get(world, f"/courses/{row['CORS_SN']}").status_code == 404
    assert get(world, "/courses/99999999").status_code == 404
    assert get(world, "/courses/abc").status_code == 400


@pytest.mark.parametrize("state", ["CS.OPEN", "CS.CLOSE", "CS.RUN"])
def test_교육_상태는_교육기간으로_판정한다(world: World, state: str) -> None:
    cyc = cycle(world)
    cases = {
        "UPCOMING": ("20261110", "20261231"),
        "ONGOING": ("20261109", "20261109"),  # 오늘 하루짜리
        "ENDED": ("20261001", "20261108"),
    }
    for expected, (begin, end) in cases.items():
        row = course(
            world, cyc, f"{expected}{state}", CORS_STTS_CD=state, EDU_BGNG_YMD=begin, EDU_END_YMD=end
        )
        assert get(world, f"/courses/{row['CORS_SN']}").json()["educationState"] == expected


def test_교육_상태는_한국_날짜로_판정한다(world: World) -> None:
    # 2026-11-09 16:00 UTC는 한국 시각으로 11월 10일 01시다
    world.clock.now = datetime(2026, 11, 9, 16, 0, 0)
    cyc = cycle(world)
    row = course(world, cyc, "어제까지", EDU_BGNG_YMD="20261101", EDU_END_YMD="20261109")
    assert get(world, f"/courses/{row['CORS_SN']}").json()["educationState"] == "ENDED"


# --- 강의계획 ------------------------------------------------------------------------


def plan_file(w: World, row: dict[str, Any], **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "CORS_SN": row["CORS_SN"],
        "FILE_USE_CD": "FP.PLAN",
        "FILE_STTS_CD": "FS.SAFE",
        "FILE_NM": "계획서.pdf",
        "FILE_SZ": 2048,
    }
    return w.factory.make("TB_FILE", **{**defaults, **values})


def test_강의계획이_없으면_본문도_파일도_없다(world: World) -> None:
    row = course(world, cycle(world), "요가")
    assert get(world, f"/courses/{row['CORS_SN']}/plan").json() == {
        "courseId": str(row["CORS_SN"]),
        "planText": None,
        "planFile": None,
    }
    assert get(world, f"/courses/{row['CORS_SN']}").json()["hasPlan"] is False


def test_강의계획_본문이_있으면_계획이_있다고_알린다(world: World) -> None:
    row = course(world, cycle(world), "요가", LCTR_PLAN_CN="1주차 호흡")
    assert get(world, f"/courses/{row['CORS_SN']}/plan").json()["planText"] == "1주차 호흡"
    assert get(world, f"/courses/{row['CORS_SN']}").json()["hasPlan"] is True


def test_공백뿐인_계획_본문은_계획이_아니다(world: World) -> None:
    row = course(world, cycle(world), "요가", LCTR_PLAN_CN="   ")
    assert get(world, f"/courses/{row['CORS_SN']}").json()["hasPlan"] is False


def test_검사를_통과한_계획서_파일만_내려_준다(world: World) -> None:
    row = course(world, cycle(world), "요가")
    plan_file(world, row, FILE_STTS_CD="FS.PENDING", FILE_NM="검사전.pdf")
    plan_file(world, row, FILE_STTS_CD="FS.BLOCK", FILE_NM="차단.pdf")
    plan_file(world, row, FILE_USE_CD="FP.ATTACH", FILE_NM="첨부.pdf")
    assert get(world, f"/courses/{row['CORS_SN']}/plan").json()["planFile"] is None
    assert get(world, f"/courses/{row['CORS_SN']}").json()["hasPlan"] is False
    good = plan_file(world, row, FILE_NM="좋은계획서.pdf", FILE_SZ=4096)
    body = get(world, f"/courses/{row['CORS_SN']}/plan").json()
    assert body["planFile"] == {"fileId": str(good["FILE_SN"]), "name": "좋은계획서.pdf", "sizeBytes": 4096}
    assert get(world, f"/courses/{row['CORS_SN']}").json()["hasPlan"] is True


def test_계획서가_여럿이면_정렬_순서가_앞선_것을_준다(world: World) -> None:
    row = course(world, cycle(world), "요가")
    plan_file(world, row, FILE_NM="뒤.pdf", SORT_SEQ=2)
    plan_file(world, row, FILE_NM="앞.pdf", SORT_SEQ=1)
    assert get(world, f"/courses/{row['CORS_SN']}/plan").json()["planFile"]["name"] == "앞.pdf"


def test_다른_강좌의_계획서는_섞이지_않는다(world: World) -> None:
    cyc = cycle(world)
    a = course(world, cyc, "가")
    b = course(world, cyc, "나")
    plan_file(world, a, FILE_NM="가계획.pdf")
    assert get(world, f"/courses/{b['CORS_SN']}/plan").json()["planFile"] is None
