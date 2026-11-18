# 강좌 만족도 집계자료 등록·승인(권한, 검증, 버전, 멱등, 승인 상태, 통계 반영)을 실제 앱과 MariaDB로 확인하는 시험
import copy
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import open_course
from tests.world import World

pytestmark = pytest.mark.db

_n = itertools.count(1)
BASE = "/stats/satisfaction/sources"


def actor(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"sa{next(_n)}", *codes, **kw)
    use(w, who)
    return who


def questions() -> list[dict[str, Any]]:
    return [
        {
            "questionId": "q1",
            "name": "수강 동기",
            "type": "SINGLE",
            "respondents": 10,
            "criteria": "단일선택 유효 응답",
            "options": [
                {"optionId": "a", "name": "취미", "count": 7},
                {"optionId": "b", "name": "취업", "count": 3},
            ],
        },
        {
            "questionId": "q2",
            "name": "알게 된 경로",
            "type": "MULTI",
            "respondents": 10,
            "criteria": "복수선택, 합계가 100%를 넘을 수 있다",
            "options": [
                {"optionId": "a", "name": "지인", "count": 8},
                {"optionId": "b", "name": "누리집", "count": 6},
            ],
        },
        {
            "questionId": "q3",
            "name": "강의 만족도",
            "type": "SCORE",
            "respondents": 10,
            "minScore": "1",
            "maxScore": "5",
            "criteria": "무응답은 점수 없음으로 분모에서 뺀다",
            "options": [
                {"optionId": "5", "name": "매우 만족", "count": 5, "score": "5"},
                {"optionId": "3", "name": "보통", "count": 4, "score": "3"},
                {"optionId": "x", "name": "무응답", "count": 1, "score": None},
            ],
        },
    ]


def body(course: dict[str, Any], **values: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "courseId": str(course["CORS_SN"]),
        "provider": "센터 만족도 조사",
        "basisId": "조사-2026-03",
        "datasetId": "dgstfn-2026",
        "periodStart": "2026-09-01",
        "periodEnd": "2026-10-15",
        "respondents": 12,
        "criteria": "수강생 전수조사, 중복 응답 제외",
        "questions": questions(),
    }
    return {**base, **values}


def create(w: World, course: dict[str, Any], key: str | None = None, **values: Any) -> Any:
    return call(
        w, "POST", BASE, body(course, **values), **{"Idempotency-Key": key or f"sat-key-{next(_n):06d}"}
    )


def stored(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위나_시스템_배정이면_403이다(world: World) -> None:
    c = open_course(world)
    world.db.commit()
    assert world.client.get(f"/api/admin/v1{BASE}").status_code == 401
    actor(world, "AU.STAT_R")
    assert call(world, "GET", BASE).status_code == 403
    assert create(world, c).status_code == 403
    actor(world, "AU.CONF_W", kind="SK.DONG", dong_sn=dong(world, "가동")["DONG_SN"])
    assert call(world, "GET", BASE).status_code == 403 and create(world, c).status_code == 403
    actor(
        world, "AU.GRANT_W", kind="SK.SYSTEM"
    )  # 구조 권한은 시스템 배정에서도 묶음 전체지만 업무 자료는 아니다
    assert call(world, "GET", BASE).status_code == 403


def test_등록은_CONF_W만_승인과_반려는_GRANT_W만_한다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.GRANT_W")
    assert create(world, c).status_code == 403
    actor(world, "AU.CONF_W")
    made = create(world, c)
    assert made.status_code == 201, made.text
    sn = made.json()["sourceId"]
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 403
    assert call(world, "POST", f"{BASE}/{sn}/reject").status_code == 403
    actor(world, "AU.GRANT_W")
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 200


def test_CSRF_토큰이_없으면_403이다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W", "AU.GRANT_W")
    sn = create(world, c).json()["sourceId"]
    for path in (BASE, f"{BASE}/{sn}/approve", f"{BASE}/{sn}/reject"):
        res = world.client.post(
            f"/api/admin/v1{path}",
            json=body(c) if path == BASE else None,
            headers={"Idempotency-Key": "csrf-key-0001"},
        )
        assert res.status_code == 403, path


# --- 등록 ---------------------------------------------------------------------------------------


def test_등록하면_검토_전으로_저장하고_문항과_선택_집계를_그대로_보존한다(world: World) -> None:
    c = open_course(world, CORS_NM="요가")
    who = actor(world, "AU.CONF_W")
    res = create(world, c)
    assert res.status_code == 201, res.text
    out = res.json()
    assert (out["state"], out["version"], out["courseName"], out["respondents"]) == ("WAIT", 1, "요가", 12)
    assert (out["periodStart"], out["periodEnd"], out["decidedAt"], out["decidedBy"]) == (
        "2026-09-01",
        "2026-10-15",
        None,
        None,
    )
    assert [(q["questionId"], q["type"], q["respondents"]) for q in out["questions"]] == [
        ("q1", "SINGLE", 10),
        ("q2", "MULTI", 10),
        ("q3", "SCORE", 10),
    ]
    score = out["questions"][2]
    assert (float(score["minScore"]), float(score["maxScore"])) == (1.0, 5.0)
    assert [
        (o["name"], o["count"], None if o["score"] is None else float(o["score"])) for o in score["options"]
    ] == [
        ("매우 만족", 5, 5.0),
        ("보통", 4, 3.0),
        ("무응답", 1, None),  # 점수 없음은 0점이 아니라 비어 있다
    ]
    [src] = stored(world, "SELECT APRV_STTS_CD s, APRV_MNGR_SN m, REG_MNGR_SN r FROM TB_CORS_DGSTFN_SRC")
    assert (str(src["s"]).strip(), src["m"], int(src["r"])) == ("SA.DRAFT", None, int(who.row["MNGR_SN"]))
    [job] = stored(world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SATISFACTION_SRC_CREATE'")
    assert "버전 1" in job["c"] and "문항 3건" in job["c"] and "조사-2026-03" not in job["c"]


def test_같은_강좌·계열을_다시_등록하면_다음_버전이고_다른_강좌나_계열은_1부터다(world: World) -> None:
    c1, c2 = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="필라테스")
    actor(world, "AU.CONF_W")
    assert create(world, c1).json()["version"] == 1
    assert create(world, c1).json()["version"] == 2
    assert create(world, c1, datasetId="other").json()["version"] == 1
    assert create(world, c2).json()["version"] == 1


def mutated(change: Any) -> list[dict[str, Any]]:
    qs = copy.deepcopy(questions())
    change(qs)
    return qs


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("periodEnd", {"periodStart": "2026-05-01", "periodEnd": "2026-04-30"}),
        ("courseId", {"courseId": "999999"}),
        (
            "questions[1]",
            {"questions": mutated(lambda q: q[1].update(respondents=13))},
        ),  # 전체 응답자 수(12)보다 크다
        ("questions[1]", {"questions": mutated(lambda q: q.__setitem__(1, {**q[0]}))}),  # 문항 식별자 중복
        (
            "questions[0]",
            {
                "questions": mutated(
                    lambda q: q[0]["options"].__setitem__(1, {**q[0]["options"][0], "count": 3})
                )
            },
        ),
        (
            "questions[0]",
            {"questions": mutated(lambda q: q[0]["options"][0].update(count=6))},
        ),  # 단일선택 합계 9 != 10
        (
            "questions[1]",
            {"questions": mutated(lambda q: q[1]["options"][0].update(count=11))},
        ),  # 복수선택 항목이 응답자보다 많다
        ("questions[2]", {"questions": mutated(lambda q: q[2].update(minScore=None))}),
        ("questions[2]", {"questions": mutated(lambda q: q[2].update(minScore="6"))}),
        (
            "questions[2]",
            {"questions": mutated(lambda q: q[2]["options"][0].update(score="9"))},
        ),  # 척도 밖 점수
        ("questions[0]", {"questions": mutated(lambda q: q[0].update(minScore="1", maxScore="5"))}),
        (
            "questions[0]",
            {"questions": mutated(lambda q: q[0]["options"][0].update(score="3"))},
        ),  # 점수 문항이 아닌데 점수
    ],
)
def test_규칙을_어기면_422이고_저장하지_않는다(world: World, field: str, values: dict[str, Any]) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W")
    res = create(world, c, **values)
    assert res.status_code == 422 and field in res.json()["fields"], res.text
    assert stored(world, "SELECT COUNT(*) n FROM TB_CORS_DGSTFN_SRC")[0]["n"] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"questions": []},
        {"questions": mutated(lambda q: q[0].update(options=[]))},
        {"questions": mutated(lambda q: q[0]["options"][0].update(count=-1))},
        {"respondents": -1},
        {"provider": ""},
        {"extra": 1},
    ],
)
def test_형식이_틀린_입력은_400이다(world: World, values: dict[str, Any]) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W")
    assert create(world, c, **values).status_code == 400
    assert stored(world, "SELECT COUNT(*) n FROM TB_CORS_DGSTFN_SRC")[0]["n"] == 0


def test_같은_키로_다시_보내면_같은_자료이고_내용이_다르면_409이며_키가_없으면_400이다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W")
    first = create(world, c, key="same-key-0001")
    again = create(world, c, key="same-key-0001")
    assert again.status_code == 201 and again.json()["sourceId"] == first.json()["sourceId"]
    assert stored(world, "SELECT COUNT(*) n FROM TB_CORS_DGSTFN_SRC")[0]["n"] == 1
    other = create(world, c, key="same-key-0001", provider="다른 출처")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert create(world, c, key="same-key-0002").json()["version"] == 2
    assert call(world, "POST", BASE, body(c)).status_code == 400


def test_다른_담당자가_같은_키를_써도_따로_등록한다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W")
    first = create(world, c, key="shared-key-01")
    actor(world, "AU.CONF_W")
    second = create(world, c, key="shared-key-01")
    assert second.status_code == 201 and second.json()["sourceId"] != first.json()["sourceId"]


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_최근_순이고_없는_번호나_다른_묶음의_자료는_404다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W", "AU.GRANT_W")
    first = create(world, c).json()["sourceId"]
    second = create(world, c, datasetId="b").json()["sourceId"]
    call(world, "POST", f"{BASE}/{first}/approve")
    items = call(world, "GET", BASE).json()["items"]
    assert [(i["sourceId"], i["state"], i["courseName"]) for i in items] == [
        (second, "WAIT", "요가"),
        (first, "APPROVED", "요가"),
    ]
    assert call(world, "GET", f"{BASE}/999999").status_code == 404
    other = world.factory.make("TB_OPER_BNDL")
    foreign_course = world.factory.make("TB_CORS", OPER_BNDL_SN=other["OPER_BNDL_SN"])
    foreign = world.factory.make(
        "TB_CORS_DGSTFN_SRC",
        OPER_BNDL_SN=other["OPER_BNDL_SN"],
        CORS_SN=foreign_course["CORS_SN"],
        BGNG_YMD="20260901",
        END_YMD="20261015",
    )
    sn = foreign["CORS_DGSTFN_SRC_SN"]
    assert call(world, "GET", f"{BASE}/{sn}").status_code == 404
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 404
    assert [i["sourceId"] for i in call(world, "GET", BASE).json()["items"]] == [second, first]


# --- 승인·반려 ----------------------------------------------------------------------------------


def test_승인하면_승인자와_일시가_남고_다시_승인하거나_반려할_수_없다(world: World) -> None:
    c = open_course(world)
    who = actor(world, "AU.CONF_W", "AU.GRANT_W")
    sn = create(world, c).json()["sourceId"]
    res = call(world, "POST", f"{BASE}/{sn}/approve")
    assert res.status_code == 200 and res.json()["state"] == "APPROVED" and res.json()["decidedAt"]
    [src] = stored(
        world, "SELECT APRV_STTS_CD s, APRV_MNGR_SN m, APRV_DT d, RCRD_VER v FROM TB_CORS_DGSTFN_SRC"
    )
    assert (str(src["s"]).strip(), int(src["m"]), src["d"] is not None, int(src["v"])) == (
        "SA.APPROVED",
        int(who.row["MNGR_SN"]),
        True,
        2,
    )
    for action in ("approve", "reject"):
        again = call(world, "POST", f"{BASE}/{sn}/{action}")
        assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE", action
    assert (
        stored(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='SATISFACTION_SRC_DECIDE'")[0]["n"]
        == 1
    )


def test_반려한_자료는_통계에_나가지_않는다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W", "AU.GRANT_W", "AU.STAT_R")
    sn = create(world, c).json()["sourceId"]
    res = call(world, "POST", f"{BASE}/{sn}/reject")
    assert res.status_code == 200 and res.json()["state"] == "REJECTED"
    assert call(world, "GET", "/stats/satisfaction").json()["source"] is None
    assert call(world, "POST", f"{BASE}/{sn}/approve").status_code == 409


def test_승인한_자료가_만족도_통계의_최신_버전이_되고_대기_자료는_보이지_않는다(world: World) -> None:
    c = open_course(world)
    actor(world, "AU.CONF_W", "AU.GRANT_W", "AU.STAT_R")
    v1 = create(world, c).json()["sourceId"]
    assert call(world, "GET", "/stats/satisfaction").json()["source"] is None  # 검토 전은 없는 것이다
    call(world, "POST", f"{BASE}/{v1}/approve")
    got = call(world, "GET", "/stats/satisfaction").json()
    assert got["source"]["version"] == "1" and got["respondents"] == 12
    items = {i["question"]: i for i in got["items"]}
    assert [i["question"] for i in got["items"]] == ["수강 동기", "알게 된 경로", "강의 만족도"]
    assert items["강의 만족도"]["average"] == round((5 * 5 + 4 * 3) / 9, 2)  # 무응답 1명은 분모에서 뺀다
    assert items["수강 동기"]["average"] is None
    v2 = create(world, c, respondents=13).json()["sourceId"]
    assert (
        call(world, "GET", "/stats/satisfaction").json()["respondents"] == 12
    )  # 새 버전은 승인 전에는 쓰지 않는다
    call(world, "POST", f"{BASE}/{v2}/approve")
    assert (
        call(world, "GET", "/stats/satisfaction").json()["respondents"] == 13
    )  # 합산하지 않고 한 버전만 본다


def test_다른_센터의_강좌는_고를_수_없다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")
    foreign = world.factory.make("TB_CORS", OPER_BNDL_SN=other["OPER_BNDL_SN"])
    actor(world, "AU.CONF_W")
    res = create(world, foreign)
    assert res.status_code == 422 and "courseId" in res.json()["fields"]
    assert stored(world, "SELECT COUNT(*) n FROM TB_CORS_DGSTFN_SRC")[0]["n"] == 0
