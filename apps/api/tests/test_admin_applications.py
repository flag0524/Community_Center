# 관리자 수강신청·대기 조회(범위·마스킹·검색·이력·승격 문자 결과)를 실제 앱과 MariaDB로 확인하는 시험
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.audit import record_job
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_cancel import cancel, waiter
from tests.test_applications_cancel import open_course as future_course
from tests.test_applications_create import apply, key
from tests.test_applications_read import RESIDENT, application, payment, sign_in
from tests.test_applications_read import open_course as _open_course
from tests.test_courses_public import course as make_course
from tests.test_courses_public import cycle
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def member(w: World, name: str = "홍길동") -> dict[str, Any]:
    return make_member(w, f"u{key()}", MBR_NM=name, **RESIDENT)


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_신청_조회_권한이_없으면_403이다(world: World) -> None:
    use(world, staff(world, "x", "AU.RFND_A"))
    assert call(world, "GET", "/applications").status_code == 403
    assert call(world, "GET", "/waitlist").status_code == 403


def test_동_담당자는_자기_동_강좌의_신청만_보고_신청자_거주지는_보지_않는다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    who = staff(world, "d1", "AU.APLY_R", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    visible = application(world, member(world), course(world, DONG_SN=mine["DONG_SN"]))
    hidden = application(world, member(world), course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))
    common = application(world, member(world), course(world, CORS_NM="공통"))
    use(world, who)
    ids = [i["applicationId"] for i in call(world, "GET", "/applications").json()["items"]]
    assert ids == [str(visible["ATNLC_APLY_SN"])]
    assert call(world, "GET", f"/applications/{visible['ATNLC_APLY_SN']}").status_code == 200
    for target in (hidden, common):
        assert call(world, "GET", f"/applications/{target['ATNLC_APLY_SN']}").status_code == 404


def test_동_담당자는_범위_밖_강좌의_대기_현황도_보지_못한다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    who = staff(world, "d1", "AU.APLY_R", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    inside = course(world, DONG_SN=mine["DONG_SN"], RCRT_NOPE=1)
    outside = course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"], RCRT_NOPE=1)
    for row in (inside, outside):
        application(world, member(world), row, "ES.CONFIRM")
        application(world, member(world), row, "ES.WAIT", WTNG_SEQ=1)
    use(world, who)
    listed = call(world, "GET", "/waitlist").json()
    assert [c["courseId"] for c in listed["items"]] == [str(inside["CORS_SN"])]
    assert call(world, "GET", f"/waitlist/{inside['CORS_SN']}").status_code == 200
    assert call(world, "GET", f"/waitlist/{outside['CORS_SN']}").status_code == 404
    assert call(world, "GET", "/waitlist/999999").status_code == 404


# --- 목록 ---------------------------------------------------------------------------------------


def test_목록은_이름을_가리고_표시_상태와_결제_환불_상태를_준다(world: World) -> None:
    who = staff(world, "boss", "AU.APLY_R")
    row = course(world)
    app = application(world, member(world, "홍길동"), row, "ES.CONFIRM")
    paid = payment(world, app, "PS.PAID", STLM_AMT=30000)
    world.factory.make("TB_RFND", STLM_SN=paid["STLM_SN"], RFND_AMT=1000, RFND_STTS_CD="RS.REQUEST")
    use(world, who)
    [item] = call(world, "GET", "/applications").json()["items"]
    assert item["applicantName"] == "홍*동" and item["courseName"] == "요가"
    assert (item["status"], item["paymentStatus"], item["refundStatus"]) == ("CONFIRMED", "PAID", "REQUESTED")
    assert item["applicationNo"] == str(app["ATNLC_APLY_SN"]) and item["displayState"]


def test_기간은_한국_날짜의_시작과_끝으로_가른다(world: World) -> None:
    who = staff(world, "boss", "AU.APLY_R")
    row = course(world)
    # 한국 11월 9일 00:00 = UTC 11월 8일 15:00
    first_second = application(
        world, member(world), row, "ES.CONFIRM", APLY_DT=datetime(2026, 11, 8, 15, 0, 0)
    )
    last_second = application(
        world, member(world), row, "ES.CONFIRM", APLY_DT=datetime(2026, 11, 8, 14, 59, 59)
    )
    use(world, who)

    def ids(query: str) -> list[str]:
        return [i["applicationId"] for i in call(world, "GET", f"/applications?{query}").json()["items"]]

    assert ids("from=2026-11-09") == [str(first_second["ATNLC_APLY_SN"])]
    assert ids("to=2026-11-08") == [str(last_second["ATNLC_APLY_SN"])]
    assert ids("from=2026-11-08&to=2026-11-08") == [str(last_second["ATNLC_APLY_SN"])]


def test_기수로_거른다(world: World) -> None:
    first, second = cycle(world, "1기", EDU_CYCL=1), cycle(world, "2기", EDU_CYCL=2)
    a = application(world, member(world), make_course(world, first, "가"), "ES.CONFIRM")
    b = application(world, member(world), make_course(world, second, "나"), "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.APLY_R"))

    def ids(cycle_row: dict[str, Any]) -> list[str]:
        query = f"/applications?cycleId={cycle_row['EDU_CYCL_SN']}"
        return [i["applicationId"] for i in call(world, "GET", query).json()["items"]]

    assert ids(first) == [str(a["ATNLC_APLY_SN"])] and ids(second) == [str(b["ATNLC_APLY_SN"])]
    listed = call(world, "GET", f"/waitlist?cycleId={first['EDU_CYCL_SN']}").json()["items"]
    assert listed == []


def test_최신순으로_쪽을_나눠_보인다(world: World) -> None:
    who = staff(world, "boss", "AU.APLY_R")
    row = course(world)
    made = [application(world, member(world), row, "ES.CONFIRM", APLY_DT=START - n * DAY) for n in range(5)]
    use(world, who)
    body = call(world, "GET", "/applications?size=2&page=2").json()
    assert body["total"] == 5 and body["page"] == 2
    assert [i["applicationId"] for i in body["items"]] == [
        str(made[2]["ATNLC_APLY_SN"]),
        str(made[3]["ATNLC_APLY_SN"]),
    ]


def test_검색과_거르기(world: World) -> None:
    who = staff(world, "boss", "AU.APLY_R")
    yoga, tennis = course(world), course(world, CORS_NM="탁구")
    a = application(world, member(world, "김가나"), yoga, "ES.CONFIRM", APLY_DT=START - 10 * DAY)
    b = application(world, member(world, "박다라"), tennis, "ES.CANCEL", APLY_DT=START)
    payment(world, a, "PS.PAID")
    payment(world, b, "PS.FAIL")
    use(world, who)

    def ids(query: str) -> list[str]:
        return [i["applicationId"] for i in call(world, "GET", f"/applications?{query}").json()["items"]]

    sa, sb = str(a["ATNLC_APLY_SN"]), str(b["ATNLC_APLY_SN"])
    assert ids(f"q={sa}") == [sa]
    assert ids("q=박다") == [sb]
    assert ids("q=%25") == []  # 와일드카드 문자는 글자로만 찾는다
    assert ids("status=CANCELLED") == [sb]
    assert ids("paymentStatus=PAID") == [sa]
    assert ids(f"courseId={tennis['CORS_SN']}") == [sb]
    assert ids(f"cycleId={yoga['EDU_CYCL_SN']}") == [sb, sa]
    assert ids("from=2026-11-09") == [sb]
    assert ids("to=2026-11-08") == [sa]
    assert ids("status=CONFIRMED&courseId=" + str(tennis["CORS_SN"])) == []


# --- 상세·이력 ----------------------------------------------------------------------------------


def test_상세는_신청_생성과_취소_이력과_결제_환불을_보인다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = future_course(world)
    created = apply(world, row)
    assert created.status_code == 201
    app_id = created.json()["applicationId"]
    assert cancel(world, {"ATNLC_APLY_SN": app_id}).status_code == 200
    use(world, staff(world, "boss", "AU.APLY_R"))
    body = call(world, "GET", f"/applications/{app_id}").json()
    assert [(h["fromStatus"], h["toStatus"], h["actor"]) for h in body["history"]] == [
        (None, "HOLD", "회원"),
        ("HOLD", "CANCELLED", "회원"),
    ]
    assert body["cycleName"] and body["courseId"] == str(row["CORS_SN"]) and body["replays"] == []
    assert body["payment"] is None and body["refund"] is None and body["waitingOrder"] is None


def test_대기_신청은_대기_순번을_보인다(world: World) -> None:
    row = future_course(world, RCRT_NOPE=1)
    application(world, member(world), row, "ES.CONFIRM")
    waiter(world, row, "w1", 1)
    second = waiter(world, row, "w2", 2)
    use(world, staff(world, "boss", "AU.APLY_R"))
    assert call(world, "GET", f"/applications/{second['ATNLC_APLY_SN']}").json()["waitingOrder"] == 2


def test_결제와_환불이_연결된_신청의_상세(world: World) -> None:
    app = application(world, member(world), course(world), "ES.CANCEL")
    paid = payment(world, app, "PS.PAID", STLM_AMT=30000)
    world.factory.make(
        "TB_RFND", STLM_SN=paid["STLM_SN"], RFND_AMT=30000, RFND_STTS_CD="RS.DONE", RFND_DT=START
    )
    use(world, staff(world, "boss", "AU.APLY_R"))
    body = call(world, "GET", f"/applications/{app['ATNLC_APLY_SN']}").json()
    assert body["payment"]["amount"] == 30000 and body["payment"]["status"] == "PAID"
    assert body["payment"]["orderNo"] == paid["STLM_NO"] and body["payment"]["approvedAt"]
    assert body["refund"]["amount"] == 30000 and body["refund"]["status"] == "DONE"


# --- 대기·승격 ----------------------------------------------------------------------------------


def test_대기_현황과_승격_이력과_문자_결과(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = future_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    first = waiter(world, row, "w1", 1)
    waiter(world, row, "w2", 2)
    assert cancel(world, holder).status_code == 200  # 자리가 나 첫 대기자가 자동 승격된다
    use(world, staff(world, "boss", "AU.APLY_R"))
    listed = call(world, "GET", "/waitlist").json()["items"]
    assert [(c["courseId"], c["capacity"], c["occupied"], c["waitCount"]) for c in listed] == [
        (str(row["CORS_SN"]), 1, 1, 1)
    ]
    assert listed[0]["nextWaitOrder"] == 1 and listed[0]["lastPromotedAt"]
    detail = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()
    assert [w["order"] for w in detail["waiters"]] == [1]
    assert "*" in detail["waiters"][0]["applicantName"]  # 이름은 가려서 준다
    [promo] = detail["promotions"]
    assert promo["applicationNo"] == str(first["ATNLC_APLY_SN"]) and promo["smsResult"] == "PENDING"
    history = call(world, "GET", f"/applications/{first['ATNLC_APLY_SN']}").json()["history"]
    assert (history[-1]["fromStatus"], history[-1]["toStatus"], history[-1]["actor"]) == (
        "WAITING",
        "HOLD",
        "SYSTEM",
    )


@pytest.mark.parametrize(
    ("code", "result"),
    [
        ("SS.WAIT", "PENDING"),
        ("SS.SENDING", "PENDING"),
        ("SS.UNKNOWN", "PENDING"),
        ("SS.SENT", "SENT"),
        ("SS.FAIL", "FAILED"),
        ("SS.SKIP", "FAILED"),
    ],
)
def test_문자_결과는_발송_상태에서_정해진다(world: World, code: str, result: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = future_course(world, RCRT_NOPE=1)
    holder = application(world, me, row, "ES.HOLD")
    waiter(world, row, "w1", 1)
    cancel(world, holder)
    world.db.execute(text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD=:c"), {"c": code})
    use(world, staff(world, "boss", "AU.APLY_R"))
    detail = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()
    assert detail["promotions"][0]["smsResult"] == result


def test_수신번호가_없어_문자를_쌓지_않았으면_발송_실패로_보인다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = future_course(world, RCRT_NOPE=1)
    holder = application(world, me, row, "ES.HOLD")
    nophone = make_member(world, "np", MBL_TELNO=None, **RESIDENT)
    application(world, nophone, row, "ES.WAIT", WTNG_SEQ=1)
    cancel(world, holder)
    use(world, staff(world, "boss", "AU.APLY_R"))
    detail = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()
    assert detail["promotions"][0]["smsResult"] == "FAILED"


def test_승격이_여러_번이면_최신_승격이_먼저이고_신청마다_자기_문자_결과를_본다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = future_course(world, RCRT_NOPE=2, WTNG_NOPE=5)
    h1, h2 = application(world, me, row, "ES.HOLD"), application(world, member(world), row, "ES.HOLD")
    first, second = waiter(world, row, "w1", 1), waiter(world, row, "w2", 2)
    assert cancel(world, h1).status_code == 200  # 첫 승격
    world.clock.advance(minutes=1)
    world.db.execute(
        text(
            "UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CANCEL', RTRCN_DT=:t, RTRCN_RSN='x' WHERE ATNLC_APLY_SN=:a"
        ),
        {"t": START, "a": h2["ATNLC_APLY_SN"]},
    )
    world.db.execute(text("UPDATE TB_SMS_TRGT SET TRGT_STTS_CD='SS.SENT'"))  # 첫 승격 문자는 발송됨
    from app.domain.application.seats import lock_course, promote_waiters

    promote_waiters(
        world.db,
        world.settings,
        lock_course(world.db, world.bundle, int(row["CORS_SN"])),
        now=world.clock(),
        request_id="r",
    )
    use(world, staff(world, "boss", "AU.APLY_R"))
    promos = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()["promotions"]
    assert [(p["applicationNo"], p["smsResult"]) for p in promos] == [
        (str(second["ATNLC_APLY_SN"]), "PENDING"),
        (str(first["ATNLC_APLY_SN"]), "SENT"),
    ]


def test_대기자는_접수_순서가_아니라_대기_순서로_보인다(world: World) -> None:
    row = future_course(world, RCRT_NOPE=1)
    application(world, member(world), row, "ES.CONFIRM")
    late = waiter(world, row, "w1", 2)  # 신청 번호는 앞서지만 대기 순서가 뒤다
    early = waiter(world, row, "w2", 1)
    use(world, staff(world, "boss", "AU.APLY_R"))
    waiters = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()["waiters"]
    assert [w["applicationNo"] for w in waiters] == [str(early["ATNLC_APLY_SN"]), str(late["ATNLC_APLY_SN"])]


def test_점유는_결제대기와_수강확정을_함께_센다(world: World) -> None:
    row = future_course(world, RCRT_NOPE=5)
    application(world, member(world), row, "ES.HOLD")
    application(world, member(world), row, "ES.CONFIRM")
    application(world, member(world), row, "ES.CANCEL")
    application(world, member(world), row, "ES.WAIT", WTNG_SEQ=1)
    use(world, staff(world, "boss", "AU.APLY_R"))
    detail = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()
    assert (detail["occupied"], detail["waitCount"], detail["capacity"]) == (2, 1, 5)


def test_실패한_작업은_이력에_보이지_않는다(world: World) -> None:
    app = application(world, member(world), course(world), "ES.CONFIRM")
    record_job(
        world.db,
        actor="AK.SYSTEM",
        job="APLY_CANCEL",
        table="TB_ATNLC_APLY",
        key=app["ATNLC_APLY_SN"],
        request_id="r",
        now=START,
        bundle_sn=world.bundle,
        result="JR.FAIL",
        change="실패",
    )
    use(world, staff(world, "boss", "AU.APLY_R"))
    assert call(world, "GET", f"/applications/{app['ATNLC_APLY_SN']}").json()["history"] == []


def test_대기자가_없는_강좌는_대기_목록에_나오지_않지만_상세는_볼_수_있다(world: World) -> None:
    row = course(world)
    application(world, member(world), row, "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.APLY_R"))
    assert call(world, "GET", "/waitlist").json()["items"] == []
    detail = call(world, "GET", f"/waitlist/{row['CORS_SN']}").json()
    assert detail["waitCount"] == 0 and detail["nextWaitOrder"] is None and detail["waiters"] == []
