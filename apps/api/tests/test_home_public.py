# 홈 화면 응답(기준 기수, 분야별 접수 현황, 공지, 배너·팝업)을 실제 앱과 MariaDB로 확인하는 시험
from datetime import timedelta
from typing import Any

import pytest

from tests.test_board_public import board, post
from tests.test_courses_public import course, cycle
from tests.test_site_public import publish as publish_content
from tests.world import MEMBER, START, World, make_admin

pytestmark = pytest.mark.db

DAY = timedelta(days=1)


def home(w: World) -> Any:
    response = w.client.get(f"{MEMBER}/home")
    assert response.status_code == 200
    return response.json()


def category(w: World, name: str, order: int = 0, **values: Any) -> dict[str, Any]:
    admin = make_admin(w, f"adm-{name}")["MNGR_SN"]
    return w.factory.make(
        "TB_CORS_CLSF", CORS_CLSF_NM=name, CLSF_NM_KEY=name, SORT_SEQ=order, REG_MNGR_SN=admin, **values
    )


def banner_image(w: World, content: dict[str, Any], **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "SITE_CONTS_SN": content["SITE_CONTS_SN"],
        "FILE_USE_CD": "FP.IMAGE",
        "FILE_STTS_CD": "FS.SAFE",
        "MIME_TYPE_NM": "image/png",
        "FILE_NM": "배너.png",
        "FILE_SZ": 10,
    }
    return w.factory.make("TB_FILE", **{**defaults, **values})


def test_아무것도_없으면_빈_홈이다(world: World) -> None:
    body = home(world)
    assert body["cycle"] is None and body["categories"] == [] and body["notices"] == []
    assert body["banners"] == [] and body["popups"] == [] and body["visual"] is None
    assert body["serverNow"].startswith("2026-11-09T09:00:00")


def test_기준_기수는_강좌_목록과_같다(world: World) -> None:
    cycle(world, "이번 기수")
    info = home(world)["cycle"]
    assert info["name"] == "이번 기수" and info["receptionState"] == "OPEN"
    assert info["educationStart"] == "2026-11-01" and info["educationEnd"] == "2026-12-31"
    listed = world.client.get(f"{MEMBER}/courses").json()["criteria"]["cycle"]
    assert info == listed


# --- 분야별 접수 현황 ------------------------------------------------------------------


def test_분야마다_접수_상태와_기간_강좌명_세_개를_모은다(world: World) -> None:
    cyc = cycle(world)
    health, art = category(world, "건강", 1), category(world, "문화", 2)
    for index in range(1, 5):
        course(world, cyc, f"건강{index}", CORS_CLSF_SN=health["CORS_CLSF_SN"])
    course(world, cyc, "서예", CORS_CLSF_SN=art["CORS_CLSF_SN"])
    cards = home(world)["categories"]
    assert [c["category"]["name"] for c in cards] == ["건강", "문화"]  # 정렬 순서
    assert cards[0]["courseNames"] == ["건강1", "건강2", "건강3"]  # 앞 세 개
    assert cards[1]["courseNames"] == ["서예"]
    assert cards[0]["category"]["categoryId"] == str(health["CORS_CLSF_SN"])
    assert cards[0]["receptionState"] == "OPEN"


def test_분야의_접수_상태는_접수중_예정_마감_순으로_우선한다(world: World) -> None:
    cyc = cycle(world)
    a, b, c = category(world, "가", 1), category(world, "나", 2), category(world, "다", 3)
    ahead = {"RCPT_BGNG_DT": START + DAY, "RCPT_END_DT": START + 3 * DAY}
    done = {"RCPT_BGNG_DT": START - 5 * DAY, "RCPT_END_DT": START - DAY}
    course(world, cyc, "가-마감", CORS_CLSF_SN=a["CORS_CLSF_SN"], **done)
    course(world, cyc, "가-예정", CORS_CLSF_SN=a["CORS_CLSF_SN"], **ahead)
    course(world, cyc, "가-접수", CORS_CLSF_SN=a["CORS_CLSF_SN"])
    course(world, cyc, "나-마감", CORS_CLSF_SN=b["CORS_CLSF_SN"], **done)
    course(world, cyc, "나-예정", CORS_CLSF_SN=b["CORS_CLSF_SN"], **ahead)
    course(world, cyc, "다-마감", CORS_CLSF_SN=c["CORS_CLSF_SN"], **done)
    states = {card["category"]["name"]: card["receptionState"] for card in home(world)["categories"]}
    assert states == {"가": "OPEN", "나": "UPCOMING", "다": "CLOSED"}


def test_분야의_접수_기간과_교육_기간은_강좌들의_가장_이른_시작과_가장_늦은_끝이다(world: World) -> None:
    cyc = cycle(world)
    health = category(world, "건강")
    course(
        world, cyc, "일찍", CORS_CLSF_SN=health["CORS_CLSF_SN"],
        RCPT_BGNG_DT=START - 6 * DAY, RCPT_END_DT=START + 2 * DAY, EDU_BGNG_YMD="20261105", EDU_END_YMD="20261220",
    )  # fmt: skip
    course(
        world, cyc, "늦게", CORS_CLSF_SN=health["CORS_CLSF_SN"],
        RCPT_BGNG_DT=START - 2 * DAY, RCPT_END_DT=START + 7 * DAY, EDU_BGNG_YMD="20261110", EDU_END_YMD="20261230",
    )  # fmt: skip
    card = home(world)["categories"][0]
    assert card["receptionStart"].startswith("2026-11-03T09:00:00") and card["receptionEnd"].startswith(
        "2026-11-16T09:00:00"
    )
    assert card["educationStart"] == "2026-11-05" and card["educationEnd"] == "2026-12-30"


def test_보이지_않는_강좌_분류_없는_강좌_쓰지_않는_분류_다른_기수는_카드에_들어가지_않는다(
    world: World,
) -> None:
    cyc = cycle(world)
    later = cycle(world, "다음", EDU_CYCL=5, EDU_YR="2027", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331")
    shown, stopped, deleted = (
        category(world, "보임", 1),
        category(world, "중지", 2, USE_YN="N"),
        category(world, "삭제", 3, DEL_YN="Y"),
    )
    course(world, cyc, "보이는강좌", CORS_CLSF_SN=shown["CORS_CLSF_SN"])
    course(world, cyc, "작성중", CORS_CLSF_SN=shown["CORS_CLSF_SN"], CORS_STTS_CD="CS.DRAFT")
    course(world, cyc, "폐강", CORS_CLSF_SN=shown["CORS_CLSF_SN"], CORS_STTS_CD="CS.CANCEL")
    course(world, cyc, "분류없음")
    course(world, cyc, "중지분류", CORS_CLSF_SN=stopped["CORS_CLSF_SN"])
    course(world, cyc, "삭제분류", CORS_CLSF_SN=deleted["CORS_CLSF_SN"])
    course(
        world,
        later,
        "다음기수강좌",
        CORS_CLSF_SN=shown["CORS_CLSF_SN"],
        EDU_BGNG_YMD="20270101",
        EDU_END_YMD="20270331",
    )
    cards = home(world)["categories"]
    assert [(c["category"]["name"], c["courseNames"]) for c in cards] == [("보임", ["보이는강좌"])]


def test_다른_운영묶음의_강좌는_카드에_들어가지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs = cycle(world, "남의 기수", OPER_BNDL_SN=other)
    theirs_category = category(world, "남의분류", OPER_BNDL_SN=other)
    course(world, theirs, "남의 강좌", OPER_BNDL_SN=other, CORS_CLSF_SN=theirs_category["CORS_CLSF_SN"])
    cycle(world, "우리 기수")
    assert home(world)["categories"] == []


# --- 공지 -----------------------------------------------------------------------------


def test_공지는_공지사항_게시판의_공개_글만_상단공지부터_다섯_개다(world: World) -> None:
    notice, news = board(world, "notice"), board(world, "news")
    for index in range(1, 7):
        post(world, notice, f"일반{index}", REG_DT=START - index * DAY)
    post(world, notice, "상단", NTC_YN="Y", REG_DT=START - 30 * DAY)
    post(world, notice, "비공개", PRVT_YN="Y", NTC_YN="Y")
    post(world, news, "소식")
    notices = home(world)["notices"]
    assert [n["title"] for n in notices] == ["상단", "일반1", "일반2", "일반3", "일반4"]
    assert notices[0]["pinned"] is True and notices[1]["pinned"] is False
    assert notices[0]["postId"] and notices[1]["publishedAt"].startswith("2026-11-08T09:00:00")


# --- 배너와 팝업 -----------------------------------------------------------------------


def test_배너는_게시_중인_것만_정렬_순서대로_이미지와_함께_준다(world: World) -> None:
    second = publish_content(world, "CT.BANNER", "b2", "", CONTS_TTL="둘째", SORT_SEQ=2, URL_ADDR="/courses")
    first = publish_content(
        world, "CT.BANNER", "b1", "", CONTS_TTL="첫째", SORT_SEQ=1, URL_ADDR="https://www.paju.go.kr"
    )
    publish_content(world, "CT.BANNER", "b3", "", CONTS_TTL="종료", PSTG_END_DT=START)
    publish_content(world, "CT.BANNER", "b4", "", CONTS_TTL="미게시", PSTG_YN="N")
    publish_content(
        world, "CT.BANNER", "b5", "", CONTS_TTL="시작전", PSTG_BGNG_DT=START + timedelta(seconds=1)
    )
    image = banner_image(world, first)
    banners = home(world)["banners"]
    assert [b["title"] for b in banners] == ["첫째", "둘째"]
    assert banners[0]["contentId"] == str(first["SITE_CONTS_SN"]) and banners[1]["contentId"] == str(
        second["SITE_CONTS_SN"]
    )
    assert banners[0]["linkUrl"] == "https://www.paju.go.kr" and banners[1]["linkUrl"] == "/courses"
    assert banners[0]["image"] == {"url": f"/api/v1/files/{image['FILE_SN']}", "alt": "첫째"}
    assert banners[1]["image"] is None


def test_홈이_알려_준_이미지_주소로_실제로_내려받을_수_있다(world: World, tmp_path: Any) -> None:
    from dataclasses import replace

    from app.core.config import get_settings

    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    content = publish_content(world, "CT.BANNER", "b1", "", CONTS_TTL="배너")
    (tmp_path / "k").write_bytes(b"IMG")
    banner_image(world, content, STRG_KEY="k")
    url = home(world)["banners"][0]["image"]["url"]
    response = world.client.get(url)
    assert response.status_code == 200 and response.content == b"IMG"


def test_같은_콘텐츠의_여러_버전_중_가장_늦게_만든_게시본만_나간다(world: World) -> None:
    publish_content(world, "CT.BANNER", "b1", "", CONTS_TTL="옛 버전", VER_NM="v1")
    publish_content(world, "CT.BANNER", "b1", "", CONTS_TTL="새 버전", VER_NM="v2")
    assert [b["title"] for b in home(world)["banners"]] == ["새 버전"]


def test_이미지는_검사를_통과한_첫_이미지만_쓰고_이미지_아닌_용도는_쓰지_않는다(world: World) -> None:
    content = publish_content(world, "CT.BANNER", "b1", "", CONTS_TTL="배너")
    banner_image(world, content, FILE_STTS_CD="FS.PENDING", SORT_SEQ=0)
    banner_image(world, content, FILE_USE_CD="FP.ATTACH", SORT_SEQ=0)
    second = banner_image(world, content, SORT_SEQ=2)
    first = banner_image(world, content, SORT_SEQ=1)
    banner_image(world, content, SORT_SEQ=1)  # 정렬 순서가 같으면 번호가 작은 것이 먼저다
    assert home(world)["banners"][0]["image"]["url"] == f"/api/v1/files/{first['FILE_SN']}"
    assert second["FILE_SN"] != first["FILE_SN"]


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("/courses", "/courses"),
        ("https://www.paju.go.kr/a?b=1", "https://www.paju.go.kr/a?b=1"),
        ("  /guide/apply  ", "/guide/apply"),
        ("javascript:alert(1)", None),
        ("http://insecure.example", None),
        ("//evil.example/x", None),
        ("data:text/html,x", None),
        ("https://", None),
        ("courses", None),
        ("", None),
        (None, None),
    ],
)
def test_링크는_사이트_안_경로나_https_주소만_내보낸다(
    world: World, stored: str | None, expected: str | None
) -> None:
    publish_content(world, "CT.BANNER", "b1", "", URL_ADDR=stored)
    publish_content(world, "CT.POPUP", "p1", "본문", URL_ADDR=stored)
    body = home(world)
    assert body["banners"][0]["linkUrl"] == expected and body["popups"][0]["linkUrl"] == expected


def test_팝업은_본문과_이미지를_주고_본문이_공백이면_null이다(world: World) -> None:
    shown = publish_content(world, "CT.POPUP", "p1", "휴관 안내입니다.", CONTS_TTL="휴관", SORT_SEQ=1)
    publish_content(world, "CT.POPUP", "p2", "   ", CONTS_TTL="본문없음", SORT_SEQ=2)
    publish_content(world, "CT.POPUP", "p3", "x", CONTS_TTL="지난팝업", PSTG_END_DT=START - DAY)
    image = banner_image(world, shown)
    popups = home(world)["popups"]
    assert [p["title"] for p in popups] == ["휴관", "본문없음"]
    assert popups[0]["body"] == "휴관 안내입니다." and popups[1]["body"] is None
    assert popups[0]["image"]["url"] == f"/api/v1/files/{image['FILE_SN']}"


def test_배너와_팝업은_서로_유형이_섞이지_않고_다른_묶음의_것은_나오지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    publish_content(world, "CT.BANNER", "b1", "", CONTS_TTL="배너")
    publish_content(world, "CT.POPUP", "p1", "본문", CONTS_TTL="팝업")
    publish_content(world, "CT.BANNER", "b9", "", CONTS_TTL="남의 배너", OPER_BNDL_SN=other)
    body = home(world)
    assert [b["title"] for b in body["banners"]] == ["배너"] and [p["title"] for p in body["popups"]] == [
        "팝업"
    ]


def test_대표_비주얼은_저장_위치가_정해질_때까지_항상_null이다(world: World) -> None:
    publish_content(world, "CT.INTRO", "home-visual", "{}", CONTS_TTL="비주얼")
    assert home(world)["visual"] is None
