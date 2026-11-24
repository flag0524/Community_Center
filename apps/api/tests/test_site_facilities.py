# 시설안내 공개 조회(사용 중 시설만, 층 표식, 운영묶음 경계, 로그인 없음)를 실제 MariaDB로 확인하는 시험
from typing import Any

import pytest

from tests.world import MEMBER, World

pytestmark = pytest.mark.db


def facility(w: World, name: str, kind: str = "FT.ROOM", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {"OPER_BNDL_SN": w.bundle, "FCLT_TYPE_CD": kind, "FCLT_NM": name}
    return w.factory.make("TB_FCLT", **{**defaults, **values})


def test_층_표식과_유형_코드는_관리자_시설_관리와_같다() -> None:
    from app.domain.admin import facility_service as admin
    from app.domain.site import facility as site

    assert site.FLOOR_LABEL == admin.FLOOR_LABEL
    assert site.CODE_KIND == {code: kind.value for kind, code in admin.KIND_CODE.items()}


def listed(w: World) -> list[dict[str, Any]]:
    response = w.client.get(f"{MEMBER}/site/facilities")
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def test_시설이_없으면_빈_목록이다(world: World) -> None:
    assert listed(world) == []


def test_센터가_먼저이고_그_아래_강의실이_이름순으로_온다(world: World) -> None:
    center = facility(world, "행정복지센터", "FT.CENTER", ADDR="파주시 조리읍")
    other = facility(world, "다른 센터", "FT.CENTER")
    facility(world, "컴퓨터실", UP_FCLT_SN=center["FCLT_SN"])
    facility(world, "강당", UP_FCLT_SN=center["FCLT_SN"])
    facility(world, "상담실", UP_FCLT_SN=other["FCLT_SN"])
    names = [(i["kind"], i["name"], i["parentId"]) for i in listed(world)]
    assert names == [
        ("CENTER", "행정복지센터", None),
        ("ROOM", "강당", str(int(center["FCLT_SN"]))),
        ("ROOM", "컴퓨터실", str(int(center["FCLT_SN"]))),
        ("CENTER", "다른 센터", None),
        ("ROOM", "상담실", str(int(other["FCLT_SN"]))),
    ]


def test_강의실은_층_순서로_오고_층이_없는_강의실은_뒤에_온다(world: World) -> None:
    center = facility(world, "행정복지센터", "FT.CENTER")
    facility(world, "가 교실", UP_FCLT_SN=center["FCLT_SN"])
    facility(world, "강당", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="층: 4층")
    facility(world, "공연장", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="층: 1층")
    facility(world, "민원실", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="층: 2층")
    assert [i["name"] for i in listed(world)] == ["행정복지센터", "공연장", "민원실", "강당", "가 교실"]


def test_층은_표식이_있을_때만_내고_주소는_그대로_낸다(world: World) -> None:
    center = facility(world, "행정복지센터", "FT.CENTER", ADDR="파주시 조리읍")
    facility(world, "강당", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="층: 3층")
    facility(world, "컴퓨터실", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="창가 쪽 교실")
    by_name = {i["name"]: i for i in listed(world)}
    assert by_name["강당"]["floor"] == "3층"
    assert by_name["컴퓨터실"]["floor"] is None  # 표식 없는 설명은 층이 아니므로 내지 않는다
    assert by_name["행정복지센터"]["address"] == "파주시 조리읍" and by_name["강당"]["address"] is None
    assert "explanation" not in by_name["강당"]  # 설명 원문은 내보내지 않는다


def test_사용_중지한_시설과_다른_운영묶음의_시설은_보이지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    facility(world, "남의 센터", "FT.CENTER", OPER_BNDL_SN=other)
    facility(world, "중지한 센터", "FT.CENTER", USE_YN="N")
    facility(world, "우리 센터", "FT.CENTER")
    assert [i["name"] for i in listed(world)] == ["우리 센터"]


def test_로그인_없이_읽고_쓰기는_받지_않는다(world: World) -> None:
    assert world.client.get(f"{MEMBER}/site/facilities").status_code == 200
    assert world.client.post(f"{MEMBER}/site/facilities", json={}).status_code in (403, 404, 405)
