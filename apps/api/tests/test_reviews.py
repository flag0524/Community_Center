# 수강후기 공개 조회와 주민 쪽 작성·수정·삭제(수강확정 이후, 한 강좌에 한 번)를 실제 앱과 DB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_applications_read import application, open_course
from tests.test_board_public import board, post
from tests.test_member_inquiries import as_member, csrf, person
from tests.world import MEMBER, START, World

pytestmark = pytest.mark.db

_n = itertools.count(1)
PUBLIC = "/api/v1/reviews"


@pytest.fixture
def review_board(world: World) -> dict[str, Any]:
    return board(world, "review", MBR_WRT_YN="Y")


def take(w: World, who: dict[str, Any], c: dict[str, Any], state: str = "ES.CONFIRM") -> dict[str, Any]:
    return application(w, who, c, state)


def written(
    w: World,
    bbs: dict[str, Any],
    who: dict[str, Any],
    c: dict[str, Any],
    title: str = "좋았어요",
    **values: Any,
) -> dict[str, Any]:
    return post(w, bbs, title, WRT_MBR_SN=who["MBR_SN"], WRT_MNGR_SN=None, CORS_SN=c["CORS_SN"], **values)


def send(
    w: World, method: str, path: str, payload: dict[str, Any] | None = None, key: str | None = None
) -> Any:
    headers = {**csrf(w), **({"Idempotency-Key": key} if key else {})}
    return w.client.request(method, f"{MEMBER}{path}", json=payload, headers=headers)


def write(
    w: World, c: dict[str, Any], title: str = "좋았어요", body: str = "재미있었습니다", key: str | None = None
) -> Any:
    payload = {"courseId": str(c["CORS_SN"]), "title": title, "body": body}
    return send(w, "POST", "/me/reviews", payload, key or f"rvw-key-{next(_n):06d}")


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 공개 조회 ----------------------------------------------------------------------------------


def test_후기_목록은_로그인하지_않아도_최근_순으로_보고_작성자는_가린다(
    world: World, review_board: dict[str, Any]
) -> None:
    c1, c2 = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    me, other = person(world, "홍길동"), person(world, "박다라")
    old = written(world, review_board, me, c1, "지난 후기", REG_DT=START.replace(day=1))
    new = written(world, review_board, other, c2, "새 후기", REG_DT=START.replace(day=5))
    res = world.client.get(PUBLIC)
    assert res.status_code == 200
    body = res.json()
    assert [i["postId"] for i in body["items"]] == [str(new["PST_SN"]), str(old["PST_SN"])] and body[
        "total"
    ] == 2
    assert [(i["title"], i["authorName"], i["courseName"], i["isMine"]) for i in body["items"]] == [
        ("새 후기", "박*라", "서예", False),
        ("지난 후기", "홍*동", "요가", False),
    ]
    assert "홍길동" not in str(body) and "박다라" not in str(body)


def test_로그인하면_내_후기에_내_글_표시가_붙는다(world: World, review_board: dict[str, Any]) -> None:
    c = open_course(world)
    me, other = person(world, "홍길동"), person(world, "박다라")
    mine = written(world, review_board, me, c)
    theirs = written(world, review_board, other, c)
    as_member(world, me)
    items = {i["postId"]: i["isMine"] for i in world.client.get(PUBLIC).json()["items"]}
    assert items == {str(mine["PST_SN"]): True, str(theirs["PST_SN"]): False}
    detail = world.client.get(f"{PUBLIC}/{theirs['PST_SN']}").json()
    assert (detail["canEdit"], detail["canDelete"]) == (False, False)
    own = world.client.get(f"{PUBLIC}/{mine['PST_SN']}").json()
    assert (own["canEdit"], own["canDelete"]) == (True, True)


def test_제목으로_찾고_쪽을_나눈다(world: World, review_board: dict[str, Any]) -> None:
    c = open_course(world)
    for title in ("요가 후기", "서예 후기", "요가 두번째"):
        written(world, review_board, person(world), c, title)

    def titles(qs: str) -> list[str]:
        return [i["title"] for i in world.client.get(f"{PUBLIC}{qs}").json()["items"]]

    assert sorted(titles("?q=요가")) == ["요가 두번째", "요가 후기"]
    assert titles("?q=_") == [] and titles("?q=%25") == []
    assert [len(titles(f"?size=2&page={p}")) for p in (1, 2, 3)] == [2, 1, 0]
    assert world.client.get(f"{PUBLIC}?size=51").status_code in (400, 422)


def test_지운_후기와_비공개와_다른_게시판의_글과_꺼진_게시판은_나오지_않는다(
    world: World, review_board: dict[str, Any]
) -> None:
    c = open_course(world)
    who = person(world)
    shown = written(world, review_board, who, c, "보이는 후기")
    hidden = {
        "삭제": written(world, review_board, who, c, "삭제", DEL_YN="Y"),
        "비공개": written(world, review_board, who, c, "비공개", PRVT_YN="Y"),
        "답글": written(
            world, review_board, who, c, "답글", UP_PST_SN=shown["PST_SN"], PST_TYPE_CD="PT.REPLY"
        ),
        "다른 게시판": post(world, board(world, "notice"), "공지", CORS_SN=c["CORS_SN"]),
    }
    items = world.client.get(PUBLIC).json()["items"]
    assert [i["postId"] for i in items] == [str(shown["PST_SN"])]
    for name, row in hidden.items():
        assert world.client.get(f"{PUBLIC}/{row['PST_SN']}").status_code == 404, name
    assert world.client.get(f"{PUBLIC}/999999999").status_code == 404
    world.db.execute(text("UPDATE TB_BBS SET USE_YN='N' WHERE BBS_SN=:b"), {"b": review_board["BBS_SN"]})
    world.db.commit()
    assert world.client.get(PUBLIC).json()["total"] == 0


# --- 작성 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_내_후기_관련은_모두_401이다(world: World) -> None:
    for method, path in (
        ("GET", "/me/reviews"),
        ("GET", "/me/reviewable-courses"),
        ("POST", "/me/reviews"),
        ("PUT", "/me/reviews/1"),
        ("DELETE", "/me/reviews/1"),
    ):
        assert world.client.request(method, f"{MEMBER}{path}").status_code == 401, path


def test_수강확정이거나_수강종료인_강좌만_후기를_쓸_수_있다고_알린다(
    world: World, review_board: dict[str, Any]
) -> None:
    me = person(world)
    confirmed, done = open_course(world, CORS_NM="확정 강좌"), open_course(world, CORS_NM="종료 강좌")
    take(world, me, confirmed)
    take(world, me, done, "ES.COMPLETE")
    for state, name in (
        ("ES.WAIT", "대기"),
        ("ES.HOLD", "결제 대기"),
        ("ES.CANCEL", "취소"),
        ("ES.EXPIRE", "만료"),
    ):
        take(world, me, open_course(world, CORS_NM=name), state)
    open_course(world, CORS_NM="신청 없음")
    as_member(world, me)
    out = send(world, "GET", "/me/reviewable-courses").json()
    assert [i["name"] for i in out["items"]] == ["종료 강좌", "확정 강좌"]
    assert set(out["items"][0]) == {"courseId", "name"}


def test_후기를_쓰면_공개_글로_저장하고_강좌의_동이_글의_동이다(
    world: World, review_board: dict[str, Any]
) -> None:
    a = dong(world, "가동")
    c = open_course(world, DONG_SN=a["DONG_SN"])
    me = person(world, "홍길동")
    take(world, me, c)
    as_member(world, me)
    r = write(world, c, "  좋았어요  ", "  재미있었습니다  ")
    assert r.status_code == 201, r.text
    out = r.json()
    assert (
        out["courseId"],
        out["courseName"],
        out["title"],
        out["body"],
        out["authorName"],
        out["canEdit"],
        out["canDelete"],
    ) == (
        str(c["CORS_SN"]),
        "요가",
        "좋았어요",
        "재미있었습니다",
        "홍*동",
        True,
        True,
    )
    [row] = rows(world, "SELECT * FROM TB_PST WHERE WRT_MBR_SN=:m", m=me["MBR_SN"])
    assert (
        row["BBS_SN"],
        row["DONG_SN"],
        row["CORS_SN"],
        row["PRVT_YN"],
        row["DEL_YN"],
        row["PST_TYPE_CD"],
        row["INQRY_CLSF_CD"],
        row["UP_PST_SN"],
    ) == (
        review_board["BBS_SN"],
        a["DONG_SN"],
        c["CORS_SN"],
        "N",
        "N",
        "PT.POST",
        None,
        None,
    )
    [job] = rows(world, "SELECT ACTR_TYPE_CD a, MBR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='RVW_CREATE'")
    assert (job["a"], job["m"]) == ("AK.MEMBER", me["MBR_SN"])
    assert [i["postId"] for i in world.client.get(PUBLIC).json()["items"]] == [out["postId"]]
    assert send(world, "GET", "/me/reviewable-courses").json()["items"] == []  # 쓴 강좌는 더 쓰지 않는다


def test_수강하지_않았거나_이미_쓴_강좌와_받지_않는_게시판은_422다(
    world: World, review_board: dict[str, Any]
) -> None:
    me = person(world)
    taken, never, waiting = (
        open_course(world, CORS_NM="수강"),
        open_course(world, CORS_NM="미수강"),
        open_course(world, CORS_NM="대기"),
    )
    take(world, me, taken)
    take(world, me, waiting, "ES.WAIT")
    as_member(world, me)
    for c in (never, waiting, {"CORS_SN": 999999999}):
        r = write(world, c)
        assert r.status_code == 422 and "courseId" in r.json()["fields"], c["CORS_SN"]
    assert write(world, taken).status_code == 201
    again = write(world, taken)
    assert again.status_code == 422 and "courseId" in again.json()["fields"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE WRT_MBR_SN=:m", m=me["MBR_SN"])[0]["n"] == 1
    world.db.execute(text("UPDATE TB_BBS SET MBR_WRT_YN='N' WHERE BBS_SN=:b"), {"b": review_board["BBS_SN"]})
    world.db.commit()
    off = write(world, taken, key="rvw-key-off001")
    assert off.status_code == 422 and "받지" in off.json()["message"]


def test_빈_제목과_내용은_거절하고_지우면_다시_쓸_수_있다(world: World, review_board: dict[str, Any]) -> None:
    c = open_course(world)
    me = person(world)
    take(world, me, c)
    as_member(world, me)
    assert "title" in write(world, c, title="   ").json()["fields"]
    assert "body" in write(world, c, body="   ").json()["fields"]
    assert write(world, c, title="").status_code in (400, 422)
    made = write(world, c).json()["postId"]
    assert send(world, "DELETE", f"/me/reviews/{made}").status_code == 204
    assert write(world, c, "다시 쓴 후기").status_code == 201


def test_같은_키로_다시_보내면_같은_후기이고_내용이_다르면_409다(
    world: World, review_board: dict[str, Any]
) -> None:
    c = open_course(world)
    me = person(world)
    take(world, me, c)
    as_member(world, me)
    first = write(world, c, key="rvw-key-same01").json()
    again = write(world, c, key="rvw-key-same01")
    assert again.status_code == 201 and again.json()["postId"] == first["postId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE WRT_MBR_SN=:m", m=me["MBR_SN"])[0]["n"] == 1
    other = write(world, c, "다른 제목", key="rvw-key-same01")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    no_key = send(world, "POST", "/me/reviews", {"courseId": str(c["CORS_SN"]), "title": "t", "body": "b"})
    assert no_key.status_code in (400, 422)


# --- 수정·삭제 ----------------------------------------------------------------------------------


def test_내_후기는_제목과_내용만_고치고_강좌는_바꿀_수_없다(
    world: World, review_board: dict[str, Any]
) -> None:
    c, other_course = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    me = person(world)
    take(world, me, c)
    take(world, me, other_course)
    as_member(world, me)
    sn = write(world, c).json()["postId"]
    ok = send(
        world,
        "PUT",
        f"/me/reviews/{sn}",
        {"courseId": str(c["CORS_SN"]), "title": " 고친 제목 ", "body": "고친 내용"},
    )
    assert ok.status_code == 200, ok.text
    assert (ok.json()["title"], ok.json()["body"], ok.json()["courseId"]) == (
        "고친 제목",
        "고친 내용",
        str(c["CORS_SN"]),
    )
    [row] = rows(world, "SELECT RCRD_VER v, MDFCN_DT d, CORS_SN c FROM TB_PST WHERE PST_SN=:s", s=sn)
    assert (row["v"], row["c"]) == (2, c["CORS_SN"]) and row["d"] is not None
    moved = send(
        world,
        "PUT",
        f"/me/reviews/{sn}",
        {"courseId": str(other_course["CORS_SN"]), "title": "t", "body": "b"},
    )
    assert moved.status_code == 422 and "courseId" in moved.json()["fields"]
    blank = send(
        world, "PUT", f"/me/reviews/{sn}", {"courseId": str(c["CORS_SN"]), "title": "  ", "body": "b"}
    )
    assert blank.status_code == 422 and "title" in blank.json()["fields"]
    assert world.client.get(f"{PUBLIC}/{sn}").json()["title"] == "고친 제목"


def test_남의_후기와_지운_후기는_고치거나_지울_수_없고_404다(
    world: World, review_board: dict[str, Any]
) -> None:
    c = open_course(world)
    me, other = person(world, "홍길동"), person(world, "박다라")
    theirs = written(world, review_board, other, c, "남의 후기")
    gone = written(world, review_board, me, c, "지운 후기", DEL_YN="Y")
    as_member(world, me)
    payload = {"courseId": str(c["CORS_SN"]), "title": "가로채기", "body": "b"}
    for sn in (theirs["PST_SN"], gone["PST_SN"], 999999999):
        assert send(world, "PUT", f"/me/reviews/{sn}", payload).status_code == 404, sn
        assert send(world, "DELETE", f"/me/reviews/{sn}").status_code == 404, sn
    assert rows(world, "SELECT PST_TTL t, DEL_YN d FROM TB_PST WHERE PST_SN=:s", s=theirs["PST_SN"])[0] == {
        "t": "남의 후기",
        "d": "N",
    }


def test_삭제는_논리삭제이고_공개_목록에서_사라진다(world: World, review_board: dict[str, Any]) -> None:
    c = open_course(world)
    me = person(world)
    take(world, me, c)
    as_member(world, me)
    sn = write(world, c).json()["postId"]
    assert send(world, "DELETE", f"/me/reviews/{sn}").status_code == 204
    assert rows(world, "SELECT DEL_YN d, RCRD_VER v FROM TB_PST WHERE PST_SN=:s", s=sn)[0] == {
        "d": "Y",
        "v": 2,
    }
    assert (
        world.client.get(f"{PUBLIC}/{sn}").status_code == 404
        and world.client.get(PUBLIC).json()["total"] == 0
    )
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='RVW_DELETE'")[0]["n"] == 1
    assert send(world, "DELETE", f"/me/reviews/{sn}").status_code == 404


def test_내_후기_목록은_내_글만_최근_순이다(world: World, review_board: dict[str, Any]) -> None:
    c1, c2 = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    me, other = person(world), person(world, "박다라")
    old = written(world, review_board, me, c1, "지난 후기", REG_DT=START.replace(day=1))
    new = written(world, review_board, me, c2, "새 후기", REG_DT=START.replace(day=5))
    written(world, review_board, other, c1, "남의 후기")
    as_member(world, me)
    body = send(world, "GET", "/me/reviews").json()
    assert [i["postId"] for i in body["items"]] == [str(new["PST_SN"]), str(old["PST_SN"])] and body[
        "total"
    ] == 2
    assert all(i["isMine"] for i in body["items"])
    assert [len(send(world, "GET", f"/me/reviews?size=1&page={p}").json()["items"]) for p in (1, 2, 3)] == [
        1,
        1,
        0,
    ]
