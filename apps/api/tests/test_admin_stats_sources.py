# 연령·성별과 만족도 통계(승인된 최신 집계자료만, 버전 합산 금지, 자료 없음과 0 구분)와 연령·성별 CSV를 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import open_course
from tests.world import START, World, make_admin

pytestmark = pytest.mark.db

_n = itertools.count(1)


def viewer(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"ss{next(_n)}", "AU.STAT_R", *codes, **kw)
    use(w, who)
    return who


def age_source(
    w: World,
    version: int = 1,
    status: str = "SA.APPROVE",
    approved: bool = True,
    days: int = 0,
    **values: Any,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if approved:
        extra.update(
            APRV_MNGR_SN=make_admin(w, f"ap{next(_n)}")["MNGR_SN"], APRV_DT=START - timedelta(days=days)
        )
    defaults: dict[str, Any] = {
        "SRC_NM": "파주시 주민등록 통계",
        "SRC_BSS_ID": f"basis-{next(_n)}",
        "DATST_ID": f"age-{next(_n)}",
        "SRC_VER": version,
        "BGNG_YMD": "20260101",
        "END_YMD": "20261031",
        "CRTR_YMD": "20261031",
        "TOT_CRTR_CN": "만 나이",
        "APRV_STTS_CD": status,
    }
    return w.factory.make("TB_MBR_STATS_SRC", **{**defaults, **extra, **values})


def band(
    w: World, src: dict[str, Any], name: str, gender: str, count: int, seq: int = 1, **values: Any
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "MBR_STATS_SRC_SN": src["MBR_STATS_SRC_SN"],
        "AGE_GROUP_ID": f"g{next(_n)}",
        "AGE_GROUP_NM": name,
        "GNDR_CLSF_ID": f"s{next(_n)}",
        "GNDR_CLSF_NM": gender,
        "TOT_NOPE": count,
        "SORT_SEQ": seq,
    }
    return w.factory.make("TB_MBR_STATS_TOT", **{**defaults, **values})


# --- 연령·성별 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_통계_권한이_없으면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/stats/age-gender").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R"))
    for path in ("/stats/age-gender", "/stats/satisfaction", "/stats/age-gender/export.csv"):
        assert call(world, "GET", path).status_code == 403, path


def test_승인된_자료가_없으면_미제공이고_0명으로_대신하지_않는다(world: World) -> None:
    viewer(world)
    out = call(world, "GET", "/stats/age-gender").json()
    assert out["source"] is None and out["rows"] == [] and out["basis"]["basisAt"]
    sat = call(world, "GET", "/stats/satisfaction").json()
    assert sat["source"] is None and sat["respondents"] is None and sat["items"] == []
    waiting = age_source(world, 1, "SA.WAIT", approved=False)
    band(world, waiting, "20대", "남", 5)
    rejected = age_source(world, 2, "SA.REJECT")
    band(world, rejected, "20대", "남", 7)
    assert call(world, "GET", "/stats/age-gender").json()["source"] is None  # 대기·반려 자료는 보이지 않는다
    assert call(world, "GET", "/stats/age-gender/export.csv").status_code == 422  # 내려받을 자료가 없다


def test_승인된_최신_버전만_구간과_성별을_그대로_보인다(world: World) -> None:
    old = age_source(world, 1, days=30)
    new = age_source(world, 2, days=1)
    band(world, old, "20대", "남", 100, 1)
    for gender, count, seq in (("남", 10, 1), ("여", 12, 2)):
        band(world, new, "20대 미만", gender, count, seq)
    for gender, count, seq in (("남", 30, 3), ("여", 25, 4), ("미상", 2, 5)):
        band(world, new, "20~39세", gender, count, seq)
    viewer(world)
    out = call(world, "GET", "/stats/age-gender").json()
    assert out["source"] == {
        "version": "2",
        "provider": "파주시 주민등록 통계",
        "period": "2026-01-01~2026-10-31",
        "basisDate": "2026-10-31",
    }
    assert out["rows"] == [
        {"band": "20대 미만", "male": 10, "female": 12, "unknown": 0},
        {"band": "20~39세", "male": 30, "female": 25, "unknown": 2},
    ]  # 이전 버전과 합치지 않는다
    assert (out["basis"]["fromDate"], out["basis"]["toDate"], out["basis"]["cycleId"]) == (
        "2026-01-01",
        "2026-10-31",
        None,
    )


def test_합계_분류는_열에_넣지_않고_0명은_0으로_보인다(world: World) -> None:
    src = age_source(world)
    band(world, src, "전체", "합계", 999, 1)
    band(world, src, "40대", "남", 0, 2)
    band(world, src, "40대", "여", 4, 3)
    band(world, src, "40대", "합계", 4, 4)
    band(world, src, "40대", "기타", 1, 5)
    viewer(world)
    rows = call(world, "GET", "/stats/age-gender").json()["rows"]
    assert rows == [
        {"band": "40대", "male": 0, "female": 4, "unknown": 1}
    ]  # 합계 분류는 합산하지 않고 0명은 그대로 0이다


def test_승인자와_승인일시가_없는_자료는_보이지_않는다(world: World) -> None:
    src = age_source(world, approved=False)
    band(world, src, "20대", "남", 3)
    viewer(world)
    assert call(world, "GET", "/stats/age-gender").json()["source"] is None


def test_승인자와_승인일시_중_하나만_있는_연령_자료도_보이지_않는다(world: World) -> None:
    only_who = age_source(world, 1, approved=False, APRV_MNGR_SN=make_admin(world, "aw")["MNGR_SN"])
    only_when = age_source(world, 2, approved=False, APRV_DT=START)
    for s in (only_who, only_when):
        band(world, s, "20대", "남", 3)
    viewer(world)
    assert call(world, "GET", "/stats/age-gender").json()["source"] is None


def test_동이_정해진_자료는_그_동을_다루는_담당자만_본다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = age_source(world, 11, days=5, DONG_SN=a["DONG_SN"])
    other = age_source(world, 12, days=1, DONG_SN=b["DONG_SN"])
    common = age_source(world, 13, days=10)
    for s in (mine, other, common):
        band(world, s, "20대", "남", 1)
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert call(world, "GET", "/stats/age-gender").json()["source"]["version"] == "11"
    viewer(world)
    assert (
        call(world, "GET", "/stats/age-gender").json()["source"]["version"] == "12"
    )  # 가장 나중에 승인한 자료


def test_연령_성별_CSV는_첫_줄에_자료_버전과_기준일을_넣고_작업이력을_남긴다(world: World) -> None:
    src = age_source(world, 7)
    band(world, src, "=SUM(1)", "남", 4, 1)
    band(world, src, "=SUM(1)", "여", 5, 2)
    me = viewer(world)
    res = call(world, "GET", "/stats/age-gender/export.csv")
    assert (
        res.status_code == 200
        and res.headers["content-type"].startswith("text/csv")
        and "no-store" in res.headers["cache-control"]
    )
    table = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert (
        table[0][0].startswith("# 자료 버전 7, 출처 파주시 주민등록 통계, 집계 기간 2026-01-01~2026-10-31")
        and "연령 기준일 2026-10-31" in table[0][0]
    )
    assert table[1] == ["연령구간", "남", "여", "미상"] and table[2] == ["'=SUM(1)", "4", "5", "0"]
    [job] = list(
        world.db.execute(
            text("SELECT MNGR_SN m, TRGT_TBL_NM t FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT'")
        ).mappings()
    )
    assert (job["m"], job["t"]) == (me.sn, "STATS_AGE_GENDER")


# --- 만족도 -------------------------------------------------------------------------------------


def survey(
    w: World,
    c: dict[str, Any],
    version: int = 1,
    status: str = "SA.APPROVED",
    approved: bool = True,
    days: int = 0,
    **values: Any,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if approved:
        extra.update(
            APRV_MNGR_SN=make_admin(w, f"sv{next(_n)}")["MNGR_SN"], APRV_DT=START - timedelta(days=days)
        )
    defaults: dict[str, Any] = {
        "CORS_SN": c["CORS_SN"],
        "DATST_ID": f"sat-{next(_n)}",
        "SRC_VER": version,
        "SRC_NM": "기관 만족도 조사",
        "SRC_BSS_ID": f"b-{next(_n)}",
        "BGNG_YMD": "20260901",
        "END_YMD": "20261015",
        "RSPNS_NOPE": 40,
        "TOT_CRTR_CN": "유효 응답 기준",
        "APRV_STTS_CD": status,
        "REG_MNGR_SN": make_admin(w, f"rg{next(_n)}")["MNGR_SN"],
    }
    return w.factory.make("TB_CORS_DGSTFN_SRC", **{**defaults, **extra, **values})


def question(
    w: World, src: dict[str, Any], name: str, kind: str, answered: int, seq: int = 1
) -> dict[str, Any]:
    return w.factory.make(
        "TB_CORS_DGSTFN_QITEM",
        CORS_DGSTFN_SRC_SN=src["CORS_DGSTFN_SRC_SN"],
        QITEM_ID=f"q{next(_n)}",
        QITEM_NM=name,
        RSPNS_TYPE_CD=kind,
        RSPNS_NOPE=answered,
        SORT_SEQ=seq,
        **({"LLMT_SCR": 1, "UPLMT_SCR": 5} if kind == "DQ.SCORE" else {}),
    )


def choice(
    w: World, q: dict[str, Any], label: str, count: int, score: int | None = None, seq: int = 1
) -> dict[str, Any]:
    return w.factory.make(
        "TB_CORS_DGSTFN_TOT",
        CORS_DGSTFN_QITEM_SN=q["CORS_DGSTFN_QITEM_SN"],
        ARTCL_ID=f"a{next(_n)}",
        ARTCL_NM=label,
        RSPNS_NOPE=count,
        SORT_SEQ=seq,
        **({} if score is None else {"SCR": score}),
    )


def test_만족도는_승인된_최신_자료의_문항별_응답과_평균을_준다(world: World) -> None:
    c = open_course(world)
    old = survey(world, c, 1, days=20)
    question(world, old, "옛 문항", "DQ.SINGLE", 1)
    new = survey(world, c, 2, days=1, RSPNS_NOPE=40)
    score = question(world, new, "강의 만족도", "DQ.SCORE", 36, 1)
    for label, count, scr, seq in (("매우 불만족", 2, 1, 1), ("보통", 10, 3, 2), ("매우 만족", 24, 5, 3)):
        choice(world, score, label, count, scr, seq)
    single = question(world, new, "수강 동기", "DQ.SINGLE", 30, 2)
    choice(world, score, "무응답", 4, None, 4)  # 점수가 없는 응답은 평균의 분모에 넣지 않는다
    choice(world, single, "취미", 20, 1, 1)
    choice(world, single, "취업", 10, 2, 2)  # 점수가 붙어 있어도 점수 문항이 아니면 평균을 내지 않는다
    empty_score = question(world, new, "시설 만족도", "DQ.SCORE", 0, 3)
    choice(world, empty_score, "점수 없음", 0, None, 1)
    viewer(world)
    out = call(world, "GET", "/stats/satisfaction").json()
    assert out["source"] == {
        "version": "2",
        "provider": "기관 만족도 조사",
        "period": "2026-09-01~2026-10-15",
        "basisDate": None,
    }
    assert out["respondents"] == 40
    items = {i["question"]: i for i in out["items"]}
    assert [i["question"] for i in out["items"]] == ["강의 만족도", "수강 동기", "시설 만족도"]
    assert (items["강의 만족도"]["answered"], items["강의 만족도"]["average"]) == (
        36,
        round((2 * 1 + 10 * 3 + 24 * 5) / 36, 2),
    )
    assert [(o["label"], o["count"]) for o in items["강의 만족도"]["options"]] == [
        ("매우 불만족", 2),
        ("보통", 10),
        ("매우 만족", 24),
        ("무응답", 4),
    ]
    assert (items["수강 동기"]["average"], [o["label"] for o in items["수강 동기"]["options"]]) == (
        None,
        ["취미", "취업"],
    )  # 점수 문항이 아니면 평균은 없다
    assert items["시설 만족도"]["average"] is None  # 분모가 0이면 산출하지 않고 0점으로 바꾸지 않는다
    assert "옛 문항" not in str(out)


def test_승인자와_승인일시_중_하나만_있는_만족도_자료도_보이지_않는다(world: World) -> None:
    c = open_course(world)
    survey(world, c, 31, approved=False, APRV_MNGR_SN=make_admin(world, "sw")["MNGR_SN"])
    survey(world, c, 32, approved=False, APRV_DT=START)
    viewer(world)
    assert call(world, "GET", "/stats/satisfaction").json()["source"] is None


def test_승인되지_않았거나_승인_기록이_없는_만족도_자료는_보이지_않는다(world: World) -> None:
    c = open_course(world)
    for version, status, approved in (
        (21, "SA.DRAFT", False),
        (22, "SA.REJECTED", True),
        (23, "SA.APPROVED", False),
    ):
        src = survey(world, c, version, status, approved)
        question(world, src, f"문항 {version}", "DQ.SINGLE", 1)
    viewer(world)
    assert call(world, "GET", "/stats/satisfaction").json()["source"] is None


def test_만족도는_강좌_동_범위의_자료만_본다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = open_course(world, CORS_NM="가동 강좌", DONG_SN=a["DONG_SN"])
    other = open_course(world, CORS_NM="나동 강좌", DONG_SN=b["DONG_SN"])
    survey(world, mine, 11, days=5)
    survey(world, other, 12, days=1)
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert call(world, "GET", "/stats/satisfaction").json()["source"]["version"] == "11"
    viewer(world)
    assert call(world, "GET", "/stats/satisfaction").json()["source"]["version"] == "12"


def test_만족도는_내보내기가_없다(world: World) -> None:
    viewer(world)
    for path in ("/stats/satisfaction/export.csv", "/stats/satisfaction/export.xlsx"):
        assert call(world, "GET", path).status_code in (404, 405), path
