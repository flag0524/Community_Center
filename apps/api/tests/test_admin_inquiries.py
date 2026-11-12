# 관리자 문의·답변(AU.POST_W, 한 단계 답변·수정 이력·버전 확인·링크 검증·범위·CSV)을 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin import inquiry_service
from tests.arena import Arena, Staff, parallel
from tests.arena import make_member as make_arena_member
from tests.factory import RowFactory
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board, post
from tests.world import START, World, make_member

pytestmark = pytest.mark.db


def category(
    w: World, code: str = "IQ.COURSE", name: str = "수강신청", seq: int = 1, **values: Any
) -> dict[str, Any]:
    return w.factory.make(
        "TB_COM_CD", COM_CD=code, CD_GROUP_ID="IQ", CD_NM=name, SORT_SEQ=seq, USE_YN="Y", **values
    )


def inquiry(
    w: World, bbs: dict[str, Any], title: str = "문의", who: str = "홍길동", **values: Any
) -> dict[str, Any]:
    member = make_member(w, f"m{title}"[:20], MBR_NM=who)
    return post(w, bbs, title, WRT_MBR_SN=member["MBR_SN"], WRT_MNGR_SN=None, **values)


def reply(w: World, original: dict[str, Any], content: str = "답변입니다", **values: Any) -> dict[str, Any]:
    return post(
        w,
        {"OPER_BNDL_SN": original["OPER_BNDL_SN"], "BBS_SN": original["BBS_SN"]},
        "답변",
        UP_PST_SN=original["PST_SN"],
        PST_TYPE_CD="PT.REPLY",
        PST_CN=content,
        **values,
    )


def answer(w: World, sn: Any, content: str = "답변 드립니다", version: int = 0, **values: Any) -> Any:
    return call(w, "PUT", f"/inquiries/{sn}/answer", {"content": content, "version": version, **values})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def csv_rows(response: Any) -> list[list[str]]:
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


@pytest.fixture
def qna(world: World) -> dict[str, Any]:
    return board(world, "qna", MBR_WRT_YN="Y", ANS_USE_YN="Y")


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/inquiries").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R"))
    for method, path, payload in (
        ("GET", "/inquiry-categories", None),
        ("GET", "/inquiries", None),
        ("GET", "/inquiries/export.csv", None),
        ("GET", "/inquiries/1", None),
        ("PUT", "/inquiries/1/answer", {"content": "x", "version": 0}),
    ):
        assert call(world, method, path, payload).status_code == 403, path


# --- 분류 ---------------------------------------------------------------------------------------


def test_분류는_공통코드_IQ에서_쓰는_것만_정렬_순서로_준다(world: World) -> None:
    category(world, "IQ.PAY", "결제", 2)
    category(world, "IQ.COURSE", "수강신청", 1)
    category(
        world,
        "IQ.OLD",
        "중지",
        3,
    )
    world.db.execute(text("UPDATE TB_COM_CD SET USE_YN='N' WHERE COM_CD='IQ.OLD'"))
    use(world, staff(world, "boss", "AU.POST_W"))
    assert call(world, "GET", "/inquiry-categories").json()["items"] == [
        {"id": "IQ.COURSE", "name": "수강신청"},
        {"id": "IQ.PAY", "name": "결제"},
    ]


def test_분류가_없으면_빈_목록이다(world: World) -> None:
    use(world, staff(world, "boss", "AU.POST_W"))
    assert call(world, "GET", "/inquiry-categories").json() == {"items": []}


# --- 목록 ---------------------------------------------------------------------------------------


def test_목록은_답변_대기가_먼저이고_각각_오래된_순이며_작성자를_가린다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world)
    day = timedelta(days=1)
    old_done = inquiry(world, qna, "오래된 완료", REG_DT=START - 5 * day, INQRY_CLSF_CD="IQ.COURSE")
    reply(world, old_done)
    new_wait = inquiry(world, qna, "새 대기", REG_DT=START - 1 * day)
    old_wait = inquiry(
        world, qna, "오래된 대기", REG_DT=START - 3 * day, PRVT_YN="Y", INQRY_CLSF_CD="IQ.COURSE"
    )
    use(world, staff(world, "boss", "AU.POST_W"))
    body = call(world, "GET", "/inquiries").json()
    assert [i["title"] for i in body["items"]] == ["오래된 대기", "새 대기", "오래된 완료"]
    by = {i["title"]: i for i in body["items"]}
    assert by["오래된 대기"]["status"] == "RECEIVED" and by["오래된 완료"]["status"] == "ANSWERED"
    assert by["오래된 대기"]["isPrivate"] is True and by["새 대기"]["isPrivate"] is False
    assert (by["오래된 완료"]["categoryName"], by["새 대기"]["categoryName"]) == ("수강신청", "")
    assert by["오래된 대기"]["authorName"] == "홍*동" and by["오래된 대기"]["receivedOn"] == "2026-11-06"
    assert {old_wait["PST_SN"], new_wait["PST_SN"]} and body["total"] == 3


def test_목록은_질문과_답변_게시판의_원글만_보이고_지운_글은_나오지_않는다(
    world: World, qna: dict[str, Any]
) -> None:
    notice = board(world, "notice")
    post(world, notice, "공지")
    inquiry(world, qna, "지운 문의", DEL_YN="Y")
    asked = inquiry(world, qna, "문의")
    reply(world, asked)
    reply(world, asked, DEL_YN="Y") if False else None
    use(world, staff(world, "boss", "AU.POST_W"))
    assert [i["title"] for i in call(world, "GET", "/inquiries").json()["items"]] == ["문의"]


def test_지운_답변은_답변으로_치지_않는다(world: World, qna: dict[str, Any]) -> None:
    asked = inquiry(world, qna, "문의")
    reply(world, asked, DEL_YN="Y")
    use(world, staff(world, "boss", "AU.POST_W"))
    assert call(world, "GET", "/inquiries").json()["items"][0]["status"] == "RECEIVED"
    assert call(world, "GET", f"/inquiries/{asked['PST_SN']}").json()["answer"] is None


def test_상태와_분류와_제목으로_거르고_쪽을_나눈다(world: World, qna: dict[str, Any]) -> None:
    category(world, "IQ.COURSE", "수강신청", 1)
    category(world, "IQ.PAY", "결제", 2)
    a = inquiry(world, qna, "수강 문의", INQRY_CLSF_CD="IQ.COURSE")
    inquiry(world, qna, "결제 문의", INQRY_CLSF_CD="IQ.PAY")
    reply(world, a)
    use(world, staff(world, "boss", "AU.POST_W"))

    def titles(qs: str) -> list[str]:
        return [i["title"] for i in call(world, "GET", f"/inquiries{qs}").json()["items"]]

    assert titles("?status=ANSWERED") == ["수강 문의"] and titles("?status=RECEIVED") == ["결제 문의"]
    assert titles("?categoryId=IQ.PAY") == ["결제 문의"]
    assert titles("?q=수강") == ["수강 문의"] and titles("?q=_") == []
    assert call(world, "GET", "/inquiries?categoryId=7").status_code in (400, 422)  # 코드 형식이 아니다
    assert [len(call(world, "GET", f"/inquiries?size=1&page={n}").json()["items"]) for n in (1, 2, 3)] == [
        1,
        1,
        0,
    ]


def test_동_담당자는_자기_동의_문의만_본다(world: World, qna: dict[str, Any]) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = inquiry(world, qna, "내 동", DONG_SN=a["DONG_SN"])
    other = inquiry(world, qna, "남의 동", DONG_SN=b["DONG_SN"])
    common = inquiry(world, qna, "공통")
    use(world, staff(world, "d", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [i["title"] for i in call(world, "GET", "/inquiries").json()["items"]] == ["내 동"]
    assert call(world, "GET", f"/inquiries/{mine['PST_SN']}").status_code == 200
    for hidden in (other, common):
        assert call(world, "GET", f"/inquiries/{hidden['PST_SN']}").status_code == 404
        assert answer(world, hidden["PST_SN"]).status_code == 404
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")[0]["n"] == 0


# --- 상세 ---------------------------------------------------------------------------------------


def test_상세는_본문과_답변과_링크와_이력을_준다(world: World, qna: dict[str, Any]) -> None:
    asked = inquiry(world, qna, "문의", PST_CN="질문 본문")
    use(world, staff(world, "boss", "AU.POST_W"))
    first = call(world, "GET", f"/inquiries/{asked['PST_SN']}").json()
    assert (first["content"], first["answer"], first["history"], first["canAnswer"]) == (
        "질문 본문",
        None,
        [],
        True,
    )
    assert (
        answer(world, asked["PST_SN"], "안내 드립니다", 0, relatedLink="/center/contact").status_code == 200
    )
    body = call(world, "GET", f"/inquiries/{asked['PST_SN']}").json()
    assert body["status"] == "ANSWERED"
    assert (body["answer"]["content"], body["answer"]["relatedLink"], body["answer"]["version"]) == (
        "안내 드립니다",
        "/center/contact",
        1,
    )
    assert (
        body["answer"]["answeredBy"] == "김관리"
        and body["answer"]["answeredAt"].endswith("Z")
        or "+" in body["answer"]["answeredAt"]
    )
    assert [h["action"] for h in body["history"]] == ["CREATED"] and body["history"][0]["by"] == "김관리"


def test_없는_문의와_질문이_아닌_글과_답변과_지운_글은_404다(world: World, qna: dict[str, Any]) -> None:
    other = post(world, board(world, "notice"), "공지")
    asked = inquiry(world, qna, "문의")
    gone = inquiry(world, qna, "지움", DEL_YN="Y")
    use(world, staff(world, "boss", "AU.POST_W"))
    rep = reply(world, asked)
    for sn in (other["PST_SN"], rep["PST_SN"], gone["PST_SN"], 999999999):
        assert call(world, "GET", f"/inquiries/{sn}").status_code == 404, sn
        assert answer(world, sn).status_code == 404, sn
    assert call(world, "GET", "/inquiries/abc").status_code in (400, 422)


# --- 답변 ---------------------------------------------------------------------------------------


def test_답변을_작성하면_원글_아래_한_단계_답변이_저장되고_공개범위와_분류를_따른다(
    world: World, qna: dict[str, Any]
) -> None:
    category(world, "IQ.PAY", "결제", 2)
    asked = inquiry(
        world, qna, "비공개 문의", PRVT_YN="Y", INQRY_CLSF_CD="IQ.PAY", DONG_SN=dong(world, "가동")["DONG_SN"]
    )
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    r = answer(world, asked["PST_SN"], "  확인했습니다  ", relatedLink="https://example.com/a")
    assert r.status_code == 200 and r.json()["answer"]["content"] == "확인했습니다"
    [row] = rows(world, "SELECT * FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")
    assert (
        row["UP_PST_SN"],
        row["BBS_SN"],
        row["PRVT_YN"],
        row["INQRY_CLSF_CD"],
        row["WRT_MNGR_SN"],
        row["WRT_MBR_SN"],
    ) == (
        asked["PST_SN"],
        asked["BBS_SN"],
        "Y",
        "IQ.PAY",
        boss.sn,
        None,
    )
    assert (row["DONG_SN"], row["DEL_YN"], int(row["RCRD_VER"])) == (asked["DONG_SN"], "N", 1)
    assert row["PST_CN"] == "확인했습니다\n\n관련 화면: https://example.com/a"
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='INQ_ANSWER'"
    )
    assert (job["m"], job["k"], job["c"]) == (boss.sn, str(asked["PST_SN"]), "답변 작성")


def test_답변을_고치면_같은_답변이_수정되고_이력이_쌓이며_답변은_한_단계다(
    world: World, qna: dict[str, Any]
) -> None:
    asked = inquiry(world, qna, "문의")
    first, second = staff(world, "a", "AU.POST_W"), staff(world, "b", "AU.POST_W")
    for who in (first, second):  # 담당자 이름을 로그인 아이디와 같게 해 구분한다
        world.db.execute(text("UPDATE TB_MNGR SET MNGR_NM=LGN_ID WHERE MNGR_SN=:s"), {"s": who.sn})
    use(world, first)
    answer(world, asked["PST_SN"], "처음", 0)
    use(world, second)
    r = answer(world, asked["PST_SN"], "고침", 1)
    assert r.status_code == 200
    out = r.json()
    assert (out["answer"]["content"], out["answer"]["version"], out["answer"]["answeredBy"]) == (
        "고침",
        2,
        "b",
    )
    assert [(h["action"], h["by"]) for h in out["history"]] == [("CREATED", "a"), ("EDITED", "b")]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")[0]["n"] == 1
    assert rows(world, "SELECT MDFCN_DT d FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")[0]["d"] is not None
    assert [
        j["c"]
        for j in rows(
            world, "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD LIKE 'INQ_ANSWER%' ORDER BY JOB_HSTRY_SN"
        )
    ] == [
        "답변 작성",
        "답변 수정",
    ]


def test_링크를_지우고_고치면_링크가_사라진다(world: World, qna: dict[str, Any]) -> None:
    asked = inquiry(world, qna, "문의")
    use(world, staff(world, "boss", "AU.POST_W"))
    answer(world, asked["PST_SN"], "처음", 0, relatedLink="/a")
    r = answer(world, asked["PST_SN"], "고침", 1)
    assert (
        r.json()["answer"]["relatedLink"] is None
        and rows(world, "SELECT PST_CN c FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")[0]["c"] == "고침"
    )


def test_읽은_버전이_다르면_409이고_답변을_바꾸지_않는다(world: World, qna: dict[str, Any]) -> None:
    asked = inquiry(world, qna, "문의")
    use(world, staff(world, "boss", "AU.POST_W"))
    stale = answer(world, asked["PST_SN"], "없는데 1", 1)  # 답변이 없는데 버전 1
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert answer(world, asked["PST_SN"], "처음", 0).status_code == 200
    for version in (0, 2):
        r = answer(world, asked["PST_SN"], "낡은 수정", version)
        assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert call(world, "GET", f"/inquiries/{asked['PST_SN']}").json()["answer"]["content"] == "처음"


@pytest.mark.parametrize(
    "link", ["http://example.com", "//evil.example", "javascript:alert(1)", "center/contact", "ftp://x", " "]
)
def test_관련_링크는_사이트_안_경로나_https만_받는다(world: World, qna: dict[str, Any], link: str) -> None:
    asked = inquiry(world, qna, "문의")
    use(world, staff(world, "boss", "AU.POST_W"))
    r = answer(world, asked["PST_SN"], "답변", 0, relatedLink=link)
    assert r.status_code == 422 and "relatedLink" in r.json()["fields"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_PST WHERE PST_TYPE_CD='PT.REPLY'")[0]["n"] == 0


def test_내용이_비면_거절하고_검증_오류는_기록하지_않는다(world: World, qna: dict[str, Any]) -> None:
    asked = inquiry(world, qna, "문의")
    use(world, staff(world, "boss", "AU.POST_W"))
    r = answer(world, asked["PST_SN"], "   ", 0)
    assert r.status_code == 422 and "content" in r.json()["fields"]
    assert answer(world, asked["PST_SN"], "", 0).status_code in (400, 422)
    assert call(world, "PUT", f"/inquiries/{asked['PST_SN']}/answer", {"content": "x"}).status_code in (
        400,
        422,
    )  # 버전 없음
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD LIKE 'INQ_ANSWER%'")[0]["n"] == 0


# --- CSV ----------------------------------------------------------------------------------------


def test_문의_CSV는_목록과_같은_조건이고_본문과_답변을_담지_않는다(world: World, qna: dict[str, Any]) -> None:
    category(world)
    a = inquiry(world, qna, "완료 문의", PST_CN="비밀 질문", INQRY_CLSF_CD="IQ.COURSE", REG_DT=START)
    reply(world, a, "비밀 답변")
    inquiry(world, qna, "대기 문의", PRVT_YN="Y", REG_DT=START - timedelta(days=1))
    boss = staff(world, "boss", "AU.POST_W")
    use(world, boss)
    r = call(world, "GET", "/inquiries/export.csv")
    table = csv_rows(r)
    assert table[0] == ["문의번호", "분류", "제목", "작성자", "공개 여부", "상태", "접수일"]
    assert [(row[2], row[4], row[5]) for row in table[1:]] == [
        ("대기 문의", "비공개", "RECEIVED"),
        ("완료 문의", "공개", "ANSWERED"),
    ]
    assert table[2][1] == "수강신청" and table[1][3] == "홍*동"
    assert "비밀 질문" not in r.text and "비밀 답변" not in r.text and "홍길동" not in r.text
    assert [row[2] for row in csv_rows(call(world, "GET", "/inquiries/export.csv?status=ANSWERED"))[1:]] == [
        "완료 문의"
    ]
    [first, *_] = rows(
        world,
        "SELECT MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT' ORDER BY JOB_HSTRY_SN",
    )
    assert (first["m"], first["t"], first["c"]) == (boss.sn, "TB_PST", "2건 내보냄(조건: 없음)")


def test_문의_CSV도_동_범위를_따른다(world: World, qna: dict[str, Any]) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    inquiry(world, qna, "내 동", DONG_SN=a["DONG_SN"])
    inquiry(world, qna, "남의 동", DONG_SN=b["DONG_SN"])
    use(world, staff(world, "d", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert [row[2] for row in csv_rows(call(world, "GET", "/inquiries/export.csv"))[1:]] == ["내 동"]


# --- 동시성 -------------------------------------------------------------------------------------


def test_여러_담당자가_같은_문의에_동시에_답해도_답변은_한_번만_만든다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = inquiry_service._load

    def slow(*args: Any) -> Any:
        found = real(*args)
        time.sleep(0.3)  # 읽은 뒤 잠그기 전의 틈을 넓혀 잠금이 없으면 겹치게 한다
        return found

    monkeypatch.setattr(inquiry_service, "_load", slow)

    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        bbs = f.make(
            "TB_BBS",
            OPER_BNDL_SN=bundle,
            BBS_ID="qna",
            BBS_NM="문의",
            BBS_TYPE_CD="BT.QNA",
            MBR_WRT_YN="Y",
            ANS_USE_YN="Y",
        )
        member = make_arena_member(f, bundle, "asker")
        asked = f.make(
            "TB_PST",
            OPER_BNDL_SN=bundle,
            BBS_SN=bbs["BBS_SN"],
            PST_TTL="문의",
            PST_CN="본문",
            WRT_MBR_SN=member,
            WRT_MNGR_SN=None,
        )
        return bundle, int(asked["PST_SN"])

    bundle, sn = arena.build(build)
    arena.serve(bundle)
    staffs = [arena.staff(bundle, f"s{n}", "AU.POST_W") for n in range(4)]

    def sender(s: Staff, n: int) -> Callable[[], Any]:
        return lambda: s.client.put(
            f"/api/admin/v1/inquiries/{sn}/answer",
            json={"content": f"답변 {n}", "version": 0},
            headers={"X-CSRF-Token": s.csrf},
        )

    codes = sorted(r.status_code for r in parallel([sender(s, n) for n, s in enumerate(staffs)]))
    assert codes == [200, 409, 409, 409], codes
    assert len(arena.query("SELECT 1 FROM TB_PST WHERE UP_PST_SN=:s AND PST_TYPE_CD='PT.REPLY'", s=sn)) == 1
