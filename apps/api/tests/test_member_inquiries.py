# 주민 쪽 문의 조회·작성·수정·삭제와 관리자 답변이 주민에게 보이는 흐름을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board, post
from tests.world import MEMBER, START, World, login, make_member

pytestmark = pytest.mark.db

PATH = "/me/inquiries"
_n = itertools.count(1)


def category(w: World, code: str = "IQ.COURSE", name: str = "수강신청", seq: int = 1) -> None:
    w.factory.make("TB_COM_CD", COM_CD=code, CD_GROUP_ID="IQ", CD_NM=name, SORT_SEQ=seq, USE_YN="Y")


def person(w: World, name: str = "홍길동", **values: Any) -> dict[str, Any]:
    return make_member(w, f"mem{next(_n)}", MBR_NM=name, **values)


def as_member(w: World, who: dict[str, Any]) -> None:
    w.client.cookies.clear()  # 로그인은 로그인 전 상태에서만 되므로 이전 세션을 비운다
    assert login(w, MEMBER, who["LGN_ID"]).status_code == 200


def csrf(w: World) -> dict[str, str]:
    return {"X-CSRF-Token": str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])}


def get(w: World, path: str) -> Any:
    return w.client.get(f"{MEMBER}{path}")


def write(
    w: World, method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None
) -> Any:
    headers = csrf(w)
    if key:
        headers["Idempotency-Key"] = key
    return w.client.request(method, f"{MEMBER}{path}", json=body, headers=headers)


def form(**values: Any) -> dict[str, Any]:
    return {
        "categoryId": "IQ.COURSE",
        "title": "수강 문의",
        "body": "문의 내용입니다",
        "isPrivate": False,
        **values,
    }


def create(w: World, body: dict[str, Any] | None = None, key: str = "inq-key-00000001") -> Any:
    return write(w, "POST", PATH, body or form(), key)


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


@pytest.fixture
def qna(world: World) -> dict[str, Any]:
    return board(world, "qna", MBR_WRT_YN="Y", ANS_USE_YN="Y")


def asked(
    w: World, bbs: dict[str, Any], owner: dict[str, Any], title: str = "문의", **values: Any
) -> dict[str, Any]:
    return post(w, bbs, title, WRT_MBR_SN=owner["MBR_SN"], WRT_MNGR_SN=None, **values)


def answered(w: World, original: dict[str, Any], content: str = "답변입니다") -> dict[str, Any]:
    return post(
        w,
        {"OPER_BNDL_SN": original["OPER_BNDL_SN"], "BBS_SN": original["BBS_SN"]},
        "답변",
        UP_PST_SN=original["PST_SN"],
        PST_TYPE_CD="PT.REPLY",
        PST_CN=content,
    )


# --- 로그인·분류 --------------------------------------------------------------------------------


def test_로그인이_없으면_모두_401이다(world: World, qna: dict[str, Any]) -> None:
    for method, path in (
        ("GET", "/inquiry-categories"),
        ("GET", "/inquiries"),
        ("GET", "/inquiries/1"),
        ("GET", PATH),
        ("POST", PATH),
        ("PUT", f"{PATH}/1"),
        ("DELETE", f"{PATH}/1"),
    ):
        assert world.client.request(method, f"{MEMBER}{path}").status_code == 401, path


def test_분류는_공통코드에서_쓰는_것만_정렬_순서로_준다(world: World) -> None:
    category(world, "IQ.PAY", "결제", 2)
    category(world, "IQ.COURSE", "수강신청", 1)
    category(world, "IQ.OLD", "중지", 3)
    world.db.execute(text("UPDATE TB_COM_CD SET USE_YN='N' WHERE COM_CD='IQ.OLD'"))
    as_member(world, person(world))
    assert get(world, "/inquiry-categories").json()["items"] == [
        {"categoryId": "IQ.COURSE", "name": "수강신청"},
        {"categoryId": "IQ.PAY", "name": "결제"},
    ]


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_모든_문의를_주되_다른_회원의_비공개_문의는_제목과_작성자를_가린다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    me, other = person(world, "홍길동"), person(world, "박다라")
    day = timedelta(days=1)
    mine_private = asked(
        world, qna, me, "내 비공개", PRVT_YN="Y", INQRY_CLSF_CD="IQ.COURSE", REG_DT=START - 3 * day
    )
    other_public = asked(world, qna, other, "남의 공개", REG_DT=START - 2 * day)
    other_private = asked(world, qna, other, "남의 비공개", PRVT_YN="Y", REG_DT=START - 1 * day)
    answered(world, other_public)
    as_member(world, me)
    body = get(world, "/inquiries").json()
    assert [i["title"] for i in body["items"]] == [
        "비공개 문의입니다.",
        "남의 공개",
        "내 비공개",
    ]  # 최근 등록이 먼저다
    first, second, third = body["items"]
    assert (first["postId"], first["authorName"], first["isMine"], first["isPrivate"]) == (
        str(other_private["PST_SN"]),
        "박**",
        False,
        True,
    )
    assert (second["authorName"], second["status"], second["isMine"]) == ("박*라", "ANSWERED", False)
    assert (third["authorName"], third["isMine"], third["categoryName"], third["status"]) == (
        "홍*동",
        True,
        "수강신청",
        "RECEIVED",
    )
    assert mine_private and body["total"] == 3
    assert [i["postId"] for i in get(world, "/inquiries?size=1&page=2").json()["items"]] == [
        str(other_public["PST_SN"])
    ]


def test_목록에는_질문과_답변_게시판의_지우지_않은_원글만_나온다(world: World, qna: dict[str, Any]) -> None:
    me = person(world)
    post(world, board(world, "notice"), "공지")
    asked(world, qna, me, "지운 문의", DEL_YN="Y")
    keep = asked(world, qna, me, "문의")
    answered(world, keep)
    as_member(world, me)
    assert [i["title"] for i in get(world, "/inquiries").json()["items"]] == ["문의"]
    assert get(world, "/inquiries").json()["total"] == 1


def test_내_문의_목록에는_내_글만_있고_비공개도_제목이_보인다(world: World, qna: dict[str, Any]) -> None:
    me, other = person(world), person(world, "박다라")
    asked(world, qna, me, "내 비공개", PRVT_YN="Y")
    asked(world, qna, other, "남의 글")
    as_member(world, me)
    items = get(world, "/me/inquiries").json()["items"]
    assert [(i["title"], i["isMine"], i["isPrivate"]) for i in items] == [("내 비공개", True, True)]


def test_상세는_공개_문의와_내_문의를_보이고_다른_회원의_비공개는_404다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    me, other = person(world, "홍길동"), person(world, "박다라")
    mine = asked(world, qna, me, "내 글", PRVT_YN="Y", PST_CN="내 본문", INQRY_CLSF_CD="IQ.COURSE")
    public = asked(world, qna, other, "남의 공개", PST_CN="공개 본문", INQRY_CLSF_CD="IQ.COURSE")
    private = asked(world, qna, other, "남의 비공개", PRVT_YN="Y", INQRY_CLSF_CD="IQ.COURSE")
    answered(world, private, "비공개 답변")
    as_member(world, me)
    a = get(world, f"/inquiries/{mine['PST_SN']}").json()
    assert (
        a["title"],
        a["body"],
        a["categoryId"],
        a["categoryName"],
        a["canEdit"],
        a["canDelete"],
        a["answer"],
    ) == (
        "내 글",
        "내 본문",
        "IQ.COURSE",
        "수강신청",
        True,
        True,
        None,
    )
    b = get(world, f"/inquiries/{public['PST_SN']}").json()
    assert (b["body"], b["authorName"], b["canEdit"], b["canDelete"]) == ("공개 본문", "박*라", False, False)
    assert get(world, f"/inquiries/{private['PST_SN']}").status_code == 404  # 답변도 비공개 범위를 따른다
    assert get(world, "/inquiries/999999999").status_code == 404
    assert get(world, "/inquiries/abc").status_code in (400, 422)


def test_답변이_달리면_상세에_답변이_보이고_고칠_수_없다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    mine = asked(world, qna, me, "내 글", INQRY_CLSF_CD="IQ.COURSE")
    answered(world, mine, "안내드립니다\n\n관련 화면: /center/contact")
    as_member(world, me)
    body = get(world, f"/inquiries/{mine['PST_SN']}").json()
    assert body["status"] == "ANSWERED" and body["canEdit"] is False and body["canDelete"] is True
    assert (
        body["answer"]["body"] == "안내드립니다\n\n관련 화면: /center/contact"
        and body["answer"]["answeredAt"]
    )


def test_지운_답변은_답변으로_치지_않고_지운_문의는_404다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    mine = asked(world, qna, me, "내 글", INQRY_CLSF_CD="IQ.COURSE")
    post(
        world,
        {"OPER_BNDL_SN": mine["OPER_BNDL_SN"], "BBS_SN": mine["BBS_SN"]},
        "지운 답변",
        UP_PST_SN=mine["PST_SN"],
        PST_TYPE_CD="PT.REPLY",
        DEL_YN="Y",
    )
    gone = asked(world, qna, me, "지움", DEL_YN="Y")
    as_member(world, me)
    assert get(world, f"/inquiries/{mine['PST_SN']}").json()["answer"] is None
    assert get(world, f"/inquiries/{gone['PST_SN']}").status_code == 404


# --- 작성 ---------------------------------------------------------------------------------------


def test_작성하면_본인_문의로_저장하고_회원의_동을_글의_동으로_남긴다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    my_dong = dong(world, "가동")
    me = person(world, "홍길동", DONG_SN=my_dong["DONG_SN"])
    as_member(world, me)
    r = create(world, form(title="  제목  ", body="  내용  ", isPrivate=True))
    assert r.status_code == 201
    out = r.json()
    assert (out["title"], out["body"], out["isPrivate"], out["status"], out["canEdit"], out["canDelete"]) == (
        "제목",
        "내용",
        True,
        "RECEIVED",
        True,
        True,
    )
    assert (out["categoryId"], out["categoryName"], out["authorName"], out["answer"]) == (
        "IQ.COURSE",
        "수강신청",
        "홍*동",
        None,
    )
    [row] = rows(world, "SELECT * FROM TB_PST WHERE PST_TYPE_CD='PT.POST' AND WRT_MBR_SN=:m", m=me["MBR_SN"])
    assert (
        row["WRT_MNGR_SN"],
        row["PRVT_YN"],
        row["NTC_YN"],
        row["DEL_YN"],
        row["INQRY_CLSF_CD"],
        int(row["RCRD_VER"]),
    ) == (
        None,
        "Y",
        "N",
        "N",
        "IQ.COURSE",
        1,
    )
    assert row["DONG_SN"] == my_dong["DONG_SN"] and row["BBS_SN"] == qna["BBS_SN"]
    [job] = rows(
        world,
        "SELECT ACTR_TYPE_CD a, MBR_SN m, TRGT_KEY_VL k, CHG_CN c "
        "FROM TB_JOB_HSTRY WHERE JOB_CD='INQ_CREATE'",
    )
    assert (job["a"], job["m"], job["k"]) == ("AK.MEMBER", me["MBR_SN"], str(row["PST_SN"]))
    assert job["c"].startswith("문의 등록 [idem ") and "내용" not in job["c"]


def test_같은_키로_다시_보내면_같은_문의이고_내용이_다르면_409다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    as_member(world, person(world))
    first = create(world).json()
    again = create(world)
    assert again.status_code == 201 and again.json()["postId"] == first["postId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE PST_TYPE_CD='PT.POST'")[0]["n"] == 1
    diff = create(world, form(title="다른 제목"))
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert create(world, form(), "inq-key-00000002").status_code == 201  # 새 키는 새 문의다
    assert write(world, "POST", PATH, form()).status_code in (400, 422)  # 멱등키 없음


def test_멱등키는_회원마다_따로_센다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    a, b = person(world), person(world, "박다라")
    as_member(world, a)
    ra = create(world).json()
    as_member(world, b)
    rb = create(world)
    assert rb.status_code == 201 and rb.json()["postId"] != ra["postId"]


def test_분류가_없거나_쓰지_않거나_형식이_틀리면_거절한다(world: World, qna: dict[str, Any]) -> None:
    category(world, "IQ.OLD", "중지")
    world.db.execute(text("UPDATE TB_COM_CD SET USE_YN='N' WHERE COM_CD='IQ.OLD'"))
    as_member(world, person(world))
    for n, code in enumerate(["IQ.NONE", "IQ.OLD"]):
        r = create(world, form(categoryId=code), f"inq-key-0000000{n}")
        assert r.status_code == 422 and "categoryId" in r.json()["fields"], code
    assert create(world, form(categoryId="1"), "inq-key-00000009").status_code in (400, 422)
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE PST_TYPE_CD='PT.POST'")[0]["n"] == 0


def test_공백뿐인_제목과_내용은_거절한다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    as_member(world, person(world))
    a = create(world, form(title="   "), "inq-key-00000001")
    assert a.status_code == 422 and "title" in a.json()["fields"]
    b = create(world, form(body="   "), "inq-key-00000002")
    assert b.status_code == 422 and "body" in b.json()["fields"]
    assert create(world, form(title=""), "inq-key-00000003").status_code in (400, 422)
    assert create(world, form(title="가" * 101), "inq-key-00000004").status_code in (400, 422)
    assert create(world, form(body="가" * 2001), "inq-key-00000005").status_code in (400, 422)


def test_문의를_받지_않는_게시판이면_거절한다(world: World) -> None:
    category(world)
    as_member(world, person(world))
    assert create(world).status_code == 422  # 게시판이 없다
    bbs = board(world, "qna", MBR_WRT_YN="N")
    r = create(world, form(), "inq-key-00000002")
    assert r.status_code == 422 and "받지 않습니다" in r.json()["message"]
    world.db.execute(
        text("UPDATE TB_BBS SET MBR_WRT_YN='Y', USE_YN='N' WHERE BBS_SN=:b"), {"b": bbs["BBS_SN"]}
    )
    assert create(world, form(), "inq-key-00000003").status_code == 422
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST")[0]["n"] == 0


def test_CSRF_토큰이_없으면_쓰기를_거절한다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    mine = asked(world, qna, me, "내 글")
    as_member(world, me)
    for method, path in (
        ("POST", PATH),
        ("PUT", f"{PATH}/{mine['PST_SN']}"),
        ("DELETE", f"{PATH}/{mine['PST_SN']}"),
    ):
        r = world.client.request(
            method, f"{MEMBER}{path}", json=form(), headers={"Idempotency-Key": "inq-key-00000001"}
        )
        assert r.status_code == 403, method


# --- 수정·삭제 ----------------------------------------------------------------------------------


def test_답변_전의_내_문의는_고칠_수_있고_버전이_오르며_작업이력에_남는다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    category(world, "IQ.PAY", "결제", 2)
    me = person(world)
    mine = asked(world, qna, me, "처음", PST_CN="처음 본문", INQRY_CLSF_CD="IQ.COURSE")
    as_member(world, me)
    r = write(
        world,
        "PUT",
        f"{PATH}/{mine['PST_SN']}",
        form(categoryId="IQ.PAY", title="고침", body="고친 본문", isPrivate=True),
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["title"], out["body"], out["categoryId"], out["isPrivate"]) == (
        "고침",
        "고친 본문",
        "IQ.PAY",
        True,
    )
    row = rows(
        world,
        "SELECT PST_TTL t, PRVT_YN p, RCRD_VER v, MDFCN_DT d, REG_DT r FROM TB_PST WHERE PST_SN=:s",
        s=mine["PST_SN"],
    )[0]
    assert (row["t"], row["p"], int(row["v"])) == ("고침", "Y", int(mine["RCRD_VER"]) + 1)
    assert row["d"] is not None and row["r"] == mine["REG_DT"]
    [job] = rows(world, "SELECT MBR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='INQ_UPDATE'")
    assert (job["m"], job["c"]) == (me["MBR_SN"], "문의 수정")


def test_답변이_달린_문의는_고칠_수_없다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    mine = asked(world, qna, me, "처음", INQRY_CLSF_CD="IQ.COURSE")
    answered(world, mine)
    as_member(world, me)
    r = write(world, "PUT", f"{PATH}/{mine['PST_SN']}", form(title="고침"))
    assert r.status_code == 422 and r.json()["code"] == "RULE_REJECTED" and "답변" in r.json()["message"]
    assert rows(world, "SELECT PST_TTL t FROM TB_PST WHERE PST_SN=:s", s=mine["PST_SN"])[0]["t"] == "처음"


def test_수정도_분류와_제목_내용을_검사한다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    mine = asked(world, qna, me, "처음", INQRY_CLSF_CD="IQ.COURSE")
    as_member(world, me)
    path = f"{PATH}/{mine['PST_SN']}"
    assert "categoryId" in write(world, "PUT", path, form(categoryId="IQ.NONE")).json()["fields"]
    assert "title" in write(world, "PUT", path, form(title="  ")).json()["fields"]
    assert "body" in write(world, "PUT", path, form(body="  ")).json()["fields"]
    assert rows(world, "SELECT PST_TTL t FROM TB_PST WHERE PST_SN=:s", s=mine["PST_SN"])[0]["t"] == "처음"


def test_남의_문의는_공개_글이어도_고치거나_지울_수_없고_404다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me, other = person(world), person(world, "박다라")
    theirs = asked(world, qna, other, "남의 공개", INQRY_CLSF_CD="IQ.COURSE")
    as_member(world, me)
    path = f"{PATH}/{theirs['PST_SN']}"
    assert write(world, "PUT", path, form()).status_code == 404
    assert write(world, "DELETE", path).status_code == 404
    assert rows(world, "SELECT DEL_YN d, PST_TTL t FROM TB_PST WHERE PST_SN=:s", s=theirs["PST_SN"])[0] == {
        "d": "N",
        "t": "남의 공개",
    }


def test_지운_문의와_없는_문의는_수정과_삭제가_404다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    me = person(world)
    gone = asked(world, qna, me, "지움", DEL_YN="Y")
    as_member(world, me)
    for sn in (gone["PST_SN"], 999999999):
        assert write(world, "PUT", f"{PATH}/{sn}", form()).status_code == 404
        assert write(world, "DELETE", f"{PATH}/{sn}").status_code == 404
    assert write(world, "DELETE", f"{PATH}/abc").status_code in (400, 422)


def test_삭제는_논리_삭제이고_답변이_달려도_지울_수_있으며_다시_지우면_404다(
    world: World, qna: dict[str, Any]
) -> None:
    me = person(world)
    category(world)
    mine = asked(world, qna, me, "내 글", INQRY_CLSF_CD="IQ.COURSE")
    answered(world, mine)
    as_member(world, me)
    r = write(world, "DELETE", f"{PATH}/{mine['PST_SN']}")
    assert r.status_code == 204 and r.content == b""
    row = rows(world, "SELECT DEL_YN d, PST_TTL t, RCRD_VER v FROM TB_PST WHERE PST_SN=:s", s=mine["PST_SN"])[
        0
    ]
    assert (row["d"], row["t"], int(row["v"])) == ("Y", "내 글", int(mine["RCRD_VER"]) + 1)  # 행은 남는다
    assert (
        get(world, "/inquiries").json()["items"] == [] and get(world, "/me/inquiries").json()["items"] == []
    )
    assert get(world, f"/inquiries/{mine['PST_SN']}").status_code == 404
    assert write(world, "DELETE", f"{PATH}/{mine['PST_SN']}").status_code == 404
    [job] = rows(world, "SELECT MBR_SN m, TRGT_KEY_VL k FROM TB_JOB_HSTRY WHERE JOB_CD='INQ_DELETE'")
    assert (job["m"], job["k"]) == (me["MBR_SN"], str(mine["PST_SN"]))


# --- 관리자와 이어지는 흐름 ---------------------------------------------------------------------


def test_주민이_올린_문의를_그_동의_담당자가_답하면_주민에게_답변이_보인다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    my_dong, other_dong = dong(world, "가동"), dong(world, "나동")
    me = person(world, "홍길동", DONG_SN=my_dong["DONG_SN"])
    as_member(world, me)
    created = create(world, form(isPrivate=True)).json()
    use(world, staff(world, "other", "AU.POST_W", kind="SK.DONG", dong_sn=other_dong["DONG_SN"]))
    assert call(world, "GET", "/inquiries").json()["total"] == 0  # 다른 동 담당자는 보지 못한다
    use(world, staff(world, "owner", "AU.POST_W", kind="SK.DONG", dong_sn=my_dong["DONG_SN"]))
    listed = call(world, "GET", "/inquiries").json()["items"]
    assert [(i["inquiryId"], i["status"], i["isPrivate"]) for i in listed] == [
        (created["postId"], "RECEIVED", True)
    ]
    done = call(
        world,
        "PUT",
        f"/inquiries/{created['postId']}/answer",
        {"content": "확인했습니다", "version": 0, "relatedLink": "/center/contact"},
    )
    assert done.status_code == 200
    as_member(world, me)
    body = get(world, f"/inquiries/{created['postId']}").json()
    assert body["status"] == "ANSWERED" and body["canEdit"] is False
    assert body["answer"]["body"] == "확인했습니다\n\n관련 화면: /center/contact"
    assert write(world, "PUT", f"{PATH}/{created['postId']}", form()).status_code == 422
