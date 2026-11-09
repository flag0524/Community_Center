# 약관·안내 글·센터 연락처 공개 조회를 실제 앱과 MariaDB로 확인하는 시험
import json
from datetime import datetime, timedelta
from typing import Any

import pytest

from app.auth.deps import get_bundle_resolver
from app.db import tables
from tests.world import MEMBER, START, FixedBundle, World

pytestmark = pytest.mark.db

HISTORY = {
    "subtitle": "걸어온 길",
    "sections": [
        {
            "heading": "연혁",
            "paragraphs": ["조리읍 주민자치센터"],
            "steps": [],
            "items": [{"label": "2020", "text": "개소"}],
            "table": None,
            "links": [],
        }
    ],
}


def publish(w: World, content_type: str, content_id: str, body: str, **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "CONTS_TYPE_CD": content_type,
        "CONTS_ID": content_id,
        "CONTS_TTL": f"{content_id} 제목",
        "CONTS_CN": body,
        "VER_NM": "v1",
        "PSTG_YN": "Y",
    }
    return w.factory.make("TB_SITE_CONTS", **{**defaults, **values})


# --- 약관 ----------------------------------------------------------------------


def test_약관은_로그인_없이_게시_중인_가장_최근_버전을_준다(world: World) -> None:
    publish(world, "CT.TERMS", "terms", "옛 본문", VER_NM="v1")
    publish(world, "CT.TERMS", "terms", "새 본문", VER_NM="v2", CONTS_TTL="이용약관")
    body = world.client.get(f"{MEMBER}/terms/TERMS_OF_USE").json()
    assert body["termType"] == "TERMS_OF_USE" and body["version"] == "v2"
    assert body["title"] == "이용약관" and body["body"] == "새 본문"


def test_버전을_지정하면_그_버전을_준다(world: World) -> None:
    publish(world, "CT.TERMS", "terms", "옛 본문", VER_NM="v1")
    publish(world, "CT.TERMS", "terms", "새 본문", VER_NM="v2")
    body = world.client.get(f"{MEMBER}/terms/TERMS_OF_USE", params={"version": "v1"}).json()
    assert body["version"] == "v1" and body["body"] == "옛 본문"
    assert world.client.get(f"{MEMBER}/terms/TERMS_OF_USE", params={"version": "v9"}).status_code == 404


@pytest.mark.parametrize(
    ("term_type", "content_type"),
    [("TERMS_OF_USE", "CT.TERMS"), ("PRIVACY_CONSENT", "CT.PRIVACY"), ("MARKETING_CONSENT", "CT.MARKET")],
)
def test_약관_유형마다_자기_콘텐츠_유형만_본다(world: World, term_type: str, content_type: str) -> None:
    for code in ("CT.TERMS", "CT.PRIVACY", "CT.MARKET"):
        publish(world, code, code, f"{code} 본문", CONTS_TTL=code)
    body = world.client.get(f"{MEMBER}/terms/{term_type}").json()
    assert body["body"] == f"{content_type} 본문"


@pytest.mark.parametrize(
    "values",
    [
        {"PSTG_YN": "N"},
        {"PSTG_END_DT": START},  # 지금 종료
        {"PSTG_BGNG_DT": START + timedelta(seconds=1)},  # 아직 시작 전
    ],
    ids=["미게시", "게시_종료", "게시_시작_전"],
)
def test_게시_중이_아닌_약관은_404다(world: World, values: dict[str, Any]) -> None:
    publish(world, "CT.TERMS", "terms", "본문", **values)
    assert world.client.get(f"{MEMBER}/terms/TERMS_OF_USE").status_code == 404


def test_게시_시작_시각_정각과_종료_하루_전은_보인다(world: World) -> None:
    publish(world, "CT.TERMS", "terms", "본문", PSTG_BGNG_DT=START, PSTG_END_DT=START + timedelta(seconds=1))
    assert world.client.get(f"{MEMBER}/terms/TERMS_OF_USE").status_code == 200


def test_다른_운영묶음의_약관은_보이지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    publish(world, "CT.TERMS", "terms", "남의 본문", OPER_BNDL_SN=other)
    assert world.client.get(f"{MEMBER}/terms/TERMS_OF_USE").status_code == 404


def test_시행일은_한국_날짜로_바꿔_준다(world: World) -> None:
    # 2026-11-08 20:00 UTC는 한국 시각으로 11월 9일 05시다
    publish(world, "CT.TERMS", "terms", "본문", PSTG_BGNG_DT=START.replace(day=8, hour=20))
    assert world.client.get(f"{MEMBER}/terms/TERMS_OF_USE").json()["effectiveOn"] == "2026-11-09"
    publish(world, "CT.PRIVACY", "privacy", "본문")
    assert world.client.get(f"{MEMBER}/terms/PRIVACY_CONSENT").json()["effectiveOn"] is None


def test_알_수_없는_약관_유형은_400이다(world: World) -> None:
    assert world.client.get(f"{MEMBER}/terms/NOPE").status_code == 400


# --- 안내 글 -------------------------------------------------------------------


def test_센터_연혁은_본문_JSON을_문서로_풀어_준다(world: World) -> None:
    publish(
        world, "CT.HISTORY", "center-history", json.dumps(HISTORY, ensure_ascii=False), CONTS_TTL="센터 연혁"
    )
    body = world.client.get(f"{MEMBER}/contents/center-history").json()
    assert body["slug"] == "center-history" and body["title"] == "센터 연혁"
    assert body["subtitle"] == "걸어온 길" and body["sections"][0]["items"] == [
        {"label": "2020", "text": "개소"}
    ]


def test_수정일은_수정_시각이_있으면_그것을_한국_날짜로_주고_없으면_등록일을_준다(world: World) -> None:
    # 2025-01-05 20:00 UTC는 한국 날짜로 1월 6일이다
    publish(
        world,
        "CT.HISTORY",
        "center-history",
        json.dumps(HISTORY),
        REG_DT=datetime(2024, 3, 1, 3, 0),
        MDFCN_DT=datetime(2025, 1, 5, 20, 0),
    )
    assert world.client.get(f"{MEMBER}/contents/center-history").json()["updatedOn"] == "2025-01-06"
    world.db.execute(tables.TB_SITE_CONTS.update().values(MDFCN_DT=None))
    assert world.client.get(f"{MEMBER}/contents/center-history").json()["updatedOn"] == "2024-03-01"


@pytest.mark.parametrize("content_type", ["CT.INTRO", "CT.HISTORY"])
def test_저장_위치가_없는_안내_글은_같은_식별자가_있어도_404다(world: World, content_type: str) -> None:
    for slug in ("guide-apply", "guide-refund", "center-facility"):
        publish(world, content_type, slug, json.dumps(HISTORY))  # 어떤 유형으로 저장돼 있어도 내주지 않는다
        assert world.client.get(f"{MEMBER}/contents/{slug}").status_code == 404


def test_식별자가_다른_연혁이나_미게시_연혁은_내주지_않는다(world: World) -> None:
    publish(world, "CT.HISTORY", "other-history", json.dumps(HISTORY))
    assert world.client.get(f"{MEMBER}/contents/center-history").status_code == 404
    publish(world, "CT.HISTORY", "center-history", json.dumps(HISTORY), PSTG_YN="N")
    assert world.client.get(f"{MEMBER}/contents/center-history").status_code == 404


@pytest.mark.parametrize(
    "raw", ["이건 JSON이 아님", "[1, 2]", '{"sections": "문자열"}', '{"뜻밖의": 1, "sections": []}']
)
def test_본문이_문서_모양이_아니면_500이다(world: World, raw: str) -> None:
    publish(world, "CT.HISTORY", "center-history", raw)
    response = world.client.get(f"{MEMBER}/contents/center-history")
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"


def test_알_수_없는_안내_글_이름은_400이다(world: World) -> None:
    assert world.client.get(f"{MEMBER}/contents/unknown").status_code == 400


# --- 연락처 --------------------------------------------------------------------


def test_연락처는_운영묶음의_전화와_주소만_채우고_나머지는_비운다(world: World) -> None:
    world.factory.make(
        "TB_OPER_BNDL", TELNO="0000000000", ADDR="다른 센터"
    )  # 다른 묶음의 값이 섞이면 안 된다
    world.db.execute(
        tables.TB_OPER_BNDL.update()
        .where(tables.TB_OPER_BNDL.c.OPER_BNDL_SN == world.bundle)
        .values(TELNO="0319451234", ADDR="경기도 파주시 조리읍")
    )
    assert world.client.get(f"{MEMBER}/site/contact").json() == {
        "phone": "0319451234",
        "adminOfficePhone": None,
        "postalCode": None,
        "address": "경기도 파주시 조리읍",
        "floorInfo": None,
        "openHours": None,
        "parking": None,
    }


def test_전화와_주소가_없으면_모두_null이다(world: World) -> None:
    world.db.execute(
        tables.TB_OPER_BNDL.update()
        .where(tables.TB_OPER_BNDL.c.OPER_BNDL_SN == world.bundle)
        .values(TELNO=None, ADDR=None)
    )
    body = world.client.get(f"{MEMBER}/site/contact").json()
    assert all(value is None for value in body.values())


def test_연락처는_요청이_해석된_운영묶음의_값을_준다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL", TELNO="0319990000", ADDR="다른 센터")["OPER_BNDL_SN"]
    world.client.app.dependency_overrides[get_bundle_resolver] = lambda: FixedBundle(int(other))  # type: ignore[attr-defined]
    body = world.client.get(f"{MEMBER}/site/contact").json()
    assert body["phone"] == "0319990000" and body["address"] == "다른 센터"
