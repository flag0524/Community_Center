# 관리자 홈·센터 콘텐츠(AU.SITE_W, 저장 가능한 유형·본문 정리·연혁 JSON·링크·게시 기간·버전·멱등·동 범위)를 실제 앱과 MariaDB로 확인하는 시험
import json
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_site_public import publish
from tests.world import MEMBER, START, World

pytestmark = pytest.mark.db

HISTORY = json.dumps(
    {
        "subtitle": "센터의 걸음",
        "sections": [{"heading": "2020", "paragraphs": ["개관"], "steps": [], "items": [], "links": []}],
    },
    ensure_ascii=False,
)


def body(kind: str = "BANNER", **values: Any) -> dict[str, Any]:
    return {
        "contentType": kind,
        "title": "배너",
        "body": "<p>본문</p>",
        "posted": True,
        "sortSeq": 1,
        **values,
    }


def make(w: World, payload: dict[str, Any] | None = None, key: str = "key-00000001") -> Any:
    return call(w, "POST", "/contents", payload or body(), **{"Idempotency-Key": key})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/contents").status_code == 401
    use(world, staff(world, "x", "AU.POST_W"))
    for method, path, payload in (
        ("GET", "/contents", None),
        ("POST", "/contents", body()),
        ("GET", "/contents/1", None),
        ("PUT", "/contents/1", {**body(), "version": 1}),
    ):
        assert call(world, method, path, payload, **{"Idempotency-Key": "key-00000001"}).status_code == 403, (
            path
        )


# --- 등록 ---------------------------------------------------------------------------------------


def test_배너를_등록하면_본문을_정리해_저장하고_공통_콘텐츠로_남긴다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    r = make(
        world,
        body(
            title="  가을 배너  ",
            body='<p onclick="x()">안내</p><script>x</script>',
            url="/courses",
            periodStart="2026-12-01T00:00:00+09:00",
            periodEnd="2026-12-31T00:00:00+09:00",
            posted=False,
            sortSeq=3,
        ),
    )
    assert r.status_code == 201
    out = r.json()
    assert (out["title"], out["body"], out["url"], out["posted"], out["sortSeq"], out["version"]) == (
        "가을 배너",
        "<p>안내</p>",
        "/courses",
        False,
        3,
        1,
    )
    assert (
        out["contentType"] == "BANNER"
        and out["contact"] is None
        and out["periodStart"].startswith("2026-11-30T15:00:00")
    )
    [row] = rows(world, "SELECT * FROM TB_SITE_CONTS")
    assert (
        row["CONTS_TYPE_CD"],
        row["DONG_SN"],
        row["VER_NM"],
        row["PSTG_YN"],
        row["ESNTL_YN"],
        row["CONTS_HASH_VL"],
        row["RVW_STTS_CD"],
    ) == (
        "CT.BANNER",
        None,
        "v1",
        "N",
        "N",
        None,
        None,
    )
    assert row["CONTS_ID"].startswith("banner-")
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CONTENT_CREATE'"
    )
    assert (
        (job["m"], job["t"]) == (boss.sn, "TB_SITE_CONTS")
        and job["c"].startswith("BANNER [idem ")
        and "가을" not in job["c"]
    )


@pytest.mark.parametrize("kind", ["VISUAL", "CONTACT", "GUIDE", "FACILITY"])
def test_스키마에_코드가_없는_유형은_저장하지_않고_이유를_알린다(world: World, kind: str) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    r = make(world, body(kind))
    assert r.status_code == 422 and "contentType" in r.json()["fields"] and "개정 요청" in r.json()["message"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_SITE_CONTS")[0]["n"] == 0


def test_연락처_구조_입력은_저장하지_않는다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    r = make(world, body("BANNER", contact={"phone": "031-000-0000"}))
    assert r.status_code == 422 and "contact" in r.json()["fields"]


def test_제목_링크_게시기간을_검사한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    assert "title" in make(world, body(title="   "), "key-00000001").json()["fields"]
    for n, link in enumerate(["http://example.com", "//evil.example", "javascript:alert(1)", "courses"]):
        r = make(world, body(url=link), f"key-0000001{n}")
        assert r.status_code == 422 and "url" in r.json()["fields"], link
    for n, link in enumerate(["/courses", "https://example.com/a"]):
        assert make(world, body(url=link), f"key-0000002{n}").status_code == 201, link
    bad = make(
        world,
        body(periodStart="2026-12-31T00:00:00+09:00", periodEnd="2026-12-01T00:00:00+09:00"),
        "key-00000030",
    )
    assert bad.status_code == 422 and "periodEnd" in bad.json()["fields"]
    same = make(
        world,
        body(periodStart="2026-12-01T00:00:00+09:00", periodEnd="2026-12-01T00:00:00+09:00"),
        "key-00000031",
    )
    assert same.status_code == 422


def test_같은_키로_다시_보내면_같은_콘텐츠이고_내용이_다르면_409다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    first = make(world).json()
    again = make(world)
    assert again.status_code == 201 and again.json()["contentId"] == first["contentId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_SITE_CONTS")[0]["n"] == 1
    diff = make(world, body(title="다른 제목"))
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/contents", body()).status_code in (400, 422)  # 멱등키 없음


# --- 연혁 ---------------------------------------------------------------------------------------


def test_연혁은_공개_화면이_읽는_JSON이어야_하고_하나만_둘_수_있다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    for n, text_ in enumerate(["그냥 글", "[1,2]", '{"sections": "x"}', '{"sections": [{"heading": 1}]}']):
        r = make(world, body("HISTORY", title="연혁", body=text_), f"key-0000001{n}")
        assert r.status_code == 422 and "body" in r.json()["fields"], text_
    ok = make(world, body("HISTORY", title="센터 연혁", body=HISTORY), "key-00000020")
    assert ok.status_code == 201 and ok.json()["body"] == HISTORY  # 정리하지 않고 그대로 저장한다
    assert rows(world, "SELECT CONTS_ID i FROM TB_SITE_CONTS")[0]["i"] == "center-history"
    again = make(world, body("HISTORY", title="또 연혁", body=HISTORY), "key-00000021")
    assert again.status_code == 422 and "하나만" in again.json()["message"]


def test_고친_연혁이_공개_화면에_바로_나온다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    made = make(world, body("HISTORY", title="센터 연혁", body=HISTORY)).json()
    pub = world.client.get(f"{MEMBER}/contents/center-history")
    assert (
        pub.status_code == 200
        and pub.json()["title"] == "센터 연혁"
        and pub.json()["subtitle"] == "센터의 걸음"
    )
    new = json.dumps({"subtitle": "고침", "sections": []}, ensure_ascii=False)
    r = call(
        world,
        "PUT",
        f"/contents/{made['contentId']}",
        {**body("HISTORY", title="새 연혁", body=new), "version": 1},
    )
    assert r.status_code == 200
    assert world.client.get(f"{MEMBER}/contents/center-history").json()["subtitle"] == "고침"
    call(
        world,
        "PUT",
        f"/contents/{made['contentId']}",
        {**body("HISTORY", title="새 연혁", body=new, posted=False), "version": 2},
    )
    assert world.client.get(f"{MEMBER}/contents/center-history").status_code == 404  # 게시를 끄면 사라진다


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_저장_가능한_유형만_유형_정렬_순서로_주고_유형으로_거른다(world: World) -> None:
    publish(world, "CT.POPUP", "popup-1", "팝업", SORT_SEQ=2)
    publish(world, "CT.BANNER", "banner-1", "배너2", SORT_SEQ=2)
    publish(world, "CT.BANNER", "banner-0", "배너1", SORT_SEQ=1)
    publish(world, "CT.TERMS", "terms", "약관")  # 약관은 콘텐츠 목록에 없다
    use(world, staff(world, "boss", "AU.SITE_W"))
    body_ = call(world, "GET", "/contents").json()
    assert [(i["contentType"], i["sortSeq"]) for i in body_["items"]] == [
        ("BANNER", 1),
        ("BANNER", 2),
        ("POPUP", 2),
    ]
    assert body_["total"] == 3 and body_["canCreate"] is True
    assert [i["contentType"] for i in call(world, "GET", "/contents?type=POPUP").json()["items"]] == ["POPUP"]
    assert call(world, "GET", "/contents?type=CONTACT").json()["items"] == []
    assert call(world, "GET", "/contents?type=NOPE").status_code in (400, 422)
    assert [len(call(world, "GET", f"/contents?size=2&page={n}").json()["items"]) for n in (1, 2)] == [2, 1]


def test_상세는_본문과_버전과_수정일을_주고_약관과_없는_글은_404다(world: World) -> None:
    row = publish(world, "CT.BANNER", "banner-1", "<p>본문</p>", URL_ADDR="/a", MDFCN_DT=START)
    term = publish(world, "CT.TERMS", "terms", "약관")
    use(world, staff(world, "boss", "AU.SITE_W"))
    out = call(world, "GET", f"/contents/{row['SITE_CONTS_SN']}").json()
    assert (out["body"], out["url"], out["version"], out["updatedOn"], out["contact"]) == (
        "<p>본문</p>",
        "/a",
        1,
        "2026-11-09",
        None,
    )
    assert call(world, "GET", f"/contents/{term['SITE_CONTS_SN']}").status_code == 404
    assert call(world, "GET", "/contents/999999999").status_code == 404
    assert call(world, "GET", "/contents/abc").status_code in (400, 422)


# --- 수정 ---------------------------------------------------------------------------------------


def test_수정하면_버전이_오르고_본문을_다시_정리하며_작업이력에_남는다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    made = make(world).json()
    r = call(
        world,
        "PUT",
        f"/contents/{made['contentId']}",
        {**body(title="고침", body="<b>굵게</b><script>x</script>", posted=False), "version": 1},
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["title"], out["body"], out["posted"], out["version"]) == ("고침", "<b>굵게</b>", False, 2)
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CONTENT_UPDATE'")
    assert (job["m"], job["c"]) == (boss.sn, "BANNER 게시 N")
    assert rows(world, "SELECT MDFCN_DT d FROM TB_SITE_CONTS")[0]["d"] is not None


def test_읽은_버전이_다르면_409이고_유형은_바꿀_수_없다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    made = make(world).json()
    path = f"/contents/{made['contentId']}"
    assert call(world, "PUT", path, {**body(title="첫 수정"), "version": 1}).status_code == 200
    stale = call(world, "PUT", path, {**body(title="낡은 수정"), "version": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    moved = call(world, "PUT", path, {**body("POPUP"), "version": 2})
    assert moved.status_code == 422 and "contentType" in moved.json()["fields"]
    assert call(world, "GET", path).json()["title"] == "첫 수정"


# --- 동 범위 ------------------------------------------------------------------------------------


def test_동_담당자는_자기_동_콘텐츠만_다루고_올린_콘텐츠는_자기_동의_것이다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = publish(world, "CT.BANNER", "banner-a", "내", DONG_SN=a["DONG_SN"])
    other = publish(world, "CT.BANNER", "banner-b", "남", DONG_SN=b["DONG_SN"])
    common = publish(world, "CT.BANNER", "banner-c", "공통")
    use(world, staff(world, "d", "AU.SITE_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [i["contentId"] for i in call(world, "GET", "/contents").json()["items"]] == [
        str(mine["SITE_CONTS_SN"])
    ]
    for hidden in (other, common):
        sn = hidden["SITE_CONTS_SN"]
        assert call(world, "GET", f"/contents/{sn}").status_code == 404
        assert call(world, "PUT", f"/contents/{sn}", {**body(), "version": 1}).status_code == 404
    made = make(world).json()
    assert int(
        rows(world, "SELECT DONG_SN d FROM TB_SITE_CONTS WHERE SITE_CONTS_SN=:s", s=made["contentId"])[0]["d"]
    ) == int(a["DONG_SN"])
    use(world, staff(world, "boss", "AU.SITE_W"))
    assert call(world, "GET", "/contents").json()["total"] == 4
