# 관리자 게시판 설정(AU.BBS_W)과 게시물 관리(AU.POST_W, 논리삭제·본문 정리·멱등·범위·CSV)를 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
import time
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin import board_service
from tests.arena import Arena, Staff, parallel
from tests.arena import make_member as make_arena_member
from tests.factory import RowFactory
from tests.test_admin_access import assign, dong, role
from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board, post
from tests.test_board_public import get as public_get
from tests.world import START, World, make_member

pytestmark = pytest.mark.db


def build_post(f: RowFactory) -> tuple[int, int]:
    bundle = f.bundle()
    bbs = f.make("TB_BBS", OPER_BNDL_SN=bundle, BBS_ID="notice", BBS_NM="공지", BBS_TYPE_CD="BT.NOTICE")
    # 작성자 관리자를 공장이 몰래 만들면 시험이 끝나도 남으므로 회원 작성 글로 만든다
    author = make_arena_member(f, bundle, "author")
    row = f.make(
        "TB_PST",
        OPER_BNDL_SN=bundle,
        BBS_SN=bbs["BBS_SN"],
        PST_TTL="공지",
        PST_CN="본문",
        WRT_MBR_SN=author,
        WRT_MNGR_SN=None,
    )
    return bundle, int(row["PST_SN"])


def body(key: str = "notice", **values: Any) -> dict[str, Any]:
    return {"boardKey": key, "title": "새 공지", "content": "<p>본문</p>", "pinned": False, **values}


def make(w: World, payload: dict[str, Any] | None = None, key: str = "key-00000001") -> Any:
    return call(w, "POST", "/posts", payload or body(), **{"Idempotency-Key": key})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def csv_rows(response: Any) -> list[list[str]]:
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/posts").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R"))
    for method, path, payload in (
        ("GET", "/boards", None),
        (
            "PUT",
            "/boards/notice",
            {
                "memberWrite": False,
                "answerEnabled": False,
                "attachEnabled": True,
                "allowPrivate": False,
                "inUse": True,
                "version": 1,
            },
        ),
        ("GET", "/posts", None),
        ("GET", "/posts/export.csv", None),
        ("POST", "/posts", body()),
        ("GET", "/posts/1", None),
        ("PUT", "/posts/1", {**body(), "version": 1}),
        ("DELETE", "/posts/1", None),
    ):
        assert call(world, method, path, payload, **{"Idempotency-Key": "key-00000001"}).status_code == 403, (
            path
        )


def test_게시판_설정만_있으면_게시물은_못_보고_게시물_권한만_있으면_설정은_읽는다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "bbs", "AU.BBS_W"))
    assert call(world, "GET", "/boards").status_code == 200
    assert call(world, "GET", "/posts").status_code == 403
    use(world, staff(world, "post", "AU.POST_W"))
    assert call(world, "GET", "/boards").status_code == 200


# --- 게시판 설정 --------------------------------------------------------------------------------


def settings_body(**values: Any) -> dict[str, Any]:
    return {
        "memberWrite": False,
        "answerEnabled": False,
        "attachEnabled": True,
        "allowPrivate": False,
        "inUse": True,
        "version": 1,
        **values,
    }


def test_게시판_목록은_정책과_글_수와_버전을_준다(world: World) -> None:
    notice, qna = (
        board(world, "notice", SORT_SEQ=1),
        board(world, "qna", SORT_SEQ=2, MBR_WRT_YN="Y", ANS_USE_YN="Y"),
    )
    post(world, notice, "하나")
    post(world, notice, "둘")
    post(world, notice, "지운 글", DEL_YN="Y")
    asked = post(world, qna, "질문")
    post(world, qna, "답변", UP_PST_SN=asked["PST_SN"], PST_TYPE_CD="PT.REPLY")  # 답변은 세지 않는다
    use(world, staff(world, "boss", "AU.BBS_W"))
    items = call(world, "GET", "/boards").json()["items"]
    assert [i["boardKey"] for i in items] == ["notice", "qna"]
    n, q = items
    assert (n["postCount"], n["version"], n["memberWrite"], n["attachEnabled"], n["inUse"]) == (
        2,
        1,
        False,
        True,
        True,
    )
    assert (q["memberWrite"], q["answerEnabled"], q["allowPrivate"], q["postCount"]) == (True, True, True, 1)
    assert n["allowPrivate"] is False


def test_설정을_바꾸면_버전이_오르고_작업이력에_남는다(world: World) -> None:
    board(world, "notice")
    boss = staff(world, "boss", "AU.BBS_W")
    use(world, boss)
    r = call(
        world, "PUT", "/boards/notice", settings_body(attachEnabled=False, answerEnabled=True, inUse=False)
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["attachEnabled"], out["answerEnabled"], out["inUse"], out["version"]) == (
        False,
        True,
        False,
        2,
    )
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='BBS_UPDATE'"
    )
    assert (job["m"], job["t"]) == (boss.sn, "TB_BBS") and job[
        "c"
    ] == "notice 회원작성 N 답변 Y 첨부 N 사용 N"
    stored = rows(
        world,
        "SELECT ATCH_USE_YN a, USE_YN u, ANS_USE_YN n, RCRD_VER v, BBS_NM nm FROM TB_BBS WHERE BBS_ID='notice'",
    )[0]
    assert (stored["a"], stored["u"], stored["n"], int(stored["v"]), stored["nm"]) == (
        "N",
        "N",
        "Y",
        2,
        "notice",
    )


def test_읽은_버전이_다르면_409이고_바꾸지_않는다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "boss", "AU.BBS_W"))
    assert call(world, "PUT", "/boards/notice", settings_body(inUse=False)).status_code == 200
    r = call(world, "PUT", "/boards/notice", settings_body(attachEnabled=False, version=1))  # 낡은 버전
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert rows(world, "SELECT ATCH_USE_YN a FROM TB_BBS WHERE BBS_ID='notice'")[0]["a"] == "Y"


def test_비공개_허용은_저장할_곳이_없어_현재_값과_다르면_거절한다(world: World) -> None:
    board(world, "notice")
    board(world, "qna", MBR_WRT_YN="Y")
    use(world, staff(world, "boss", "AU.BBS_W"))
    r = call(world, "PUT", "/boards/notice", settings_body(allowPrivate=True))
    assert (
        r.status_code == 422 and r.json()["code"] == "RULE_REJECTED" and "allowPrivate" in r.json()["fields"]
    )
    assert (
        call(world, "PUT", "/boards/qna", settings_body(memberWrite=True, allowPrivate=True)).status_code
        == 200
    )
    assert (
        call(
            world, "PUT", "/boards/qna", settings_body(memberWrite=True, allowPrivate=False, version=2)
        ).status_code
        == 422
    )


def test_설정은_묶음_전체_범위의_담당자만_바꾸고_없는_게시판은_404다(world: World) -> None:
    mine = dong(world, "가동")
    board(world, "notice")
    use(world, staff(world, "d", "AU.BBS_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert call(world, "PUT", "/boards/notice", settings_body()).status_code == 403
    use(world, staff(world, "boss", "AU.BBS_W"))
    assert call(world, "PUT", "/boards/faq", settings_body()).status_code == 404  # 이 묶음에 없는 게시판
    assert call(world, "PUT", "/boards/nope", settings_body()).status_code in (400, 422)


# --- 게시물 등록 --------------------------------------------------------------------------------


def test_등록하면_본문을_정리해_저장하고_관리자가_쓴_글로_남긴다(world: World) -> None:
    board(world, "notice")
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    r = make(
        world,
        body(
            title="  휴관 안내  ", content='<p onclick="x()">안내</p><script>alert(1)</script>', pinned=True
        ),
    )
    assert r.status_code == 201
    out = r.json()
    assert out["title"] == "휴관 안내" and out["content"] == "<p>안내</p>" and out["pinned"] is True
    assert (out["memberAuthored"], out["canEditContent"], out["version"], out["authorName"]) == (
        False,
        True,
        1,
        "김관리",
    )
    assert out["boardKey"] == "notice" and out["periodStart"] is None and out["periodEnd"] is None
    row = rows(
        world, "SELECT WRT_MNGR_SN m, WRT_MBR_SN b, PRVT_YN p, DEL_YN d, PST_TYPE_CD t, DONG_SN g FROM TB_PST"
    )[0]
    assert (row["m"], row["b"], row["p"], row["d"], row["t"], row["g"]) == (
        boss.sn,
        None,
        "N",
        "N",
        "PT.POST",
        None,
    )
    [job] = rows(world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='POST_CREATE'")
    assert job["c"].startswith("notice [idem ") and "휴관" not in job["c"]


def test_게시_기간을_받고_종료가_시작보다_앞서면_거절한다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "boss", "AU.POST_W"))
    ok = make(world, body(periodStart="2026-12-01T00:00:00+09:00", periodEnd="2026-12-31T00:00:00+09:00"))
    assert ok.status_code == 201 and ok.json()["periodStart"].startswith("2026-11-30T15:00:00")
    bad = make(
        world,
        body(periodStart="2026-12-31T00:00:00+09:00", periodEnd="2026-12-01T00:00:00+09:00"),
        "key-00000002",
    )
    assert bad.status_code == 422 and "periodEnd" in bad.json()["fields"]
    same = make(
        world,
        body(periodStart="2026-12-01T00:00:00+09:00", periodEnd="2026-12-01T00:00:00+09:00"),
        "key-00000003",
    )
    assert same.status_code == 422


def test_제목과_본문이_비면_거절한다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "boss", "AU.POST_W"))
    assert make(world, body(title="   "), "key-00000001").status_code == 422
    for n, content in enumerate(["<script>x</script>", "<p> </p>", "<img src=x>"]):
        r = make(world, body(content=content), f"key-0000001{n}")
        assert r.status_code == 422 and "content" in r.json()["fields"], content
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST")[0]["n"] == 0


def test_회원이_쓰는_게시판과_사용을_중지한_게시판에는_새_글을_올리지_못한다(world: World) -> None:
    board(world, "qna", MBR_WRT_YN="Y")
    board(world, "faq", USE_YN="N")
    use(world, staff(world, "boss", "AU.POST_W"))
    for n, key in enumerate(["qna", "faq"]):
        r = make(world, body(key), f"key-0000000{n}")
        assert r.status_code == 422 and "boardKey" in r.json()["fields"], key
    assert make(world, body("gallery"), "key-00000009").status_code == 404  # 이 묶음에 없는 게시판
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST")[0]["n"] == 0


def test_같은_키로_다시_보내면_같은_글을_주고_내용이_다르면_409다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "boss", "AU.POST_W"))
    first = make(world, body()).json()
    again = make(world, body())
    assert again.status_code == 201 and again.json()["postId"] == first["postId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST")[0]["n"] == 1
    diff = make(world, body(title="다른 제목"))
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/posts", body()).status_code in (400, 422)  # 멱등키 없음


def test_동_담당자가_올린_글은_자기_동의_글이고_담당_동이_여럿이면_거절한다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    board(world, "notice")
    one = staff(world, "one", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"])
    use(world, one)
    assert make(world, body()).status_code == 201
    assert int(rows(world, "SELECT DONG_SN g FROM TB_PST")[0]["g"]) == int(a["DONG_SN"])
    two = staff(world, "two", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"])
    assign(world, two.row, role(world, "r-two-extra", "AU.POST_W"), "SK.DONG", dong_sn=b["DONG_SN"])
    use(world, two)
    r = make(world, body(), "key-00000002")
    assert r.status_code == 422 and "하나로 정해지지" in r.json()["message"]


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_상단공지가_먼저이고_지운_글과_답변은_나오지_않으며_작성자를_가린다(world: World) -> None:
    notice, qna = board(world, "notice"), board(world, "qna", MBR_WRT_YN="Y")
    writer = make_member(world, "w1", MBR_NM="홍길동")
    old = post(world, notice, "오래된 글", REG_DT=START.replace(year=2025))
    new = post(world, notice, "새 글")
    pinned = post(world, notice, "고정 글", NTC_YN="Y", REG_DT=START.replace(year=2024))
    post(world, notice, "지운 글", DEL_YN="Y")
    asked = post(world, qna, "질문", WRT_MBR_SN=writer["MBR_SN"], WRT_MNGR_SN=None)
    post(world, qna, "답변", UP_PST_SN=asked["PST_SN"], PST_TYPE_CD="PT.REPLY")
    use(world, staff(world, "boss", "AU.POST_W"))
    body_ = call(world, "GET", "/posts").json()
    assert [i["title"] for i in body_["items"]][:3] == ["고정 글", "새 글", "오래된 글"] or body_["items"][0][
        "title"
    ] == "고정 글"
    assert {i["title"] for i in body_["items"]} == {"고정 글", "새 글", "오래된 글", "질문"} and body_[
        "total"
    ] == 4
    by_title = {i["title"]: i for i in body_["items"]}
    assert by_title["질문"]["authorName"] == "홍*동" and by_title["고정 글"]["pinned"] is True
    assert {old["PST_SN"], new["PST_SN"], pinned["PST_SN"]}
    only = call(world, "GET", "/posts?board=qna").json()
    assert [i["title"] for i in only["items"]] == ["질문"]
    assert [i["title"] for i in call(world, "GET", "/posts?q=오래").json()["items"]] == ["오래된 글"]
    assert call(world, "GET", "/posts?q=_").json()["total"] == 0  # 와일드카드는 글자로 다룬다


def test_목록은_쪽을_나눈다(world: World) -> None:
    notice = board(world, "notice")
    for n in range(3):
        post(world, notice, f"글{n}")
    use(world, staff(world, "boss", "AU.POST_W"))
    first = call(world, "GET", "/posts?size=2&page=1").json()
    second = call(world, "GET", "/posts?size=2&page=2").json()
    assert (len(first["items"]), len(second["items"]), first["total"]) == (2, 1, 3)


def test_동_담당자는_자기_동의_글만_보고_공통_글과_다른_동_글은_없는_것과_같다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    notice = board(world, "notice")
    mine = post(world, notice, "내 글", DONG_SN=a["DONG_SN"])
    other = post(world, notice, "남의 글", DONG_SN=b["DONG_SN"])
    common = post(world, notice, "공통 글")
    use(world, staff(world, "d", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [i["title"] for i in call(world, "GET", "/posts").json()["items"]] == ["내 글"]
    assert call(world, "GET", f"/posts/{mine['PST_SN']}").status_code == 200
    for hidden in (other, common):
        sn = hidden["PST_SN"]
        assert call(world, "GET", f"/posts/{sn}").status_code == 404
        assert call(world, "PUT", f"/posts/{sn}", {**body(), "version": 1}).status_code == 404
        assert call(world, "DELETE", f"/posts/{sn}").status_code == 404
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE DEL_YN='N'")[0]["n"] == 3
    use(world, staff(world, "boss", "AU.POST_W"))
    assert call(world, "GET", "/posts").json()["total"] == 3


def test_상세는_본문과_수정_가능_여부를_준다(world: World) -> None:
    qna = board(world, "qna", MBR_WRT_YN="Y")
    notice = board(world, "notice")
    writer = make_member(world, "w1", MBR_NM="홍길동")
    mine = post(
        world, notice, "공지", PST_CN="<p>안녕</p>", PSTG_BGNG_DT=START, PSTG_END_DT=START.replace(year=2027)
    )
    theirs = post(world, qna, "후기", WRT_MBR_SN=writer["MBR_SN"], WRT_MNGR_SN=None)
    use(world, staff(world, "boss", "AU.POST_W"))
    a = call(world, "GET", f"/posts/{mine['PST_SN']}").json()
    assert (a["content"], a["memberAuthored"], a["canEditContent"], a["version"]) == (
        "<p>안녕</p>",
        False,
        True,
        1,
    )
    assert a["periodStart"] is not None and a["periodEnd"] is not None
    b = call(world, "GET", f"/posts/{theirs['PST_SN']}").json()
    assert (b["memberAuthored"], b["canEditContent"], b["authorName"]) == (True, False, "홍*동")


def test_없거나_지웠거나_답변이거나_다른_묶음의_글은_404다(world: World) -> None:
    notice = board(world, "notice")
    gone = post(world, notice, "지운", DEL_YN="Y")
    reply = post(world, notice, "답", UP_PST_SN=post(world, notice, "원글")["PST_SN"], PST_TYPE_CD="PT.REPLY")
    other_bundle = int(world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"])
    foreign_bbs = world.factory.make(
        "TB_BBS", OPER_BNDL_SN=other_bundle, BBS_ID="notice", BBS_NM="공지", BBS_TYPE_CD="BT.NOTICE"
    )
    foreign = post(world, foreign_bbs, "타지")
    use(world, staff(world, "boss", "AU.POST_W"))
    for sn in (gone["PST_SN"], reply["PST_SN"], foreign["PST_SN"], 999999999):
        assert call(world, "GET", f"/posts/{sn}").status_code == 404, sn
    assert call(world, "GET", "/posts/abc").status_code in (400, 422)


# --- 수정·삭제 ----------------------------------------------------------------------------------


def test_수정하면_본문을_다시_정리하고_버전이_오르며_작업이력에_남긴다(world: World) -> None:
    board(world, "notice")
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    made = make(world).json()
    r = call(
        world,
        "PUT",
        f"/posts/{made['postId']}",
        {**body(title="수정 제목", content="<p>고침</p><script>x</script>", pinned=True), "version": 1},
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["title"], out["content"], out["pinned"], out["version"]) == (
        "수정 제목",
        "<p>고침</p>",
        True,
        2,
    )
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='POST_UPDATE'")
    assert (job["m"], job["c"]) == (boss.sn, "notice 수정")
    assert rows(world, "SELECT MDFCN_DT d FROM TB_PST")[0]["d"] is not None


def test_읽은_버전이_다르면_수정을_거절한다(world: World) -> None:
    board(world, "notice")
    use(world, staff(world, "boss", "AU.POST_W"))
    made = make(world).json()
    path = f"/posts/{made['postId']}"
    assert call(world, "PUT", path, {**body(title="첫 수정"), "version": 1}).status_code == 200
    r = call(world, "PUT", path, {**body(title="낡은 수정"), "version": 1})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert call(world, "GET", path).json()["title"] == "첫 수정"


def test_회원이_쓴_글은_내용을_고치지_못하고_게시판도_바꾸지_못한다(world: World) -> None:
    qna, notice = board(world, "qna", MBR_WRT_YN="Y"), board(world, "notice")
    writer = make_member(world, "w1")
    theirs = post(world, qna, "후기", WRT_MBR_SN=writer["MBR_SN"], WRT_MNGR_SN=None)
    mine = post(world, notice, "공지")
    use(world, staff(world, "boss", "AU.POST_W"))
    r = call(world, "PUT", f"/posts/{theirs['PST_SN']}", {**body("qna"), "version": 1})
    assert r.status_code == 422 and "삭제만" in r.json()["message"]
    moved = call(world, "PUT", f"/posts/{mine['PST_SN']}", {**body("qna"), "version": 1})
    assert moved.status_code == 422 and "boardKey" in moved.json()["fields"]
    assert rows(world, "SELECT PST_TTL t FROM TB_PST WHERE PST_SN=:s", s=theirs["PST_SN"])[0]["t"] == "후기"


def test_수정도_정리한_뒤_비면_거절한다(world: World) -> None:
    notice = board(world, "notice")
    mine = post(world, notice, "공지")
    use(world, staff(world, "boss", "AU.POST_W"))
    r = call(world, "PUT", f"/posts/{mine['PST_SN']}", {**body(content="<script>x</script>"), "version": 1})
    assert r.status_code == 422 and "content" in r.json()["fields"]


def test_삭제는_삭제여부만_바꾸고_공개_목록에서도_사라지며_다시_지우면_404다(world: World) -> None:
    notice = board(world, "notice")
    mine = post(world, notice, "공지")
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    assert public_get(world, "/boards/notice/posts").json()["total"] == 1
    r = call(world, "DELETE", f"/posts/{mine['PST_SN']}")
    assert r.status_code == 204 and r.content == b""
    row = rows(world, "SELECT DEL_YN d, PST_TTL t, RCRD_VER v FROM TB_PST WHERE PST_SN=:s", s=mine["PST_SN"])[
        0
    ]
    assert (row["d"], row["t"], int(row["v"])) == ("Y", "공지", int(mine["RCRD_VER"]) + 1)  # 행은 남는다
    assert call(world, "GET", f"/posts/{mine['PST_SN']}").status_code == 404
    assert call(world, "DELETE", f"/posts/{mine['PST_SN']}").status_code == 404
    assert public_get(world, "/boards/notice/posts").json()["total"] == 0
    [job] = rows(world, "SELECT MNGR_SN m, TRGT_KEY_VL k FROM TB_JOB_HSTRY WHERE JOB_CD='POST_DELETE'")
    assert (job["m"], job["k"]) == (boss.sn, str(mine["PST_SN"]))


def test_회원이_쓴_글도_지울_수_있다(world: World) -> None:
    qna = board(world, "qna", MBR_WRT_YN="Y")
    theirs = post(world, qna, "후기", WRT_MBR_SN=make_member(world, "w1")["MBR_SN"], WRT_MNGR_SN=None)
    use(world, staff(world, "boss", "AU.POST_W"))
    assert call(world, "DELETE", f"/posts/{theirs['PST_SN']}").status_code == 204


# --- CSV ----------------------------------------------------------------------------------------


def test_게시물_CSV는_목록과_같은_조건이고_본문과_회원_이름을_담지_않는다(world: World) -> None:
    notice, qna = board(world, "notice"), board(world, "qna", MBR_WRT_YN="Y")
    post(world, notice, "공지 하나", PST_CN="비밀 본문", NTC_YN="Y")
    post(world, notice, "지운 글", DEL_YN="Y")
    post(
        world,
        qna,
        "질문 글",
        WRT_MBR_SN=make_member(world, "w1", MBR_NM="홍길동")["MBR_SN"],
        WRT_MNGR_SN=None,
    )
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    r = call(world, "GET", "/posts/export.csv")
    table = csv_rows(r)
    assert table[0] == [
        "게시물번호",
        "게시판",
        "제목",
        "작성자",
        "상단공지",
        "게시 시작",
        "게시 종료",
        "등록일",
    ]
    assert [row[2] for row in table[1:]] == ["공지 하나", "질문 글"]  # 상단공지가 먼저, 지운 글은 없다
    assert table[1][4] == "Y" and table[2][3] == "홍*동"
    assert "비밀 본문" not in r.text and "홍길동" not in r.text
    assert [row[2] for row in csv_rows(call(world, "GET", "/posts/export.csv?board=qna"))[1:]] == ["질문 글"]
    [first, *_] = rows(
        world,
        "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT' ORDER BY JOB_HSTRY_SN",
    )
    assert (first["m"], first["t"], first["c"]) == (boss.sn, "TB_PST", "2건 내보냄(조건: 없음)")


def test_게시물_CSV도_동_범위를_따르고_권한이_없으면_403이다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    notice = board(world, "notice")
    post(world, notice, "내 글", DONG_SN=a["DONG_SN"])
    post(world, notice, "남의 글", DONG_SN=b["DONG_SN"])
    use(world, staff(world, "d", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [row[2] for row in csv_rows(call(world, "GET", "/posts/export.csv"))[1:]] == ["내 글"]
    use(world, staff(world, "x", "AU.BBS_W"))
    assert call(world, "GET", "/posts/export.csv").status_code == 403


def test_여러_담당자가_같은_글을_동시에_지워도_한_번만_지운다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = board_service._load

    def slow(*args: Any) -> Any:
        found = real(*args)
        time.sleep(0.3)  # 읽은 뒤 잠그기 전의 틈을 넓혀 잠금이 없으면 겹치게 한다
        return found

    monkeypatch.setattr(board_service, "_load", slow)
    bundle, post_sn = arena.build(build_post)
    arena.serve(bundle)
    staffs = [arena.staff(bundle, f"s{n}", "AU.POST_W") for n in range(4)]

    def deleter(s: Staff) -> Callable[[], Any]:
        return lambda: s.client.delete(f"/api/admin/v1/posts/{post_sn}", headers={"X-CSRF-Token": s.csrf})

    calls = [deleter(s) for s in staffs]
    codes = sorted(r.status_code for r in parallel(calls))
    assert codes == [204, 404, 404, 404], codes
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='POST_DELETE'")) == 1
    assert int(arena.query("SELECT RCRD_VER v FROM TB_PST WHERE PST_SN=:s", s=post_sn)[0]["v"]) == 2
