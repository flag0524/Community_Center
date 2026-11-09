# 읽기 게시판 목록·상세와 첨부 내려받기 판정을 실제 앱과 MariaDB로 확인하는 시험
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.core.config import get_settings
from app.db import tables
from tests.test_courses_public import course, cycle
from tests.test_site_public import publish as publish_content
from tests.world import MEMBER, START, World, make_admin, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
TYPES = {
    "notice": "BT.NOTICE",
    "news": "BT.NOTICE",
    "resources": "BT.DATA",
    "gallery": "BT.GALLERY",
    "faq": "BT.FAQ",
    "qna": "BT.QNA",
    "review": "BT.REVIEW",
}


def board(w: World, key: str = "notice", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "BBS_ID": key,
        "BBS_NM": key,
        "BBS_TYPE_CD": TYPES[key],
        "USE_YN": "Y",
        "ATCH_USE_YN": "Y",
    }
    return w.factory.make("TB_BBS", **{**defaults, **values})


def post(w: World, bbs: dict[str, Any], title: str = "제목", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": bbs["OPER_BNDL_SN"],
        "BBS_SN": bbs["BBS_SN"],
        "PST_TTL": title,
        "PST_CN": f"{title} 본문",
        "REG_DT": START - DAY,
    }
    return w.factory.make("TB_PST", **{**defaults, **values})


def get(w: World, path: str, **params: Any) -> Any:
    return w.client.get(f"{MEMBER}{path}", params=params)


def titles(w: World, key: str = "notice", **params: Any) -> list[str]:
    return [item["title"] for item in get(w, f"/boards/{key}/posts", **params).json()["items"]]


def stored_file(w: World, root: Path, content: bytes = b"hello", **values: Any) -> dict[str, Any]:
    """실제 파일을 저장소에 쓰고 그 객체키를 가진 파일 행을 만든다."""
    key = f"b{w.bundle}/{len(list(root.rglob('*')))}-object"
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    defaults: dict[str, Any] = {
        "STRG_KEY": key,
        "FILE_NM": "공지.pdf",
        "FILE_SZ": len(content),
        "MIME_TYPE_NM": "application/pdf",
        "FILE_USE_CD": "FP.ATTACH",
        "FILE_STTS_CD": "FS.SAFE",
    }
    return w.factory.make("TB_FILE", **{**defaults, **values})


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    """저장소 위치를 시험용 임시 폴더로 바꾼다."""
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


# --- 목록: 공개 범위 -----------------------------------------------------------------


def test_게시판_목록은_그_게시판의_공개_글만_준다(world: World) -> None:
    notice, news = board(world, "notice"), board(world, "news")
    post(world, notice, "공지1")
    post(world, news, "소식1")
    assert titles(world, "notice") == ["공지1"] and titles(world, "news") == ["소식1"]


@pytest.mark.parametrize(
    "values",
    [
        {"DEL_YN": "Y"},
        {"PRVT_YN": "Y"},
        {"PSTG_BGNG_DT": START + timedelta(seconds=1)},
        {"PSTG_END_DT": START},
    ],
    ids=["삭제", "비공개", "게시_시작_전", "게시_종료"],
)
def test_숨겨야_하는_글은_목록에_없다(world: World, values: dict[str, Any]) -> None:
    bbs = board(world)
    post(world, bbs, "보이는글")
    post(world, bbs, "숨는글", **values)
    assert titles(world) == ["보이는글"]
    assert get(world, "/boards/notice/posts").json()["total"] == 1


def test_게시_시작_정각과_종료_직전은_보인다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "시작정각", PSTG_BGNG_DT=START)
    post(world, bbs, "종료직전", PSTG_END_DT=START + timedelta(seconds=1))
    assert sorted(titles(world)) == ["시작정각", "종료직전"]


def test_답변은_목록에_나오지_않는다(world: World) -> None:
    bbs = board(world)
    parent = post(world, bbs, "원글")
    post(world, bbs, "답변", UP_PST_SN=parent["PST_SN"], PST_TYPE_CD="PT.REPLY")
    assert titles(world) == ["원글"]


def test_없거나_쓰지_않는_게시판은_404다(world: World) -> None:
    assert get(world, "/boards/notice/posts").status_code == 404
    board(world, "notice", USE_YN="N")
    assert get(world, "/boards/notice/posts").status_code == 404


def test_질문과_답변_수강후기는_이_엔드포인트로_열지_않는다(world: World) -> None:
    for key in ("qna", "review"):
        bbs = board(world, key)
        post(world, bbs, "남의 글")
        assert get(world, f"/boards/{key}/posts").status_code == 404


def test_다른_운영묶음의_게시판과_글은_보이지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs = board(world, "notice", OPER_BNDL_SN=other)
    post(world, theirs, "남의 공지")
    assert get(world, "/boards/notice/posts").status_code == 404
    mine = board(world, "notice")
    assert titles(world) == []
    post(world, mine, "우리 공지")
    assert titles(world) == ["우리 공지"]


def test_알_수_없는_게시판_키는_400이다(world: World) -> None:
    assert get(world, "/boards/nope/posts").status_code == 400


# --- 목록: 순서·검색·쪽 ---------------------------------------------------------------


def test_상단공지가_먼저이고_그다음_게시일_내림차순이다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "오래된 글", REG_DT=START - 5 * DAY)
    post(world, bbs, "최근 글", REG_DT=START - 1 * DAY)
    post(world, bbs, "오래된 상단", NTC_YN="Y", REG_DT=START - 9 * DAY)
    post(world, bbs, "최근 상단", NTC_YN="Y", REG_DT=START - 2 * DAY)
    assert titles(world) == ["최근 상단", "오래된 상단", "최근 글", "오래된 글"]


def test_게시_시작_시각이_있으면_그것이_게시일이다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "예약글", REG_DT=START - 9 * DAY, PSTG_BGNG_DT=START - 1 * DAY)
    post(world, bbs, "일반글", REG_DT=START - 3 * DAY)
    items = get(world, "/boards/notice/posts").json()["items"]
    assert [i["title"] for i in items] == ["예약글", "일반글"]
    assert items[0]["publishedAt"].startswith("2026-11-08T09:00:00")  # 게시 시작 시각
    assert items[1]["publishedAt"].startswith("2026-11-06T09:00:00")  # 등록 시각


def test_같은_시각의_글은_번호가_큰_것이_먼저다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "먼저", REG_DT=START - DAY)
    post(world, bbs, "나중", REG_DT=START - DAY)
    assert titles(world) == ["나중", "먼저"]


def test_제목_검색은_공백을_자르고_퍼센트와_밑줄을_글자로_본다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "수강 안내")
    post(world, bbs, "100% 환불")
    post(world, bbs, "a_b")
    assert titles(world, q="  수강  ") == ["수강 안내"]
    assert titles(world, q="%") == ["100% 환불"]
    assert titles(world, q="_") == ["a_b"]
    assert len(titles(world, q="   ")) == 3


def test_본문에만_있는_말은_제목_검색에_걸리지_않는다(world: World) -> None:
    bbs = board(world)
    post(world, bbs, "제목", PST_CN="비밀단어")
    assert titles(world, q="비밀단어") == []


def test_쪽_나누기와_전체_건수(world: World) -> None:
    bbs = board(world)
    for index in range(5):
        post(world, bbs, f"글{index}", REG_DT=START - (index + 1) * DAY)
    body = get(world, "/boards/notice/posts", size=2, page=2).json()
    assert [i["title"] for i in body["items"]] == ["글2", "글3"]
    assert body["total"] == 5 and (body["page"], body["size"]) == (2, 2)
    assert get(world, "/boards/notice/posts", size=2, page=4).json()["items"] == []
    assert len(get(world, "/boards/notice/posts").json()["items"]) == 5
    for params in ({"page": 0}, {"size": 0}, {"size": 51}):
        assert get(world, "/boards/notice/posts", **params).status_code == 400


# --- 목록: 게시판 유형별 요약 -------------------------------------------------------------


def test_자주하는_질문만_목록에_본문을_담는다(world: World) -> None:
    faq, notice = board(world, "faq"), board(world, "notice")
    post(world, faq, "질문", PST_CN="답입니다")
    post(world, notice, "공지", PST_CN="공지 본문")
    assert get(world, "/boards/faq/posts").json()["items"][0]["body"] == "답입니다"
    assert get(world, "/boards/notice/posts").json()["items"][0]["body"] is None


def test_자료실은_첫_첨부를_갤러리는_첫_이미지를_담는다(world: World, root: Path) -> None:
    res, gal = board(world, "resources"), board(world, "gallery")
    data = post(world, res, "자료")
    stored_file(world, root, PST_SN=data["PST_SN"], FILE_NM="뒤.pdf", SORT_SEQ=2)
    first = stored_file(world, root, PST_SN=data["PST_SN"], FILE_NM="앞.pdf", SORT_SEQ=1, FILE_SZ=77)
    stored_file(
        world, root, PST_SN=data["PST_SN"], FILE_NM="미검사.pdf", FILE_STTS_CD="FS.PENDING", SORT_SEQ=0
    )
    stored_file(world, root, PST_SN=data["PST_SN"], FILE_NM="그림.png", FILE_USE_CD="FP.IMAGE", SORT_SEQ=0)
    picture = post(world, gal, "사진")
    img = stored_file(world, root, PST_SN=picture["PST_SN"], FILE_USE_CD="FP.IMAGE", MIME_TYPE_NM="image/png")
    stored_file(
        world, root, PST_SN=picture["PST_SN"], FILE_NM="문서.pdf"
    )  # 이미지가 아닌 첨부는 대표 이미지가 아니다
    res_item = get(world, "/boards/resources/posts").json()["items"][0]
    assert res_item["primaryFile"] == {
        "fileId": str(first["FILE_SN"]),
        "name": "앞.pdf",
        "sizeBytes": 77,
        "contentType": "application/pdf",
    }
    assert res_item["thumbnail"] is None
    gal_item = get(world, "/boards/gallery/posts").json()["items"][0]
    assert gal_item["thumbnail"] == {"fileId": str(img["FILE_SN"]), "alt": "사진"}
    assert gal_item["primaryFile"] is None


def test_첨부를_끈_게시판은_목록에_파일을_담지_않는다(world: World, root: Path) -> None:
    res = board(world, "resources", ATCH_USE_YN="N")
    data = post(world, res, "자료")
    stored_file(world, root, PST_SN=data["PST_SN"])
    assert get(world, "/boards/resources/posts").json()["items"][0]["primaryFile"] is None


def test_다른_글의_첨부는_섞이지_않는다(world: World, root: Path) -> None:
    res = board(world, "resources")
    a, b = post(world, res, "가", REG_DT=START - DAY), post(world, res, "나", REG_DT=START - 2 * DAY)
    stored_file(world, root, PST_SN=a["PST_SN"], FILE_NM="가.pdf")
    items = {i["title"]: i for i in get(world, "/boards/resources/posts").json()["items"]}
    assert items["가"]["primaryFile"]["name"] == "가.pdf" and items["나"]["primaryFile"] is None
    assert b["PST_SN"] != a["PST_SN"]


# --- 상세 ----------------------------------------------------------------------------


def test_상세는_본문과_첨부_이미지를_나누어_준다(world: World, root: Path) -> None:
    bbs = board(world, "news")
    row = post(world, bbs, "소식", PST_CN="첫 문단\n\n둘째 문단", NTC_YN="Y")
    doc = stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="안내.pdf", FILE_SZ=10)
    img = stored_file(world, root, PST_SN=row["PST_SN"], FILE_USE_CD="FP.IMAGE", MIME_TYPE_NM="image/png")
    stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="검사중.pdf", FILE_STTS_CD="FS.PENDING")
    stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="차단.pdf", FILE_STTS_CD="FS.BLOCK")
    body = get(world, f"/posts/{row['PST_SN']}").json()
    assert body["postId"] == str(row["PST_SN"]) and body["board"] == "news" and body["title"] == "소식"
    assert body["body"] == "첫 문단\n\n둘째 문단" and body["pinned"] is True and body["facts"] == []
    assert [a["fileId"] for a in body["attachments"]] == [str(doc["FILE_SN"])]
    assert body["attachments"][0]["sizeBytes"] == 10
    assert body["images"] == [{"fileId": str(img["FILE_SN"]), "alt": "소식"}]


def test_첨부는_정렬_순서_다음_번호_순으로_준다(world: World, root: Path) -> None:
    row = post(world, board(world, "news"), "소식")
    stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="c.pdf", SORT_SEQ=2)
    stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="b.pdf", SORT_SEQ=1)
    stored_file(world, root, PST_SN=row["PST_SN"], FILE_NM="a.pdf", SORT_SEQ=1)
    attachments = get(world, f"/posts/{row['PST_SN']}").json()["attachments"]
    assert [a["name"] for a in attachments] == ["b.pdf", "a.pdf", "c.pdf"]


def test_첨부를_끈_게시판의_상세에는_파일이_없다(world: World, root: Path) -> None:
    bbs = board(world, "news", ATCH_USE_YN="N")
    row = post(world, bbs, "소식")
    stored_file(world, root, PST_SN=row["PST_SN"])
    body = get(world, f"/posts/{row['PST_SN']}").json()
    assert body["attachments"] == [] and body["images"] == []


@pytest.mark.parametrize(
    "values",
    [
        {"DEL_YN": "Y"},
        {"PRVT_YN": "Y"},
        {"PSTG_END_DT": START},
        {"PSTG_BGNG_DT": START + DAY},
    ],
    ids=["삭제", "비공개", "게시_종료", "게시_시작_전"],
)
def test_숨겨야_하는_글의_상세는_404다(world: World, values: dict[str, Any]) -> None:
    row = post(world, board(world), "숨김", **values)
    assert get(world, f"/posts/{row['PST_SN']}").status_code == 404


def test_답변_질문게시판_후기_꺼진_게시판_다른_묶음의_글은_상세도_404다(world: World) -> None:
    bbs = board(world)
    parent = post(world, bbs, "원글")
    answer = post(world, bbs, "답변", UP_PST_SN=parent["PST_SN"], PST_TYPE_CD="PT.REPLY")
    qna = post(world, board(world, "qna"), "문의")
    review = post(world, board(world, "review"), "후기")
    off = post(world, board(world, "faq", USE_YN="N"), "꺼짐")
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs = post(world, board(world, "news", OPER_BNDL_SN=other), "남의 글")
    for row in (answer, qna, review, off, theirs):
        assert get(world, f"/posts/{row['PST_SN']}").status_code == 404
    assert get(world, f"/posts/{parent['PST_SN']}").status_code == 200
    assert get(world, "/posts/999999999").status_code == 404
    assert get(world, "/posts/abc").status_code == 400


# --- 첨부 내려받기 ---------------------------------------------------------------------


def download(w: World, file_row: dict[str, Any]) -> Any:
    return get(w, f"/files/{file_row['FILE_SN']}")


def test_공개_글의_첨부는_내용과_안전한_머리글로_내려_준다(world: World, root: Path) -> None:
    row = post(world, board(world, "resources"), "자료")
    file = stored_file(world, root, b"%PDF-1", PST_SN=row["PST_SN"], FILE_NM="안내 문서.pdf")
    response = download(world, file)
    assert response.status_code == 200 and response.content == b"%PDF-1"
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == "attachment; filename*=UTF-8''%EC%95%88%EB%82%B4%20%EB%AC%B8%EC%84%9C.pdf"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_이미지는_화면에_바로_보이게_내려_주고_이미지가_아닌_것은_내려받기로_준다(
    world: World, root: Path
) -> None:
    row = post(world, board(world, "gallery"), "사진")
    png = stored_file(
        world, root, b"PNG", PST_SN=row["PST_SN"], FILE_USE_CD="FP.IMAGE", MIME_TYPE_NM="image/png"
    )
    fake = stored_file(
        world,
        root,
        b"<html>",
        PST_SN=row["PST_SN"],
        FILE_USE_CD="FP.IMAGE",
        MIME_TYPE_NM="text/html",
        FILE_NM="x.png",
    )
    assert download(world, png).headers["content-disposition"].startswith("inline;")
    assert (
        download(world, fake).headers["content-disposition"].startswith("attachment;")
    )  # 이미지를 가장한 문서


@pytest.mark.parametrize(
    "values",
    [
        {"DEL_YN": "Y"},
        {"PRVT_YN": "Y"},
        {"PSTG_END_DT": START},
        {"PSTG_BGNG_DT": START + DAY},
    ],
    ids=["삭제", "비공개", "게시_종료", "게시_시작_전"],
)
def test_글이_숨겨지면_첨부도_바로_막힌다(world: World, root: Path, values: dict[str, Any]) -> None:
    row = post(world, board(world, "resources"), "자료")
    file = stored_file(world, root, PST_SN=row["PST_SN"])
    assert download(world, file).status_code == 200
    world.db.execute(tables.TB_PST.update().where(tables.TB_PST.c.PST_SN == row["PST_SN"]).values(**values))
    assert download(world, file).status_code == 404


def test_검사를_통과하지_못한_파일과_허용하지_않은_용도는_404다(world: World, root: Path) -> None:
    row = post(world, board(world, "resources"), "자료")
    for status in ("FS.PENDING", "FS.BLOCK", "FS.DELETE"):
        assert (
            download(world, stored_file(world, root, PST_SN=row["PST_SN"], FILE_STTS_CD=status)).status_code
            == 404
        )
    assert (
        download(world, stored_file(world, root, PST_SN=row["PST_SN"], FILE_USE_CD="FP.PROOF")).status_code
        == 404
    )


def test_첨부를_끈_게시판_질문게시판_다른_묶음의_첨부는_404다(world: World, root: Path) -> None:
    off = post(world, board(world, "resources", ATCH_USE_YN="N"), "끔")
    qna = post(world, board(world, "qna"), "문의")
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs = post(world, board(world, "news", OPER_BNDL_SN=other), "남의 글")
    for owner in (off, qna):
        assert download(world, stored_file(world, root, PST_SN=owner["PST_SN"])).status_code == 404
    foreign = stored_file(world, root, OPER_BNDL_SN=other, PST_SN=theirs["PST_SN"])
    assert download(world, foreign).status_code == 404


def test_홈_콘텐츠의_이미지는_게시_중일_때만_내려_준다(world: World, root: Path) -> None:
    banner = publish_content(world, "CT.BANNER", "b1", "본문")
    file = stored_file(
        world,
        root,
        b"IMG",
        SITE_CONTS_SN=banner["SITE_CONTS_SN"],
        FILE_USE_CD="FP.IMAGE",
        MIME_TYPE_NM="image/jpeg",
    )
    assert download(world, file).status_code == 200
    ended = publish_content(world, "CT.POPUP", "p1", "본문", PSTG_END_DT=START)
    assert (
        download(
            world, stored_file(world, root, SITE_CONTS_SN=ended["SITE_CONTS_SN"], FILE_USE_CD="FP.IMAGE")
        ).status_code
        == 404
    )
    off = publish_content(world, "CT.POPUP", "p2", "본문", PSTG_YN="N")
    assert (
        download(
            world, stored_file(world, root, SITE_CONTS_SN=off["SITE_CONTS_SN"], FILE_USE_CD="FP.IMAGE")
        ).status_code
        == 404
    )


def test_홈_콘텐츠_중_배너와_팝업_밖이나_이미지_아닌_첨부는_404다(world: World, root: Path) -> None:
    terms = publish_content(world, "CT.TERMS", "terms", "본문")
    assert (
        download(
            world, stored_file(world, root, SITE_CONTS_SN=terms["SITE_CONTS_SN"], FILE_USE_CD="FP.IMAGE")
        ).status_code
        == 404
    )
    banner = publish_content(world, "CT.BANNER", "b1", "본문")
    assert download(world, stored_file(world, root, SITE_CONTS_SN=banner["SITE_CONTS_SN"])).status_code == 404


def test_공개_강좌의_강의계획서는_내려_주고_작성중_강좌는_막는다(world: World, root: Path) -> None:
    cyc = cycle(world)
    open_course, draft = course(world, cyc, "열림"), course(world, cyc, "작성중", CORS_STTS_CD="CS.DRAFT")
    plan = stored_file(world, root, b"PLAN", CORS_SN=open_course["CORS_SN"], FILE_USE_CD="FP.PLAN")
    assert download(world, plan).content == b"PLAN"
    hidden = stored_file(world, root, CORS_SN=draft["CORS_SN"], FILE_USE_CD="FP.PLAN")
    assert download(world, hidden).status_code == 404
    other = stored_file(world, root, CORS_SN=open_course["CORS_SN"], FILE_USE_CD="FP.ATTACH")
    assert download(world, other).status_code == 404  # 계획서 용도가 아니다


def test_그_밖의_소유자의_파일은_모두_비공개다(world: World, root: Path) -> None:
    member = make_member(world, "owner")
    instr = world.factory.make(
        "TB_INSTR",
        MBR_SN=member["MBR_SN"],
        INSTR_STTS_CD="IS.APPROVE",
        RLS_YN="Y",
        APRV_DT=START,
        APRV_MNGR_SN=make_admin(world)["MNGR_SN"],
    )
    assert download(world, stored_file(world, root, INSTR_SN=instr["INSTR_SN"])).status_code == 404


def test_없는_파일과_형식이_틀린_번호(world: World, root: Path) -> None:
    assert get(world, "/files/99999999").status_code == 404
    assert get(world, "/files/abc").status_code == 400


def test_저장소에_파일이_없으면_500이고_경로를_알리지_않는다(world: World, root: Path) -> None:
    row = post(world, board(world, "resources"), "자료")
    file = stored_file(world, root, PST_SN=row["PST_SN"])
    (root / file["STRG_KEY"]).unlink()
    response = download(world, file)
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert str(root) not in response.text


def test_저장소_밖을_가리키는_키는_읽지_않는다(
    world: World, root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    secret = tmp_path_factory.mktemp("secret") / "secret.txt"
    secret.write_text("비밀")
    row = post(world, board(world, "resources"), "자료")
    file = stored_file(world, root, PST_SN=row["PST_SN"], STRG_KEY=f"../{secret.parent.name}/secret.txt")
    assert download(world, file).status_code == 500
