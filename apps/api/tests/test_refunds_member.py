# 회원 환불의 반환 기준액 산정, 접수, 신청 취소·자리 반환·승격, 멱등, 한도, 소유권을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.refund.calc import reference_amount
from app.domain.refund.types import RefundRule
from tests.test_applications_read import RESIDENT, application, payment, sign_in
from tests.test_applications_read import open_course as _open_course
from tests.world import MEMBER, World, make_member

pytestmark = pytest.mark.db

_keys = itertools.count(1)


def key() -> str:
    return f"rf-{next(_keys):08d}"


def open_course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def csrf(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])


def paid_application(
    w: World, me: dict[str, Any], row: dict[str, Any], amount: int = 30000
) -> dict[str, Any]:
    app = application(w, me, row, "ES.CONFIRM", TTCHG_AMT=amount, STLM_PRNMNT_AMT=amount)
    payment(w, app, "PS.PAID", STLM_AMT=amount)
    return app


def request_refund(w: World, app: dict[str, Any], idem: str | None = None, **body: Any) -> Any:
    return w.client.post(
        f"{MEMBER}/me/refunds",
        json={"applicationId": str(app["ATNLC_APLY_SN"]), **body},
        headers={"X-CSRF-Token": csrf(w), "Idempotency-Key": idem or key()},
    )


def preview(w: World, app: dict[str, Any]) -> Any:
    return w.client.get(f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/refund-preview")


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings().all())


def status_of(w: World, app: dict[str, Any]) -> str:
    return str(
        rows(w, "SELECT APLY_STTS_CD s FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN=:a", a=app["ATNLC_APLY_SN"])[0][
            "s"
        ]
    )


# --- 반환 기준액 공식(순수 계산) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("paid", "begin", "end", "today", "amount", "rule"),
    [
        (30000, "20261201", "20261231", date(2026, 11, 30), 30000, RefundRule.BEFORE_START),
        (
            30000,
            "20261201",
            "20261231",
            date(2026, 12, 1),
            0,
            RefundRule.AFTER_START,
        ),  # 1개월 과정은 당월에 소진
        (90000, "20261201", "20270228", date(2026, 12, 31), 60000, RefundRule.AFTER_START),
        (90000, "20261201", "20270228", date(2027, 1, 1), 30000, RefundRule.AFTER_START),
        (90000, "20261201", "20270228", date(2027, 2, 1), 0, RefundRule.AFTER_START),  # 마지막 달
        (90000, "20261201", "20270228", date(2027, 3, 5), 0, RefundRule.AFTER_START),  # 종료 후
        (
            100000,
            "20261201",
            "20270228",
            date(2026, 12, 15),
            100000 - 33333,
            RefundRule.AFTER_START,
        ),  # 나머지 원
    ],
)
def test_반환_기준액_공식(
    paid: int, begin: str, end: str, today: date, amount: int, rule: RefundRule
) -> None:
    ref = reference_amount(paid, begin, end, today)
    assert (ref.amount, ref.rule) == (amount, rule)


# --- 미리보기 --------------------------------------------------------------------------------


def test_개강_전_미리보기는_결제액_전액이다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    body = preview(world, app).json()
    assert (body["paidAmount"], body["refundableAmount"], body["reservedAmount"]) == (30000, 30000, 0)
    assert body["basis"]["rule"] == "BEFORE_START"


@pytest.mark.parametrize("kind", ["결제없는_확정", "대기"])
def test_결제가_없거나_확정이_아니면_환불_미리보기를_볼_수_없다(world: World, kind: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    if kind == "대기":
        target = application(world, me, row, "ES.WAIT")
    else:
        target = application(world, me, row, "ES.CONFIRM", TTCHG_AMT=0, STLM_PRNMNT_AMT=0)
    r = preview(world, target)
    assert r.status_code == 422 and r.json()["code"] == "RFND_NOT_ALLOWED"


def test_남의_신청은_환불_미리보기도_404이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    other = application(world, make_member(world, "x"), open_course(world), "ES.CONFIRM")
    assert preview(world, other).status_code == 404


# --- 접수 ------------------------------------------------------------------------------------


def test_환불을_접수하면_신청이_취소되고_자리가_대기자에게_넘어간다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    app = paid_application(world, me, row)
    other = make_member(world, "w1", MBL_TELNO="01012345678", **RESIDENT)
    waiter = application(world, other, row, "ES.WAIT", WTNG_SEQ=1)
    response = request_refund(world, app, reason="사정이 생김")
    assert response.status_code == 201
    body = response.json()
    assert (body["amount"], body["status"], body["applicationId"]) == (
        30000,
        "REQUESTED",
        str(app["ATNLC_APLY_SN"]),
    )
    assert status_of(world, app) == "ES.CANCEL" and status_of(world, waiter) == "ES.HOLD"
    saved = rows(world, "SELECT RFND_AMT, RFND_STTS_CD, DMND_MBR_SN FROM TB_RFND")[0]
    assert (saved["RFND_AMT"], saved["RFND_STTS_CD"], saved["DMND_MBR_SN"]) == (
        30000,
        "RS.REQUEST",
        me["MBR_SN"],
    )


def test_개강_후에는_정원을_돌려주지_않고_대기자를_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261101", EDU_END_YMD="20270131")
    app = paid_application(world, me, row, 90000)
    other = make_member(world, "w1", MBL_TELNO="01012345678", **RESIDENT)
    waiter = application(world, other, row, "ES.WAIT", WTNG_SEQ=1)
    body = request_refund(world, app).json()
    assert body["amount"] == 60000  # 11월 경과 1개월 분을 뺀다
    assert status_of(world, app) == "ES.CANCEL" and status_of(world, waiter) == "ES.WAIT"


def test_교육기간이_지나_남은_금액이_없으면_환불할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world, EDU_BGNG_YMD="20261101", EDU_END_YMD="20261130"))
    r = request_refund(world, app)
    assert r.status_code == 422 and r.json()["code"] == "RFND_NOT_ALLOWED"
    assert status_of(world, app) == "ES.CONFIRM"


def test_진행_중인_환불이_있으면_같은_결제에_다시_접수할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    assert request_refund(world, app).status_code == 201
    again = request_refund(world, app)
    assert again.status_code == 422 and again.json()["code"] == "RFND_NOT_ALLOWED"
    assert len(rows(world, "SELECT 1 FROM TB_RFND")) == 1


def test_신청이_확정인데_환불이_진행_중이면_접수할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    stlm = rows(world, "SELECT STLM_SN FROM TB_STLM WHERE ATNLC_APLY_SN=:a", a=app["ATNLC_APLY_SN"])[0][
        "STLM_SN"
    ]
    world.factory.make(
        "TB_RFND", STLM_SN=stlm, RFND_AMT=1000, RFND_STTS_CD="RS.REQUEST", DMND_MBR_SN=me["MBR_SN"]
    )
    r = request_refund(world, app)
    assert r.status_code == 422 and r.json()["code"] == "RFND_NOT_ALLOWED"


def test_이미_환불이_잡힌_금액을_넘겨_접수할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    world.db.execute(
        text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CONFIRM' WHERE ATNLC_APLY_SN=:a"),
        {"a": app["ATNLC_APLY_SN"]},
    )
    stlm = rows(world, "SELECT STLM_SN FROM TB_STLM WHERE ATNLC_APLY_SN=:a", a=app["ATNLC_APLY_SN"])[0][
        "STLM_SN"
    ]
    world.factory.make("TB_RFND", STLM_SN=stlm, RFND_AMT=30000, RFND_STTS_CD="RS.DONE", RFND_DT=world.clock())
    r = request_refund(world, app)
    assert r.status_code == 422 and r.json()["code"] == "RFND_LIMIT_EXCEEDED"


def test_반려된_환불은_금액을_잡지_않고_신청은_되살리지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    assert request_refund(world, app).status_code == 201
    world.db.execute(text("UPDATE TB_RFND SET RFND_STTS_CD='RS.REJECT', RJCT_RSN='불가'"))
    assert status_of(world, app) == "ES.CANCEL"
    r = request_refund(world, app)  # 신청이 이미 취소라 새로 접수할 수 없다
    assert r.status_code == 422 and r.json()["code"] == "RFND_NOT_ALLOWED"


def test_금액은_요청으로_정할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    r = request_refund(world, app, amount=1)
    assert r.status_code == 400 and "amount" in r.json()["fields"]
    assert rows(world, "SELECT 1 FROM TB_RFND") == []


def test_환불_접수는_작업이력에_남는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    request_refund(world, app)
    found = rows(world, "SELECT MBR_SN, JOB_CD FROM TB_JOB_HSTRY WHERE JOB_CD = 'RFND_REQUEST'")
    assert len(found) == 1 and found[0]["MBR_SN"] == me["MBR_SN"]


# --- 멱등 ------------------------------------------------------------------------------------


def test_같은_키로_다시_보내면_이전_결과이고_다른_신청이면_충돌이다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    first = paid_application(world, me, row)
    second = paid_application(world, make_member(world, "x2", **RESIDENT), row)
    idem = key()
    a = request_refund(world, first, idem)
    b = request_refund(world, first, idem)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["refundId"] == b.json()["refundId"]
    assert len(rows(world, "SELECT 1 FROM TB_RFND")) == 1
    other = application(world, me, open_course(world, CORS_NM="탁구"), "ES.CONFIRM")
    payment(world, other, "PS.PAID", STLM_AMT=30000)
    c = request_refund(world, other, idem)
    assert c.status_code == 409 and c.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert second  # 남의 신청은 이 회원의 요청으로 건드리지 않았다


def test_멱등키가_없으면_400이다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = paid_application(world, me, open_course(world))
    r = world.client.post(
        f"{MEMBER}/me/refunds",
        json={"applicationId": str(app["ATNLC_APLY_SN"])},
        headers={"X-CSRF-Token": csrf(world)},
    )
    assert r.status_code == 400 and rows(world, "SELECT 1 FROM TB_RFND") == []


# --- 소유권·인증 -----------------------------------------------------------------------------


def test_남의_신청과_없는_신청은_404이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    theirs = paid_application(world, make_member(world, "other", **RESIDENT), open_course(world))
    assert request_refund(world, theirs).status_code == 404
    assert status_of(world, theirs) == "ES.CONFIRM" and rows(world, "SELECT 1 FROM TB_RFND") == []
    r = world.client.post(
        f"{MEMBER}/me/refunds",
        json={"applicationId": "99999999"},
        headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()},
    )
    assert r.status_code == 404


def test_로그인과_CSRF가_없으면_접수할_수_없다(world: World) -> None:
    me = make_member(world, "nobody", **RESIDENT)
    app = paid_application(world, me, open_course(world))
    body = {"applicationId": str(app["ATNLC_APLY_SN"])}
    anon = world.client.post(f"{MEMBER}/me/refunds", json=body, headers={"Idempotency-Key": key()})
    assert anon.status_code == 401
    assert world.client.get(f"{MEMBER}/me/refunds").status_code == 401
    sign_in(world, "me2", **RESIDENT)
    no_csrf = world.client.post(f"{MEMBER}/me/refunds", json=body, headers={"Idempotency-Key": key()})
    assert no_csrf.status_code == 403
    assert rows(world, "SELECT 1 FROM TB_RFND") == []


# --- 내역 ------------------------------------------------------------------------------------


def test_내_환불_내역은_내_것만_최신순으로_보인다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    mine = paid_application(world, me, row)
    theirs = paid_application(world, make_member(world, "o", **RESIDENT), row)
    stlm = rows(world, "SELECT STLM_SN FROM TB_STLM WHERE ATNLC_APLY_SN=:a", a=theirs["ATNLC_APLY_SN"])[0][
        "STLM_SN"
    ]
    other_member = rows(world, "SELECT MBR_SN FROM TB_MBR WHERE LGN_ID='o'")[0]["MBR_SN"]
    world.factory.make(
        "TB_RFND", STLM_SN=stlm, RFND_AMT=1000, RFND_STTS_CD="RS.REQUEST", DMND_MBR_SN=other_member
    )
    request_refund(world, mine)
    body = world.client.get(f"{MEMBER}/me/refunds").json()
    assert body["total"] == 1 and body["items"][0]["amount"] == 30000
    assert body["items"][0]["courseName"] == "요가" and body["items"][0]["status"] == "REQUESTED"
