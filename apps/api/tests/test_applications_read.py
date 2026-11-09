# 신청 화면 미리보기(신청 가능 판정·금액·감면)와 내 신청 목록·상세를 실제 앱과 MariaDB로 확인하는 시험
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from app.core.errors import ErrorCode
from app.domain.application.pricing import find_usable_approval
from app.domain.application.service import first_blocker, load_member
from tests.test_courses_public import course, cycle
from tests.world import MEMBER, START, World, login, make_admin, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
RESIDENT = {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.OK"}


def sign_in(w: World, login_id: str = "me", **values: Any) -> dict[str, Any]:
    member = make_member(w, login_id, **values)
    assert login(w, MEMBER, login_id).status_code == 200
    return member


def application(
    w: World, member: dict[str, Any], course_row: dict[str, Any], state: str = "ES.CONFIRM", **values: Any
) -> dict[str, Any]:
    extra: dict[str, Any] = {"TTCHG_AMT": 30000, "RDCT_AMT": 0, "STLM_PRNMNT_AMT": 30000}
    if state == "ES.WAIT":
        extra["WTNG_SEQ"] = 1
    if state == "ES.HOLD":
        extra.update(SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START + timedelta(minutes=10))
    if state in ("ES.CONFIRM", "ES.COMPLETE"):
        extra["SEAT_ALTMNT_DT"] = START
    if state in ("ES.CANCEL", "ES.EXPIRE"):
        extra.update(RTRCN_DT=START, RTRCN_RSN="취소")
    return w.factory.make(
        "TB_ATNLC_APLY",
        CORS_SN=course_row["CORS_SN"],
        MBR_SN=member["MBR_SN"],
        APLY_STTS_CD=state,
        **{**extra, **values},
    )


def payment(w: World, app: dict[str, Any], state: str, **values: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if state == "PS.PAID":
        extra.update(STLM_APRV_NO="A1", STLM_APRV_DT=START)
    return w.factory.make(
        "TB_STLM", ATNLC_APLY_SN=app["ATNLC_APLY_SN"], STLM_STTS_CD=state, **{**extra, **values}
    )


def preview(w: World, course_row: dict[str, Any]) -> Any:
    return w.client.get(f"{MEMBER}/courses/{course_row['CORS_SN']}/apply-preview")


def the_cycle(w: World) -> dict[str, Any]:
    """이 시험의 기본 기수. 이미 있으면 다시 만들지 않는다."""
    found = (
        w.db.execute(
            text("SELECT * FROM TB_EDU_CYCL WHERE OPER_BNDL_SN = :b AND EDU_YR = '2026' AND EDU_CYCL = 4"),
            {"b": w.bundle},
        )
        .mappings()
        .first()
    )
    return dict(found) if found else cycle(w)


def open_course(w: World, **values: Any) -> dict[str, Any]:
    name = values.pop("CORS_NM", "요가")
    return course(w, the_cycle(w), name, **values)


# --- 신청 가능 판정(미리보기) ---------------------------------------------------------------


def test_접수중인_강좌는_주민이면_신청할_수_있다(world: World) -> None:
    sign_in(world, **RESIDENT)
    body = preview(world, open_course(world, TTCHG=45000)).json()
    assert body["eligibility"] == {"canApply": True, "reasonCode": None, "reasonMessage": None}
    assert (body["fee"], body["reductionAmount"], body["payableAmount"]) == (45000, 0, 45000)
    assert body["paymentWindowSeconds"] == 600 and body["alreadyApplied"] is False
    assert body["serverNow"].startswith("2026-11-09T09:00:00")
    assert body["course"]["name"] == "요가" and body["course"]["remainingSeats"] == 10


@pytest.mark.parametrize(
    "values",
    [
        {"CORS_STTS_CD": "CS.CLOSE"},
        {"CORS_STTS_CD": "CS.RUN"},
        {"RCPT_BGNG_DT": START + timedelta(seconds=1)},
        {"RCPT_END_DT": START},
    ],
    ids=["수동마감", "운영중", "접수전", "접수종료_정각"],
)
def test_접수중이_아니면_접수기간이_아니라고_알린다(world: World, values: dict[str, Any]) -> None:
    sign_in(world, **RESIDENT)
    body = preview(world, open_course(world, **values)).json()
    assert (
        body["eligibility"]["canApply"] is False and body["eligibility"]["reasonCode"] == "APLY_RCPT_CLOSED"
    )
    assert body["eligibility"]["reasonMessage"] == "접수기간이 아닙니다."


def test_주민이_아니면_관외_개방_전까지_우선접수_기간이다(world: World) -> None:
    sign_in(world, "outsider")
    unset = open_course(world)
    future = open_course(world, OTSD_RGN_RCPT_BGNG_DT=START + timedelta(seconds=1))
    assert preview(world, unset).json()["eligibility"]["reasonCode"] == "APLY_PRIORITY_PERIOD"
    assert preview(world, future).json()["eligibility"]["reasonCode"] == "APLY_PRIORITY_PERIOD"
    assert preview(world, future).json()["residentPriorityActive"] is True


def test_관외_개방_시각이_되면_주민이_아니어도_신청할_수_있다(world: World) -> None:
    sign_in(world, "outsider")
    opened = open_course(world, OTSD_RGN_RCPT_BGNG_DT=START)  # 정각부터 열린다
    body = preview(world, opened).json()
    assert body["eligibility"]["canApply"] is True and body["residentPriorityActive"] is False


@pytest.mark.parametrize(
    "values",
    [
        {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.OK"},
        {"HAB_RGN_CD": "RA.PAJU_ETC", "HAB_IDNTY_STTS_CD": "RV.OK"},
    ],
    ids=["조리읍", "파주시"],
)
def test_확인된_파주시_주민은_우선접수_기간에도_신청할_수_있다(world: World, values: dict[str, Any]) -> None:
    sign_in(world, **values)
    assert preview(world, open_course(world)).json()["eligibility"]["canApply"] is True


@pytest.mark.parametrize(
    "values",
    [
        {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.NONE"},
        {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.RECHECK"},
        {"HAB_RGN_CD": "RA.OUTSIDE", "HAB_IDNTY_STTS_CD": "RV.OK"},
        {"HAB_RGN_CD": "RA.UNKNOWN", "HAB_IDNTY_STTS_CD": "RV.OK"},
    ],
    ids=["미확인", "재확인필요", "파주시_외", "구분_미확인"],
)
def test_센터가_거주를_확인하지_못한_회원은_주민이_아니다(world: World, values: dict[str, Any]) -> None:
    sign_in(world, **values)
    assert preview(world, open_course(world)).json()["eligibility"]["reasonCode"] == "APLY_PRIORITY_PERIOD"


@pytest.mark.parametrize("state", ["ES.WAIT", "ES.HOLD", "ES.CONFIRM"])
def test_이미_유효한_신청이_있으면_중복이라고_알린다(world: World, state: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    application(world, me, row, state)
    body = preview(world, row).json()
    assert body["alreadyApplied"] is True and body["eligibility"]["reasonCode"] == "APLY_ALREADY_APPLIED"


@pytest.mark.parametrize("state", ["ES.CANCEL", "ES.EXPIRE", "ES.COMPLETE"])
def test_취소_만료_종료된_신청은_다시_신청할_수_있다(world: World, state: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    application(world, me, row, state)
    body = preview(world, row).json()
    assert body["alreadyApplied"] is False and body["eligibility"]["canApply"] is True


def test_다른_회원이나_다른_강좌의_신청은_중복이_아니다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row, other_course = open_course(world), open_course(world, CORS_NM="다른강좌")
    stranger = make_member(world, "stranger")
    application(world, stranger, row, "ES.CONFIRM")
    me_row = world.db.execute(text("SELECT MBR_SN FROM TB_MBR WHERE LGN_ID = 'me'")).one()
    application(world, {"MBR_SN": int(me_row[0])}, other_course, "ES.CONFIRM")
    assert preview(world, row).json()["alreadyApplied"] is False


def fill(w: World, course_row: dict[str, Any], confirmed: int = 0, waiting: int = 0) -> None:
    for index in range(confirmed):
        application(w, make_member(w, f"c{index}"), course_row, "ES.CONFIRM")
    for index in range(waiting):
        application(w, make_member(w, f"w{index}"), course_row, "ES.WAIT", WTNG_SEQ=index + 1)


def test_정원이_차면_주민은_대기_접수를_할_수_있다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=2, WTNG_NOPE=2)
    fill(world, row, confirmed=2)
    body = preview(world, row).json()
    assert body["eligibility"]["canApply"] is True and body["course"]["remainingSeats"] == 0


def test_대기정원까지_차면_정원_초과라고_알린다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=1)
    fill(world, row, confirmed=1, waiting=1)
    assert preview(world, row).json()["eligibility"]["reasonCode"] == "APLY_FULL"


def test_대기자가_있으면_빈자리가_있어도_새_신청이_가로채지_못한다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=3, WTNG_NOPE=1)
    fill(world, row, confirmed=1, waiting=1)
    assert preview(world, row).json()["eligibility"]["reasonCode"] == "APLY_FULL"  # 주민도 대기 정원이 찼다
    roomy = open_course(world, CORS_NM="넓은강좌", RCRT_NOPE=3, WTNG_NOPE=5)
    fill_member = make_member(world, "wait-roomy")
    application(world, fill_member, roomy, "ES.WAIT", WTNG_SEQ=1)
    assert preview(world, roomy).json()["eligibility"]["canApply"] is True  # 대기열 맨 뒤에 선다


def test_관외_신청자는_잔여가_없으면_대기도_못한다(world: World) -> None:
    sign_in(world, "outsider")
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, OTSD_RGN_RCPT_BGNG_DT=START - DAY)
    fill(world, row, confirmed=1)
    assert preview(world, row).json()["eligibility"]["reasonCode"] == "APLY_FULL"


def test_관외_신청자도_잔여가_있고_대기자가_없으면_신청할_수_있다(world: World) -> None:
    sign_in(world, "outsider")
    row = open_course(world, RCRT_NOPE=2, OTSD_RGN_RCPT_BGNG_DT=START - DAY)
    fill(world, row, confirmed=1)
    assert preview(world, row).json()["eligibility"]["canApply"] is True


def test_보류도_정원을_차지하지만_취소와_만료는_차지하지_않는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=0)
    holder = make_member(world, "holder")
    held = application(world, holder, row, "ES.HOLD")
    assert preview(world, row).json()["eligibility"]["reasonCode"] == "APLY_FULL"
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.EXPIRE', RTRCN_DT=:n WHERE ATNLC_APLY_SN=:s"),
        {"n": START, "s": held["ATNLC_APLY_SN"]},
    )
    assert preview(world, row).json()["eligibility"]["canApply"] is True


def test_이유가_여럿이면_접수기간_우선접수_중복_정원_순으로_알린다(world: World) -> None:
    member = SimpleNamespace(MBR_STTS_CD="MS.ACTIVE", HAB_RGN_CD="RA.OUTSIDE", HAB_IDNTY_STTS_CD="RV.OK")
    row = SimpleNamespace(
        CORS_STTS_CD="CS.OPEN",
        RCPT_BGNG_DT=START - DAY,
        RCPT_END_DT=START + DAY,
        OTSD_RGN_RCPT_BGNG_DT=None,
        RCRT_NOPE=1,
        WTNG_NOPE=0,
    )

    def blocker(already_applied: bool) -> ErrorCode | None:
        return first_blocker(
            member=member, course=row, already_applied=already_applied, occupied=1, waiting=0, now=START
        )

    assert blocker(True) is ErrorCode.APLY_PRIORITY_PERIOD
    row.OTSD_RGN_RCPT_BGNG_DT = START - DAY
    assert blocker(True) is ErrorCode.APLY_ALREADY_APPLIED
    assert blocker(False) is ErrorCode.APLY_FULL
    member.MBR_STTS_CD = "MS.LOCKED"
    assert blocker(False) is ErrorCode.APLY_MEMBER_INACTIVE
    row.CORS_STTS_CD = "CS.CLOSE"
    assert blocker(False) is ErrorCode.APLY_RCPT_CLOSED


def test_공개되지_않았거나_없는_강좌의_미리보기는_404다(world: World) -> None:
    sign_in(world, **RESIDENT)
    draft = open_course(world, CORS_STTS_CD="CS.DRAFT")
    assert preview(world, draft).status_code == 404
    assert world.client.get(f"{MEMBER}/courses/99999999/apply-preview").status_code == 404
    assert world.client.get(f"{MEMBER}/courses/abc/apply-preview").status_code == 400


# --- 금액과 감면 ---------------------------------------------------------------------------


def approval(w: World, member: dict[str, Any], cyc: dict[str, Any], **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "MBR_SN": member["MBR_SN"],
        "EDU_CYCL_SN": cyc["EDU_CYCL_SN"],
        "RDCT_TYPE_CD": "DR.LIVELIHD",
        "SRNG_STTS_CD": "DS.APPROVED",
        "SRNG_MNGR_SN": make_admin(w, f"rev{next(_counter)}")["MNGR_SN"],
        "SRNG_DT": START,
    }
    return w.factory.make("TB_RDCT_BFHD_SRNG", **{**defaults, **values})


def reduction_log(w: World, app: dict[str, Any], result: str, **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "ATNLC_APLY_SN": app["ATNLC_APLY_SN"],
        "DCSN_RSLT_CD": result,
        "RDCT_AMT": 15000,
        "DCSN_MNGR_SN": make_admin(w, f"dec{next(_counter)}")["MNGR_SN"],
    }
    return w.factory.make("TB_RDCT_HSTRY", **{**defaults, **values})


_counter = iter(range(1, 10_000))


def reduced(w: World, row: dict[str, Any]) -> tuple[int, int, int]:
    body = preview(w, row).json()
    return body["fee"], body["reductionAmount"], body["payableAmount"]


def reduction_world(world: World) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    me = sign_in(world, **RESIDENT)
    cyc = cycle(world)
    return me, cyc, course(world, cyc, "요가", TTCHG=100000)


def test_사전심사_승인이_있으면_수강료의_절반을_감면한다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    assert reduced(world, row) == (100000, 50000, 50000)


def test_감면은_원_단위로_내림한다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    row = course(world, cyc, "홀수", TTCHG=30001)
    approval(world, me, cyc)
    assert reduced(world, row) == (30001, 15000, 15001)


@pytest.mark.parametrize("kind", ["DR.LIVELIHD", "DR.VETERAN", "DR.DISABLED"])
def test_감면_대상_세_유형은_모두_적용된다(world: World, kind: str) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc, RDCT_TYPE_CD=kind)
    assert reduced(world, row)[1] == 50000


def test_승인이_없으면_감면이_없다(world: World) -> None:
    _, _, row = reduction_world(world)
    assert reduced(world, row) == (100000, 0, 100000)


@pytest.mark.parametrize("state", ["DS.RECEIVED", "DS.REJECTED", "DS.REVOKED"])
def test_승인이_아닌_심사는_감면하지_않는다(world: World, state: str) -> None:
    me, cyc, row = reduction_world(world)
    extra = {"RJCT_RSN": "사유"} if state == "DS.REJECTED" else {}
    approval(world, me, cyc, SRNG_STTS_CD=state, **extra)
    assert reduced(world, row)[1] == 0


def test_다른_기수나_다른_회원의_승인은_쓰지_않는다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    later = cycle(world, "다음", EDU_CYCL=5, EDU_YR="2027", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331")
    approval(world, me, later)
    approval(world, make_member(world, "other", **RESIDENT), cyc)
    assert reduced(world, row)[1] == 0


def test_승인_유효기간이_끝나면_쓰지_않는다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc, VLD_END_DT=START)  # 종료 시각 정각은 이미 끝났다
    assert reduced(world, row)[1] == 0
    approval(world, me, cyc, VLD_END_DT=START + timedelta(seconds=1))
    assert reduced(world, row)[1] == 50000


@pytest.mark.parametrize(
    "values",
    [
        {"HAB_RGN_CD": "RA.PAJU_ETC", "HAB_IDNTY_STTS_CD": "RV.OK"},
        {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.RECHECK"},
    ],
    ids=["파주시_기타", "거주_재확인"],
)
def test_조리읍_거주가_확인된_회원만_감면을_받는다(world: World, values: dict[str, Any]) -> None:
    me = sign_in(world, **values)
    cyc = cycle(world)
    row = course(world, cyc, "요가", TTCHG=100000)
    approval(world, me, cyc)
    assert reduced(world, row)[1] == 0


def test_같은_기수에_이미_감면을_쓴_신청이_있으면_다시_쓰지_못한다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    first = application(
        world, me, course(world, cyc, "먼저", TTCHG=100000), "ES.CANCEL"
    )  # 취소돼도 복구되지 않는다
    reduction_log(world, first, "DR.APPROVE")
    assert reduced(world, row)[1] == 0


def test_담당자가_해제하면_다시_쓸_수_있다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    first = application(world, me, course(world, cyc, "먼저", TTCHG=100000), "ES.CANCEL")
    reduction_log(world, first, "DR.APPROVE")
    reduction_log(world, first, "DR.REJECT")  # 해제는 더 나중의 반려 이력이다
    assert reduced(world, row)[1] == 50000


def test_해제보다_먼저_기록된_반려는_해제가_아니다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    first = application(world, me, course(world, cyc, "먼저", TTCHG=100000), "ES.CANCEL")
    reduction_log(world, first, "DR.REJECT")
    reduction_log(world, first, "DR.APPROVE")  # 반려 뒤에 다시 적용됐다
    assert reduced(world, row)[1] == 0


def test_다른_기수나_다른_회원이_쓴_감면은_영향이_없다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    later = cycle(world, "다음", EDU_CYCL=5, EDU_YR="2027", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331")
    used_later = application(
        world,
        me,
        course(world, later, "다음강좌", EDU_BGNG_YMD="20270101", EDU_END_YMD="20270331"),
        "ES.CONFIRM",
    )
    reduction_log(world, used_later, "DR.APPROVE")
    stranger = make_member(world, "stranger", **RESIDENT)
    used_by_other = application(world, stranger, course(world, cyc, "남의", TTCHG=100000), "ES.CONFIRM")
    reduction_log(world, used_by_other, "DR.APPROVE")
    assert reduced(world, row)[1] == 50000


def test_수강료가_0원이면_감면도_0원이다(world: World) -> None:
    me, cyc, _ = reduction_world(world)
    free = course(world, cyc, "무료", TTCHG=0)
    approval(world, me, cyc)
    assert reduced(world, free) == (0, 0, 0)


# --- 내 신청 목록·상세 ----------------------------------------------------------------------


def mine(w: World, **params: Any) -> Any:
    return w.client.get(f"{MEMBER}/me/applications", params=params)


def detail(w: World, app: dict[str, Any]) -> Any:
    return w.client.get(f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}")


def test_내_신청만_최근_순으로_보인다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    cyc = cycle(world)
    older = application(world, me, course(world, cyc, "먼저"), "ES.CONFIRM", APLY_DT=START - 2 * DAY)
    newer = application(world, me, course(world, cyc, "나중"), "ES.CONFIRM", APLY_DT=START - DAY)
    application(world, make_member(world, "stranger"), course(world, cyc, "남의"), "ES.CONFIRM")
    body = mine(world).json()
    assert [i["applicationId"] for i in body["items"]] == [
        str(newer["ATNLC_APLY_SN"]),
        str(older["ATNLC_APLY_SN"]),
    ]
    assert body["total"] == 2 and body["criteria"]["basisAt"].startswith("2026-11-09T09:00:00")


def test_목록은_쪽으로_나뉘고_전체_건수는_내_신청_수다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    cyc = cycle(world)
    for index in range(5):
        application(
            world, me, course(world, cyc, f"강좌{index}"), "ES.CONFIRM", APLY_DT=START - (index + 1) * DAY
        )
    page2 = mine(world, size=2, page=2).json()
    assert [i["course"]["name"] for i in page2["items"]] == ["강좌2", "강좌3"] and page2["total"] == 5
    assert mine(world, size=2, page=4).json()["items"] == []
    assert mine(world, page=0).status_code == 400 and mine(world, size=51).status_code == 400


def test_상세는_내_신청이_아니면_404다(world: World) -> None:
    sign_in(world, **RESIDENT)
    cyc = cycle(world)
    stranger = make_member(world, "stranger")
    theirs = application(world, stranger, course(world, cyc, "남의"), "ES.CONFIRM")
    assert detail(world, theirs).status_code == 404
    assert world.client.get(f"{MEMBER}/me/applications/99999999").status_code == 404
    assert world.client.get(f"{MEMBER}/me/applications/abc").status_code == 400


def test_상세는_금액_일시와_서버_시각을_준다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    app = application(
        world,
        me,
        row,
        "ES.HOLD",
        TTCHG_AMT=100000,
        RDCT_AMT=50000,
        STLM_PRNMNT_AMT=50000,
        RDCT_RSN="국가유공자",  # 감면이 있으면 사유와 담당자가 필요하다(R09)
        RDCT_MNGR_SN=make_admin(world, "reviewer")["MNGR_SN"],
        APLY_DT=START - DAY,
    )
    body = detail(world, app).json()
    assert (body["fee"], body["reductionAmount"], body["payableAmount"]) == (100000, 50000, 50000)
    assert body["appliedAt"].startswith("2026-11-08T09:00:00") and body["seatAssignedAt"].startswith(
        "2026-11-09T09:00:00"
    )
    assert body["paymentDeadline"].startswith("2026-11-09T09:10:00") and body["serverNow"].startswith(
        "2026-11-09T09:00:00"
    )
    assert body["status"] == "HOLD" and body["course"]["name"] == "요가"


def test_폐강된_강좌의_신청도_강좌_정보와_함께_보인다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, CORS_STTS_CD="CS.CANCEL")
    app = application(world, me, row, "ES.CANCEL", RTRCN_RSN="폐강")
    body = detail(world, app).json()
    assert body["displayState"] == "COURSE_CLOSED" and body["course"]["name"] == "요가"
    assert body["course"]["receptionState"] == "CLOSED"


@pytest.mark.parametrize(
    ("state", "course_state", "display", "cancel"),
    [
        ("ES.EXPIRE", "CS.OPEN", "EXPIRED", False),
        ("ES.COMPLETE", "CS.RUN", "COMPLETED", False),
        ("ES.CANCEL", "CS.OPEN", "CANCELLED", False),
        ("ES.CANCEL", "CS.CANCEL", "COURSE_CLOSED", False),
    ],
)
def test_끝난_신청의_화면_상태(
    world: World, state: str, course_state: str, display: str, cancel: bool
) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world, CORS_STTS_CD=course_state), state)
    body = detail(world, app).json()
    assert body["displayState"] == display and body["canCancel"] is cancel
    assert body["canPay"] is False and body["canRequestRefund"] is False


def test_대기_신청은_순번을_보이고_취소할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    ahead = application(world, make_member(world, "first"), row, "ES.WAIT", WTNG_SEQ=1)
    mine_app = application(world, me, row, "ES.WAIT", WTNG_SEQ=2)
    application(world, make_member(world, "behind"), row, "ES.WAIT", WTNG_SEQ=3)
    body = detail(world, mine_app).json()
    assert body["displayState"] == "WAITING" and body["waitingRank"] == 2 and body["canCancel"] is True
    assert detail(world, ahead).status_code == 404  # 남의 신청이다
    assert body["canPay"] is False and body["canRequestRefund"] is False


def test_대기_순번은_같은_강좌의_대기_신청만_센다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    cyc = cycle(world)
    row, other = course(world, cyc, "가"), course(world, cyc, "나")
    application(world, make_member(world, "other-course"), other, "ES.WAIT", WTNG_SEQ=1)
    application(world, make_member(world, "cancelled"), row, "ES.CANCEL")
    mine_app = application(world, me, row, "ES.WAIT", WTNG_SEQ=7)
    assert detail(world, mine_app).json()["waitingRank"] == 1


def test_대기순서가_같으면_신청번호가_빠른_쪽이_앞이다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    application(world, make_member(world, "early"), row, "ES.WAIT", WTNG_SEQ=4)
    mine_app = application(world, me, row, "ES.WAIT", WTNG_SEQ=4)
    assert detail(world, mine_app).json()["waitingRank"] == 2


def test_대기_순번은_대기_신청에만_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.CONFIRM")
    assert detail(world, app).json()["waitingRank"] is None


def test_결제대기는_기한_안에서만_결제할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    live = application(world, me, row, "ES.HOLD")
    body = detail(world, live).json()
    assert body["displayState"] == "PAYMENT_DUE" and body["canPay"] is True and body["canCancel"] is True
    world.clock.advance(minutes=10)  # 기한 정각
    body = detail(world, live).json()
    assert body["displayState"] == "PAYMENT_DUE" and body["canPay"] is False and body["canCancel"] is True


def test_결제_결과_확인_중에는_결제_취소_환불을_모두_막는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    payment(world, app, "PS.PENDING")
    body = detail(world, app).json()
    assert body["displayState"] == "PAYMENT_UNKNOWN" and body["paymentStatus"] == "PENDING"
    assert (body["canPay"], body["canCancel"], body["canRequestRefund"]) == (False, False, False)


def test_결제가_실패해도_기한_안이면_다시_결제할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    payment(world, app, "PS.FAIL")
    body = detail(world, app).json()
    assert body["displayState"] == "PAYMENT_FAILED" and body["canPay"] is True
    world.clock.advance(minutes=11)
    body = detail(world, app).json()
    assert body["displayState"] == "PAYMENT_DUE" and body["canPay"] is False


def test_가장_최근_결제의_상태와_번호를_준다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    payment(world, app, "PS.FAIL")
    last = payment(world, app, "PS.READY")
    body = detail(world, app).json()
    assert body["paymentStatus"] == "READY" and body["paymentId"] == str(last["STLM_SN"])


def test_결제가_없으면_결제_정보도_비어_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    body = detail(world, application(world, me, open_course(world), "ES.HOLD")).json()
    assert body["paymentStatus"] is None and body["paymentId"] is None and body["refundStage"] is None


def test_결제를_마친_확정_신청은_환불을_요청할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.CONFIRM")
    payment(world, app, "PS.PAID")
    body = detail(world, app).json()
    assert body["displayState"] == "CONFIRMED" and body["canRequestRefund"] is True
    assert body["canCancel"] is False and body["canPay"] is False and body["paymentStatus"] == "PAID"


def test_결제_없는_확정은_개강_전까지만_취소할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    before = application(
        world, me, open_course(world, EDU_BGNG_YMD="20261110"), "ES.CONFIRM", TTCHG_AMT=0, STLM_PRNMNT_AMT=0
    )
    after = application(
        world,
        me,
        open_course(world, CORS_NM="시작", EDU_BGNG_YMD="20261109"),
        "ES.CONFIRM",
        TTCHG_AMT=0,
        STLM_PRNMNT_AMT=0,
    )
    one, two = detail(world, before).json(), detail(world, after).json()
    assert (
        one["displayState"] == "CONFIRMED_FREE"
        and one["canCancel"] is True
        and one["canRequestRefund"] is False
    )
    assert two["displayState"] == "CONFIRMED_FREE" and two["canCancel"] is False  # 개강일 당일부터는 막는다


@pytest.mark.parametrize(
    ("code", "stage", "can_request"),
    [
        ("RS.REQUEST", "RECEIVED", False),
        ("RS.HOLD", "ON_HOLD", False),
        ("RS.APPROVE", "PROCESSING", False),
        ("RS.PENDING", "PROCESSING", False),
        ("RS.FAIL", "PROCESSING", False),
        ("RS.DONE", "DONE", False),
        ("RS.REJECT", "REJECTED", True),
    ],
)
def test_환불_단계는_주민_화면_단계로_바꾸고_반려일_때만_다시_요청할_수_있다(
    world: World, code: str, stage: str, can_request: bool
) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.CONFIRM")
    paid = payment(world, app, "PS.PAID")
    extra: dict[str, Any] = {}
    if code == "RS.HOLD":
        extra["HLDOF_RSN"] = "보류 사유"
    if code == "RS.REJECT":
        extra["RJCT_RSN"] = "반려 사유"
    world.factory.make("TB_RFND", STLM_SN=paid["STLM_SN"], RFND_STTS_CD=code, **extra)
    body = detail(world, app).json()
    assert body["refundStage"] == stage and body["canRequestRefund"] is can_request


def test_같은_결제의_환불이_여럿이면_가장_나중_환불의_단계를_준다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.CONFIRM")
    paid = payment(world, app, "PS.PAID")
    world.factory.make("TB_RFND", STLM_SN=paid["STLM_SN"], RFND_STTS_CD="RS.REJECT", RJCT_RSN="반려")
    world.factory.make("TB_RFND", STLM_SN=paid["STLM_SN"], RFND_STTS_CD="RS.REQUEST")
    assert detail(world, app).json()["refundStage"] == "RECEIVED"


def test_감면_대상이_아닌_유형의_승인은_감면하지_않는다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc, RDCT_TYPE_CD="DR.APPROVE")  # 감면 대상 세 유형이 아니다
    assert reduced(world, row)[1] == 0


def test_승인이_여럿이면_가장_나중_승인을_고른다(world: World) -> None:
    me, cyc, _ = reduction_world(world)
    first = approval(world, me, cyc)
    last = approval(world, me, cyc, RDCT_TYPE_CD="DR.VETERAN")
    member = load_member(world.db, me["MBR_SN"])
    assert find_usable_approval(world.db, member, cyc["EDU_CYCL_SN"], START) == last["RDCT_BFHD_SRNG_SN"]
    assert first["RDCT_BFHD_SRNG_SN"] != last["RDCT_BFHD_SRNG_SN"]


def test_다른_신청에_남긴_반려는_해제로_보지_않는다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc)
    used = application(world, me, course(world, cyc, "먼저", TTCHG=100000), "ES.CANCEL")
    other = application(world, me, course(world, cyc, "다른", TTCHG=100000), "ES.CANCEL")
    reduction_log(world, used, "DR.APPROVE")
    reduction_log(world, other, "DR.REJECT")  # 감면을 쓴 신청이 아니라 다른 신청의 반려다
    assert reduced(world, row)[1] == 0


def test_수강료가_있어도_결제예정이_0원이면_결제_없는_확정이다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, EDU_BGNG_YMD="20261110")
    app = application(
        world,
        me,
        row,
        "ES.CONFIRM",
        TTCHG_AMT=30000,
        RDCT_AMT=30000,
        STLM_PRNMNT_AMT=0,
        RDCT_RSN="전액 감면",
        RDCT_MNGR_SN=make_admin(world, "free-reviewer")["MNGR_SN"],
    )
    body = detail(world, app).json()
    assert body["displayState"] == "CONFIRMED_FREE" and body["canCancel"] is True
