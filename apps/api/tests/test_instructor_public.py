# 공개 강사 목록·상세(승인·공개한 강사, 강좌와 분야, 검색, 심사 정보 비공개)를 실제 앱과 DB로 확인하는 시험
import itertools
from typing import Any

import pytest

from tests.test_courses_public import course as make_course
from tests.test_courses_public import cycle as make_cycle
from tests.test_instructor_member import category
from tests.world import START, World, make_admin, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)
LIST = "/api/v1/instructors"


def teacher(
    w: World, name: str = "김강사", status: str = "IS.APPROVE", public: str = "Y", **values: Any
) -> dict[str, Any]:
    who = make_member(w, f"t{next(_n)}", MBR_NM=name)
    defaults: dict[str, Any] = {
        "MBR_SN": who["MBR_SN"],
        "INSTR_STTS_CD": status,
        "RLS_YN": public,
        "APRV_DT": START,
        "APRV_MNGR_SN": make_admin(w, f"ap{next(_n)}")["MNGR_SN"],
    }
    if status == "IS.STOP":
        defaults["RJCT_RSN"] = "사유"
    return w.factory.make("TB_INSTR", **{**defaults, **values})


def teach(w: World, who: dict[str, Any], name: str, cyc: dict[str, Any], **values: Any) -> dict[str, Any]:
    return make_course(w, cyc, name, INSTR_SN=who["INSTR_SN"], **values)


def names(w: World, qs: str = "") -> list[str]:
    return [i["name"] for i in w.client.get(f"{LIST}{qs}").json()["items"]]


def test_로그인하지_않아도_승인하고_공개한_강사만_가나다순으로_본다(world: World) -> None:
    teacher(world, "박강사")
    teacher(world, "가강사")
    teacher(world, "비공개", public="N")
    teacher(world, "활동중지", status="IS.STOP")
    teacher(world, "신청중", status="IS.APPLY", APRV_DT=None, APRV_MNGR_SN=None)
    teacher(world, "반려", status="IS.REJECT", RJCT_RSN="사유")
    res = world.client.get(LIST)
    assert res.status_code == 200
    body = res.json()
    assert [i["name"] for i in body["items"]] == ["가강사", "박강사"] and body["total"] == 2
    assert body["criteria"]["basisAt"]
    assert all(set(i) == {"instructorId", "name", "categoryName", "courseNames"} for i in body["items"])


def test_목록은_공개_강좌_이름과_가장_최근_강좌의_분야를_준다(world: World) -> None:
    cyc = make_cycle(world)
    who = teacher(world, "김강사")
    sports, arts = category(world, "생활체육"), category(world, "문화예술")
    teach(world, who, "서예", cyc, CORS_CLSF_SN=arts["CORS_CLSF_SN"])  # 먼저 만든 강좌
    teach(world, who, "요가", cyc, CORS_CLSF_SN=sports["CORS_CLSF_SN"])
    teach(
        world, who, "요가", cyc, CORS_CLSF_SN=sports["CORS_CLSF_SN"], CORS_STTS_CD="CS.CLOSE"
    )  # 같은 이름은 한 번만
    teach(world, who, "초안", cyc, CORS_STTS_CD="CS.DRAFT")
    teach(world, who, "폐강", cyc, CORS_STTS_CD="CS.CANCEL")
    other = teacher(world, "강좌없음")
    [item] = [i for i in world.client.get(LIST).json()["items"] if i["name"] == "김강사"]
    assert item["courseNames"] == ["서예", "요가"]  # 초안·폐강은 공개하지 않는다
    assert item["categoryName"] == "생활체육"  # 가장 나중에 만든 강좌의 분류
    empty = [i for i in world.client.get(LIST).json()["items"] if i["name"] == "강좌없음"][0]
    assert (empty["courseNames"], empty["categoryName"]) == ([], None) and other["INSTR_SN"]


def test_지운_분류는_분야로_쓰지_않는다(world: World) -> None:
    cyc = make_cycle(world)
    who = teacher(world)
    gone = category(world, "지운 분류", DEL_YN="Y")
    teach(world, who, "요가", cyc, CORS_CLSF_SN=gone["CORS_CLSF_SN"])
    [item] = world.client.get(LIST).json()["items"]
    assert (item["courseNames"], item["categoryName"]) == (["요가"], None)


def test_강사_이름이나_공개_강좌_이름으로_찾는다(world: World) -> None:
    cyc = make_cycle(world)
    a, b = teacher(world, "김요가"), teacher(world, "박서예")
    teach(world, a, "건강체조", cyc)
    teach(world, b, "서예기초", cyc)
    teach(world, b, "비밀초안", cyc, CORS_STTS_CD="CS.DRAFT")
    assert names(world, "?q=요가") == ["김요가"]
    assert names(world, "?q=서예") == ["박서예"]
    assert names(world, "?q=체조") == ["김요가"]
    assert names(world, "?q=비밀") == []  # 공개하지 않는 강좌 이름으로는 찾지 못한다
    assert names(world, "?q=_") == [] and names(world, "?q=%") == []
    assert names(world, "?q=%20") == ["김요가", "박서예"]


def test_쪽을_나누고_범위를_넘으면_거절한다(world: World) -> None:
    for n in range(3):
        teacher(world, f"강사{n}")
    sizes = [len(world.client.get(f"{LIST}?size=2&page={p}").json()["items"]) for p in (1, 2, 3)]
    assert sizes == [2, 1, 0]
    assert world.client.get(f"{LIST}?size=51").status_code in (400, 422)
    assert world.client.get(f"{LIST}?page=0").status_code in (400, 422)


def test_상세는_경력과_자격을_합쳐_주고_없으면_null이다(world: World) -> None:
    cyc = make_cycle(world)
    full = teacher(
        world, "김강사", CRR_CN="요가 지도 10년", QLFC_CN="생활스포츠지도사 2급", INSTR_INTRO_CN="소개글"
    )
    only = teacher(world, "박강사", CRR_CN="서예 5년")
    blank = teacher(world, "최강사", CRR_CN="  ")
    teach(world, full, "요가", cyc)
    out = world.client.get(f"{LIST}/{full['INSTR_SN']}").json()
    assert (out["name"], out["career"], out["courseNames"]) == (
        "김강사",
        "요가 지도 10년\n생활스포츠지도사 2급",
        ["요가"],
    )
    assert set(out) == {"instructorId", "name", "categoryName", "courseNames", "career"}
    assert world.client.get(f"{LIST}/{only['INSTR_SN']}").json()["career"] == "서예 5년"
    assert world.client.get(f"{LIST}/{blank['INSTR_SN']}").json()["career"] is None


def test_공개하지_않는_강사의_상세는_없는_것과_같다(world: World) -> None:
    hidden = {
        "비공개": teacher(world, public="N"),
        "활동중지": teacher(world, status="IS.STOP"),
        "반려": teacher(world, status="IS.REJECT", RJCT_RSN="사유"),
        "신청": teacher(world, status="IS.APPLY", APRV_DT=None, APRV_MNGR_SN=None),
    }
    for name, row in hidden.items():
        assert world.client.get(f"{LIST}/{row['INSTR_SN']}").status_code == 404, name
    assert world.client.get(f"{LIST}/999999999").status_code == 404
    assert world.client.get(f"{LIST}/abc").status_code in (400, 422)


def test_심사_정보와_연락처는_어떤_응답에도_없다(world: World) -> None:
    who = teacher(world, "김강사", CRR_CN="경력", RJCT_RSN="내부 메모")
    text = str(world.client.get(LIST).json()) + str(world.client.get(f"{LIST}/{who['INSTR_SN']}").json())
    for secret in ("내부 메모", "APRV", "RLS", "mblTelno", "phone"):
        assert secret not in text, secret
