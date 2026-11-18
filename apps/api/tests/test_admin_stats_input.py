# 연령·성별 집계자료 등록·승인(권한, 검증, 버전, 멱등, 승인 상태, 통계 반영)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.world import World

pytestmark = pytest.mark.db

_n = itertools.count(1)
BASE = "/stats/age-gender/sources"


def actor(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"si{next(_n)}", *codes, **kw)
    use(w, who)
    return who


def rows() -> list[dict[str, Any]]:
    def cell(band: str, lower: int | None, upper: int | None, gender: str, count: int) -> dict[str, Any]:
        return {
            "ageGroupId": f"a{lower}",
            "ageGroupName": band,
            "lowerAge": lower,
            "upperAge": upper,
            "genderId": gender,
            "genderName": {"M": "남", "F": "여", "U": "미상", "T": "합계"}[gender],
            "count": count,
        }

    return [
        cell("20~29세", 20, 29, "M", 10),
        cell("20~29세", 20, 29, "F", 0),
        cell("20~29세", 20, 29, "T", 10),
        cell("80세 이상", 80, None, "U", 3),
    ]


def body(**values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "provider": "파주시 주민등록 통계",
        "basisId": "문서-2026-001",
        "datasetId": "age-gender-2026",
        "periodStart": "2026-01-01",
        "periodEnd": "2026-10-31",
        "ageBasisDate": "2026-10-31",
        "dedupeNote": "만 나이, 중복 거주 제외",
        "rows": rows(),
    }
    return {**base, **values}


def create(w: World, key: str | None = None, **values: Any) -> Any:
    return call(w, "POST", BASE, body(**values), **{"Idempotency-Key": key or f"src-key-{next(_n):06d}"})


def stored(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위뿐이면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get(f"/api/admin/v1{BASE}").status_code == 401
    actor(world, "AU.STAT_R")  # 조회 통계 권한만으로는 자료를 보거나 올릴 수 없다
    assert call(world, "GET", BASE).status_code == 403
    assert create(world).status_code == 403
    actor(world, "AU.CONF_W", kind="SK.DONG", dong_sn=dong(world, "가동")["DONG_SN"])
    assert call(world, "GET", BASE).status_code == 403  # 묶음 공통 자료라 묶음 전체 범위만 다룬다
    assert create(world).status_code == 403


def test_등록은_CONF_W만_승인과_반려는_GRANT_W만_한다(world: World) -> None:
    actor(world, "AU.GRANT_W")
    assert create(world).status_code == 403  # 승인 담당이 등록까지 하지는 못한다
    actor(world, "AU.CONF_W")
    made = create(world)
    assert made.status_code == 201, made.text
    sn = made.json()["sourceId"]
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 403
    assert call(world, "POST", f"{BASE}/{sn}/reject").status_code == 403
    actor(world, "AU.GRANT_W")
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 200


def test_같은_사람이_등록과_승인을_모두_할_수_있다(world: World) -> None:
    actor(world, "AU.CONF_W", "AU.GRANT_W")
    sn = create(world).json()["sourceId"]
    res = call(world, "POST", f"{BASE}/{sn}/approve")
    assert res.status_code == 200 and res.json()["state"] == "APPROVED"


def test_CSRF_토큰이_없으면_등록도_승인도_403이다(world: World) -> None:
    actor(world, "AU.CONF_W", "AU.GRANT_W")
    sn = create(world).json()["sourceId"]
    for path in (BASE, f"{BASE}/{sn}/approve", f"{BASE}/{sn}/reject"):
        res = world.client.post(
            f"/api/admin/v1{path}",
            json=body() if path == BASE else None,
            headers={"Idempotency-Key": "csrf-key-0001"},
        )
        assert res.status_code == 403, path


# --- 등록 ---------------------------------------------------------------------------------------


def test_등록하면_검토대기로_저장하고_집계값과_작업이력이_남는다(world: World) -> None:
    who = actor(world, "AU.CONF_W")
    res = create(world)
    assert res.status_code == 201, res.text
    out = res.json()
    assert (out["state"], out["version"], out["decidedAt"], out["decidedBy"]) == ("WAIT", 1, None, None)
    assert (out["periodStart"], out["periodEnd"], out["ageBasisDate"]) == (
        "2026-01-01",
        "2026-10-31",
        "2026-10-31",
    )
    assert [(r["ageGroupName"], r["genderName"], r["count"]) for r in out["rows"]] == [
        ("20~29세", "남", 10),
        ("20~29세", "여", 0),
        ("20~29세", "합계", 10),
        ("80세 이상", "미상", 3),
    ]  # 입력 순서와 합계 분류, 실제 0명을 그대로 보존한다
    assert out["rows"][3]["upperAge"] is None
    [src] = stored(world, "SELECT APRV_STTS_CD s, APRV_MNGR_SN m, BGNG_YMD b FROM TB_MBR_STATS_SRC")
    assert (str(src["s"]).strip(), src["m"], src["b"]) == ("SA.WAIT", None, "20260101")
    [job] = stored(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='STATS_SRC_CREATE'")
    assert int(job["m"]) == int(who.row["MNGR_SN"]) and "버전 1" in job["c"] and "행 4건" in job["c"]
    assert "문서-2026-001" not in job["c"] and "만 나이" not in job["c"]  # 입력 내용은 이력에 싣지 않는다


def test_같은_계열을_다시_등록하면_다음_버전이고_다른_계열은_1부터다(world: World) -> None:
    actor(world, "AU.CONF_W")
    assert create(world).json()["version"] == 1
    assert create(world).json()["version"] == 2
    assert create(world, datasetId="other").json()["version"] == 1


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("periodEnd", {"periodStart": "2026-05-01", "periodEnd": "2026-04-30"}),
        ("rows[1]", {"rows": rows()[:1] + [{**rows()[0]}]}),  # 같은 구간·성별 조합이 겹친다
        ("rows[0]", {"rows": [{**rows()[0], "lowerAge": 30, "upperAge": 20}]}),
    ],
)
def test_기간이_거꾸로이거나_조합이_겹치거나_하한이_상한보다_크면_422이고_저장하지_않는다(
    world: World, field: str, values: dict[str, Any]
) -> None:
    actor(world, "AU.CONF_W")
    res = create(world, **values)
    assert res.status_code == 422 and field in res.json()["fields"], res.text
    assert stored(world, "SELECT COUNT(*) n FROM TB_MBR_STATS_SRC")[0]["n"] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"rows": []},
        {"rows": [{**rows()[0], "count": -1}]},
        {"provider": ""},
        {"periodStart": "2026-13-01"},
        {"extra": 1},  # 정의되지 않은 필드는 거절한다
    ],
)
def test_형식이_틀린_입력은_400이다(world: World, values: dict[str, Any]) -> None:
    actor(world, "AU.CONF_W")
    assert create(world, **values).status_code == 400
    assert stored(world, "SELECT COUNT(*) n FROM TB_MBR_STATS_SRC")[0]["n"] == 0


def test_같은_키로_다시_보내면_같은_자료이고_내용이_다르면_409다(world: World) -> None:
    actor(world, "AU.CONF_W")
    first = create(world, key="same-key-0001")
    again = create(world, key="same-key-0001")
    assert again.status_code == 201 and again.json()["sourceId"] == first.json()["sourceId"]
    assert stored(world, "SELECT COUNT(*) n FROM TB_MBR_STATS_SRC")[0]["n"] == 1
    other = create(world, key="same-key-0001", provider="다른 출처")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert create(world, key="same-key-0002").json()["version"] == 2  # 다른 키는 새 버전이다


def test_Idempotency_Key가_없으면_400이다(world: World) -> None:
    actor(world, "AU.CONF_W")
    assert call(world, "POST", BASE, body()).status_code == 400


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_최근_등록_순이고_상세는_없는_번호나_다른_묶음이면_404다(world: World) -> None:
    actor(world, "AU.CONF_W", "AU.GRANT_W")
    first = create(world).json()["sourceId"]
    second = create(world, datasetId="b").json()["sourceId"]
    assert call(world, "POST", f"{BASE}/{first}/approve").status_code == 200
    items = call(world, "GET", BASE).json()["items"]
    assert [(i["sourceId"], i["state"]) for i in items] == [(second, "WAIT"), (first, "APPROVED")]
    assert items[1]["decidedBy"] is not None
    assert call(world, "GET", f"{BASE}/{first}").json()["rows"][0]["count"] == 10
    assert call(world, "GET", f"{BASE}/999999").status_code == 404
    other = world.factory.make("TB_OPER_BNDL")
    foreign = world.factory.make(
        "TB_MBR_STATS_SRC",
        OPER_BNDL_SN=other["OPER_BNDL_SN"],
        BGNG_YMD="20260101",
        END_YMD="20261031",
        CRTR_YMD="20261031",
    )
    assert call(world, "GET", f"{BASE}/{foreign['MBR_STATS_SRC_SN']}").status_code == 404
    assert call(world, "POST", f"{BASE}/{foreign['MBR_STATS_SRC_SN']}/approve").status_code == 404
    assert [i["sourceId"] for i in call(world, "GET", BASE).json()["items"]] == [second, first]


# --- 승인·반려 ----------------------------------------------------------------------------------


def test_승인하면_승인자와_일시가_남고_다시_승인하거나_반려할_수_없다(world: World) -> None:
    who = actor(world, "AU.CONF_W", "AU.GRANT_W")
    sn = create(world).json()["sourceId"]
    res = call(world, "POST", f"{BASE}/{sn}/approve")
    assert res.status_code == 200 and res.json()["state"] == "APPROVED" and res.json()["decidedAt"]
    [src] = stored(
        world, "SELECT APRV_STTS_CD s, APRV_MNGR_SN m, APRV_DT d, RCRD_VER v FROM TB_MBR_STATS_SRC"
    )
    assert (str(src["s"]).strip(), int(src["m"]), src["d"] is not None, int(src["v"])) == (
        "SA.APPROVE",
        int(who.row["MNGR_SN"]),
        True,
        2,
    )
    for action in ("approve", "reject"):
        again = call(world, "POST", f"{BASE}/{sn}/{action}")
        assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE", action
    assert stored(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='STATS_SRC_DECIDE'")[0]["n"] == 1


def test_반려하면_통계에_나가지_않고_다시_결정할_수_없다(world: World) -> None:
    actor(world, "AU.CONF_W", "AU.GRANT_W", "AU.STAT_R")
    sn = create(world).json()["sourceId"]
    res = call(world, "POST", f"{BASE}/{sn}/reject")
    assert res.status_code == 200 and res.json()["state"] == "REJECTED"
    assert call(world, "GET", "/stats/age-gender").json()["source"] is None
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 409
    [job] = stored(world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='STATS_SRC_DECIDE'")
    assert job["c"] == "반려"


def test_승인한_자료가_통계_조회의_최신_버전이_되고_대기_자료는_보이지_않는다(world: World) -> None:
    actor(world, "AU.CONF_W", "AU.GRANT_W", "AU.STAT_R")
    v1 = create(world).json()["sourceId"]
    assert call(world, "GET", "/stats/age-gender").json()["source"] is None  # 검토대기는 없는 것이다
    call(world, "POST", f"{BASE}/{v1}/approve")
    got = call(world, "GET", "/stats/age-gender").json()
    assert got["source"]["version"] == "1"
    assert [(r["band"], r["male"], r["female"], r["unknown"]) for r in got["rows"]] == [
        ("20~29세", 10, 0, 0),  # 합계 분류는 열에 넣지 않는다
        ("80세 이상", 0, 0, 3),
    ]
    v2 = create(world, rows=[{**rows()[0], "count": 99}]).json()["sourceId"]
    assert (
        call(world, "GET", "/stats/age-gender").json()["rows"][0]["male"] == 10
    )  # 새 버전은 승인 전까지 쓰지 않는다
    call(world, "POST", f"{BASE}/{v2}/approve")
    latest = call(world, "GET", "/stats/age-gender").json()
    assert (
        latest["source"]["version"] == "2" and latest["rows"][0]["male"] == 99
    )  # 합산하지 않고 한 버전만 본다


def test_다른_담당자가_같은_키를_써도_따로_등록한다(world: World) -> None:
    actor(world, "AU.CONF_W")
    first = create(world, key="shared-key-01")
    actor(world, "AU.CONF_W")
    second = create(world, key="shared-key-01")
    assert second.status_code == 201 and second.json()["sourceId"] != first.json()["sourceId"]
