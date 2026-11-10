# 수강신청 생성(자리 배정·대기·금액·감면 이력·멱등·CSRF)을 실제 앱과 MariaDB로 확인하는 시험
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_applications_read import (
    RESIDENT,
    application,
    approval,
    fill,
    open_course,
    reduction_log,
    reduction_world,
    sign_in,
)
from tests.test_courses_public import course
from tests.world import MEMBER, START, World, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
_keys = iter(range(1, 100_000))


def key() -> str:
    return f"key-{next(_keys):08d}"


def csrf(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])


def apply(w: World, course_row: dict[str, Any], idem: str | None = None, **headers: str) -> Any:
    sent = {"X-CSRF-Token": csrf(w), "Idempotency-Key": idem or key(), **headers}
    return w.client.post(
        f"{MEMBER}/me/applications", json={"courseId": str(course_row["CORS_SN"])}, headers=sent
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings().all())


def count_applications(w: World) -> int:
    return len(rows(w, "SELECT 1 FROM TB_ATNLC_APLY"))


# --- 자리 배정 -----------------------------------------------------------------------------


def test_자리가_있으면_결제대기로_배정하고_기한은_배정_시각_10분_뒤다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, TTCHG=45000)
    response = apply(world, row)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "HOLD" and body["displayState"] == "PAYMENT_DUE" and body["canPay"] is True
    assert (body["fee"], body["reductionAmount"], body["payableAmount"]) == (45000, 0, 45000)
    assert body["seatAssignedAt"].startswith("2026-11-09T09:00:00")
    assert body["paymentDeadline"].startswith("2026-11-09T09:10:00")
    assert body["appliedAt"].startswith("2026-11-09T09:00:00") and body["waitingRank"] is None
    saved = rows(world, "SELECT * FROM TB_ATNLC_APLY")[0]
    assert saved["APLY_STTS_CD"] == "ES.HOLD" and saved["WTNG_SEQ"] is None
    assert saved["SEAT_ALTMNT_DT"] == START and saved["STLM_DDLN_DT"] == START + timedelta(seconds=600)


def test_결제기한은_신청_시각이_아니라_배정_시각_기준으로_새로_정해진다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    world.clock.advance(minutes=3)
    body = apply(world, row).json()
    assert body["paymentDeadline"].startswith("2026-11-09T09:13:00")


def test_결제할_금액이_0원이면_바로_수강확정이고_결제기한이_없다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, TTCHG=0)
    body = apply(world, row).json()
    assert body["status"] == "CONFIRMED" and body["displayState"] == "CONFIRMED_FREE"
    assert body["paymentDeadline"] is None and body["seatAssignedAt"].startswith("2026-11-09T09:00:00")
    assert rows(world, "SELECT 1 FROM TB_STLM") == []  # 0원 거래는 만들지 않는다(R12)


def test_정원이_차면_대기로_들어가고_순번을_받는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=2, WTNG_NOPE=3)
    fill(world, row, confirmed=2)
    body = apply(world, row).json()
    assert body["status"] == "WAITING" and body["displayState"] == "WAITING" and body["waitingRank"] == 1
    assert body["seatAssignedAt"] is None and body["paymentDeadline"] is None
    saved = rows(
        world, "SELECT * FROM TB_ATNLC_APLY WHERE MBR_SN = (SELECT MBR_SN FROM TB_MBR WHERE LGN_ID='me')"
    )[0]
    assert saved["WTNG_SEQ"] == 1 and saved["SEAT_ALTMNT_DT"] is None and saved["STLM_DDLN_DT"] is None


def test_대기_순번은_기존_대기_뒤에_이어_붙는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    fill(world, row, confirmed=1)
    application(world, make_member(world, "w1"), row, "ES.WAIT", WTNG_SEQ=4)
    application(world, make_member(world, "w2"), row, "ES.WAIT", WTNG_SEQ=9)
    body = apply(world, row).json()
    assert body["waitingRank"] == 3
    assert (
        rows(world, "SELECT WTNG_SEQ FROM TB_ATNLC_APLY WHERE APLY_STTS_CD='ES.WAIT' ORDER BY WTNG_SEQ")[-1][
            "WTNG_SEQ"
        ]
        == 10
    )


def test_대기자가_있으면_빈자리가_있어도_대기로_들어간다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=3, WTNG_NOPE=5)
    fill(world, row, confirmed=1, waiting=1)  # 자리 2개가 비었지만 대기자가 앞에 있다
    assert apply(world, row).json()["status"] == "WAITING"


def test_보류도_정원을_차지하므로_마지막_자리_뒤_신청은_대기가_된다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=2)
    application(world, make_member(world, "holder"), row, "ES.HOLD")
    assert apply(world, row).json()["status"] == "WAITING"


def test_취소_만료된_신청은_정원을_차지하지_않아_자리를_받는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=0)
    application(world, make_member(world, "gone1"), row, "ES.CANCEL")
    application(world, make_member(world, "gone2"), row, "ES.EXPIRE")
    assert apply(world, row).json()["status"] == "HOLD"


# --- 거절 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"CORS_STTS_CD": "CS.CLOSE"}, "APLY_RCPT_CLOSED"),
        ({"RCPT_END_DT": START}, "APLY_RCPT_CLOSED"),
        ({"RCPT_BGNG_DT": START + timedelta(seconds=1)}, "APLY_RCPT_CLOSED"),
    ],
    ids=["수동마감", "접수종료_정각", "접수전"],
)
def test_접수중이_아니면_422이고_아무것도_남지_않는다(
    world: World, values: dict[str, Any], code: str
) -> None:
    sign_in(world, **RESIDENT)
    response = apply(world, open_course(world, **values))
    assert response.status_code == 422 and response.json()["code"] == code
    assert (
        count_applications(world) == 0
        and rows(world, "SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='APLY_CREATE'") == []
    )


def test_주민이_아니면_우선접수_기간에_422다(world: World) -> None:
    sign_in(world, "outsider")
    response = apply(world, open_course(world))
    assert response.status_code == 422 and response.json()["code"] == "APLY_PRIORITY_PERIOD"


def test_관외_개방_뒤에는_주민이_아니어도_신청된다(world: World) -> None:
    sign_in(world, "outsider")
    assert apply(world, open_course(world, OTSD_RGN_RCPT_BGNG_DT=START)).status_code == 201


def test_이미_신청한_강좌는_다른_키로_다시_못_한다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    assert apply(world, row).status_code == 201
    again = apply(world, row)
    assert again.status_code == 422 and again.json()["code"] == "APLY_ALREADY_APPLIED"
    assert count_applications(world) == 1


def test_취소한_뒤에는_새_신청으로_다시_할_수_있다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    first = apply(world, row).json()
    world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CANCEL', RTRCN_DT=:n"), {"n": START})
    second = apply(world, row)
    assert second.status_code == 201 and second.json()["applicationId"] != first["applicationId"]
    assert count_applications(world) == 2  # 이전 행은 바뀌지 않고 새 행이 생긴다


def test_정원과_대기정원이_모두_차면_422다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=1)
    fill(world, row, confirmed=1, waiting=1)
    before = count_applications(world)
    response = apply(world, row)
    assert response.status_code == 422 and response.json()["code"] == "APLY_FULL"
    assert count_applications(world) == before


def test_관외_신청자는_정원이_차면_대기도_못_한다(world: World) -> None:
    sign_in(world, "outsider")
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, OTSD_RGN_RCPT_BGNG_DT=START - DAY)
    fill(world, row, confirmed=1)
    assert apply(world, row).json()["code"] == "APLY_FULL"


def test_공개되지_않았거나_없거나_다른_묶음의_강좌는_404다(world: World) -> None:
    sign_in(world, **RESIDENT)
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs = course(
        world,
        world.factory.make(
            "TB_EDU_CYCL",
            OPER_BNDL_SN=other,
            EDU_YR="2026",
            EDU_CYCL=9,
            EDU_CYCL_NM="남",
            EDU_BGNG_YMD="20261101",
            EDU_END_YMD="20261231",
            RCPT_BGNG_DT=START - DAY,
            RCPT_END_DT=START + DAY,
        ),
        "남의",
        OPER_BNDL_SN=other,
    )
    for target in (open_course(world, CORS_STTS_CD="CS.DRAFT", CORS_NM="초안"), theirs):
        assert apply(world, target).status_code == 404
    ghost = {"CORS_SN": 99999999}
    assert apply(world, ghost).status_code == 404
    assert count_applications(world) == 0


# --- 금액과 감면 ------------------------------------------------------------------------------


def test_금액은_서버가_정하고_요청에_금액을_넣으면_400이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, TTCHG=45000)
    response = world.client.post(
        f"{MEMBER}/me/applications",
        json={"courseId": str(row["CORS_SN"]), "amount": 1},
        headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()},
    )
    assert response.status_code == 400 and count_applications(world) == 0
    assert "amount" in response.json()["fields"]  # 어떤 필드가 거절됐는지는 알려 준다


def test_신청_뒤에_수강료가_바뀌어도_신청_금액은_그대로다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, TTCHG=45000)
    apply(world, row)
    world.db.execute(text("UPDATE TB_CORS SET TTCHG = 99000"))
    assert rows(world, "SELECT TTCHG_AMT FROM TB_ATNLC_APLY")[0]["TTCHG_AMT"] == 45000


def test_감면이_있으면_절반만_결제하고_사유_담당자_이력이_남는다(world: World) -> None:
    me, cyc, row = reduction_world(world)
    srng = approval(world, me, cyc)
    body = apply(world, row).json()
    assert (body["fee"], body["reductionAmount"], body["payableAmount"]) == (100000, 50000, 50000)
    saved = rows(world, "SELECT * FROM TB_ATNLC_APLY")[0]
    assert (
        saved["RDCT_RSN"] == "기초생활보장 수급자 본인 사전심사 승인"
        and saved["RDCT_MNGR_SN"] == srng["SRNG_MNGR_SN"]
    )
    log = rows(world, "SELECT * FROM TB_RDCT_HSTRY")
    assert len(log) == 1 and log[0]["DCSN_RSLT_CD"] == "DR.APPROVE" and log[0]["RDCT_AMT"] == 50000
    assert (
        log[0]["ATNLC_APLY_SN"] == saved["ATNLC_APLY_SN"]
        and log[0]["RDCT_BFHD_SRNG_SN"] == srng["RDCT_BFHD_SRNG_SN"]
    )
    assert log[0]["DCSN_MNGR_SN"] == srng["SRNG_MNGR_SN"] and log[0]["DCSN_DT"] == START


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("DR.LIVELIHD", "기초생활보장 수급자 본인 사전심사 승인"),
        ("DR.VETERAN", "국가유공자 본인 사전심사 승인"),
        ("DR.DISABLED", "등록 장애인 본인 사전심사 승인"),
    ],
)
def test_감면_사유는_대상_유형만_적는다(world: World, kind: str, reason: str) -> None:
    me, cyc, row = reduction_world(world)
    approval(world, me, cyc, RDCT_TYPE_CD=kind)
    apply(world, row)
    assert rows(world, "SELECT RDCT_RSN FROM TB_ATNLC_APLY")[0]["RDCT_RSN"] == reason
    assert rows(world, "SELECT DCSN_RSN FROM TB_RDCT_HSTRY")[0]["DCSN_RSN"] == reason


def test_같은_기수의_두_번째_강좌에는_감면을_다시_쓰지_못한다(world: World) -> None:
    me, cyc, first = reduction_world(world)
    second = course(world, cyc, "두번째", TTCHG=100000)
    approval(world, me, cyc)
    assert apply(world, first).json()["reductionAmount"] == 50000
    body = apply(world, second).json()
    assert body["reductionAmount"] == 0 and body["payableAmount"] == 100000
    assert len(rows(world, "SELECT 1 FROM TB_RDCT_HSTRY")) == 1


def test_감면을_쓴_신청을_취소해도_감면은_돌아오지_않는다(world: World) -> None:
    me, cyc, first = reduction_world(world)
    second = course(world, cyc, "두번째", TTCHG=100000)
    approval(world, me, cyc)
    apply(world, first)
    world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CANCEL', RTRCN_DT=:n"), {"n": START})
    assert apply(world, second).json()["reductionAmount"] == 0


def test_담당자가_해제하면_다시_쓸_수_있다(world: World) -> None:
    me, cyc, first = reduction_world(world)
    second = course(world, cyc, "두번째", TTCHG=100000)
    approval(world, me, cyc)
    created = apply(world, first).json()
    world.db.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD='ES.CANCEL', RTRCN_DT=:n"), {"n": START})
    reduction_log(world, {"ATNLC_APLY_SN": int(created["applicationId"])}, "DR.REJECT")
    assert apply(world, second).json()["reductionAmount"] == 50000


def test_감면_없는_신청은_감면_이력을_남기지_않는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    apply(world, open_course(world))
    assert rows(world, "SELECT 1 FROM TB_RDCT_HSTRY") == []
    saved = rows(world, "SELECT * FROM TB_ATNLC_APLY")[0]
    assert saved["RDCT_AMT"] == 0 and saved["RDCT_RSN"] is None and saved["RDCT_MNGR_SN"] is None


def test_수강료가_0원이면_승인이_있어도_감면_이력을_남기지_않는다(world: World) -> None:
    me, cyc, _ = reduction_world(world)
    free = course(world, cyc, "무료", TTCHG=0)
    approval(world, me, cyc)
    apply(world, free)
    assert rows(world, "SELECT 1 FROM TB_RDCT_HSTRY") == []


# --- 멱등 -----------------------------------------------------------------------------------


def test_같은_키로_다시_보내면_같은_결과를_돌려주고_새_행을_만들지_않는다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    same = key()
    first, second = apply(world, row, same), apply(world, row, same)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["applicationId"] == second.json()["applicationId"]
    assert (
        count_applications(world) == 1
        and len(rows(world, "SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='APLY_CREATE'")) == 1
    )


def test_재전송은_그_사이_정원이_차거나_접수가_끝나도_이전_결과다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=0)
    same = key()
    first = apply(world, row, same).json()
    world.db.execute(text("UPDATE TB_CORS SET CORS_STTS_CD='CS.CLOSE'"))
    again = apply(world, row, same)
    assert again.status_code == 201 and again.json()["applicationId"] == first["applicationId"]


def test_같은_키로_다른_강좌를_보내면_409다(world: World) -> None:
    sign_in(world, **RESIDENT)
    one, two = open_course(world), open_course(world, CORS_NM="다른강좌")
    same = key()
    assert apply(world, one, same).status_code == 201
    response = apply(world, two, same)
    assert response.status_code == 409 and response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert count_applications(world) == 1


def test_다른_회원이_쓴_키를_쓰면_409다(world: World) -> None:
    other = make_member(world, "other", **RESIDENT)
    row = open_course(world)
    application(world, other, row, "ES.CONFIRM", IDEM_KEY="shared-key-0001")
    sign_in(world, **RESIDENT)
    response = apply(world, row, "shared-key-0001")
    assert response.status_code == 409 and response.json()["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("bad", ["short", "has space 12345", "x" * 65])
def test_멱등키_형식이_틀리면_400이다(world: World, bad: str) -> None:
    sign_in(world, **RESIDENT)
    assert apply(world, open_course(world), bad).status_code == 400


def test_멱등키가_없으면_400이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    response = world.client.post(
        f"{MEMBER}/me/applications",
        json={"courseId": str(row["CORS_SN"])},
        headers={"X-CSRF-Token": csrf(world)},
    )
    assert response.status_code == 400 and count_applications(world) == 0


def test_강좌_번호_형식이_틀리면_400이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    for body in ({"courseId": "abc"}, {"courseId": ""}, {}):
        response = world.client.post(
            f"{MEMBER}/me/applications",
            json=body,
            headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()},
        )
        assert response.status_code == 400


# --- 인증과 CSRF ---------------------------------------------------------------------------------


def test_로그인_없이는_401이다(world: World) -> None:
    row = open_course(world)
    response = world.client.post(
        f"{MEMBER}/me/applications",
        json={"courseId": str(row["CORS_SN"])},
        headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": key()},
    )
    assert response.status_code == 401 and count_applications(world) == 0


def test_CSRF_토큰이_없거나_틀리면_403이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    body = {"courseId": str(row["CORS_SN"])}
    missing = world.client.post(f"{MEMBER}/me/applications", json=body, headers={"Idempotency-Key": key()})
    wrong = world.client.post(
        f"{MEMBER}/me/applications", json=body, headers={"X-CSRF-Token": "x" * 40, "Idempotency-Key": key()}
    )
    assert missing.status_code == 403 and wrong.status_code == 403 and count_applications(world) == 0


def test_로그인_전에_받은_CSRF_토큰은_로그인_뒤에_쓸_수_없다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    anonymous = csrf(world)  # 로그인 상태에서 받은 올바른 토큰
    other = world.client.post(
        f"{MEMBER}/me/applications",
        json={"courseId": str(row["CORS_SN"])},
        headers={"X-CSRF-Token": anonymous + "0", "Idempotency-Key": key()},
    )
    assert other.status_code == 403


def test_신청_생성은_회원의_세션_유휴_시간을_연장한다(world: World) -> None:
    sign_in(world, **RESIDENT)
    row = open_course(world)
    world.clock.advance(minutes=20)
    assert apply(world, row).status_code == 201
    world.clock.advance(minutes=20)
    assert world.client.get(f"{MEMBER}/me/applications").status_code == 200


# --- 감사 ---------------------------------------------------------------------------------------


def test_신청_생성은_작업이력에_남고_멱등키는_남기지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    idem = key()
    created = apply(world, open_course(world), idem).json()
    log = rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD='APLY_CREATE'")
    assert len(log) == 1
    assert log[0]["ACTR_TYPE_CD"] == "AK.MEMBER" and log[0]["MBR_SN"] == me["MBR_SN"]
    assert log[0]["TRGT_TBL_NM"] == "TB_ATNLC_APLY" and log[0]["TRGT_KEY_VL"] == created["applicationId"]
    assert log[0]["JOB_RSLT_CD"] == "JR.SUCCESS" and idem not in str(log[0]["CHG_CN"])


# --- 다른 강좌·다른 묶음과 섞이지 않는다 -----------------------------------------------------------


def test_다른_강좌가_찼어도_이_강좌의_정원에는_영향이_없다(world: World) -> None:
    sign_in(world, **RESIDENT)
    full, roomy = (
        open_course(world, RCRT_NOPE=1, WTNG_NOPE=0),
        open_course(world, CORS_NM="여유", RCRT_NOPE=1),
    )
    fill(world, full, confirmed=1)
    assert apply(world, roomy).json()["status"] == "HOLD"


def test_다른_강좌의_대기자는_이_강좌의_대기_순번에_영향이_없다(world: World) -> None:
    sign_in(world, **RESIDENT)
    one, other = (
        open_course(world, RCRT_NOPE=1, WTNG_NOPE=5),
        open_course(world, CORS_NM="다른", RCRT_NOPE=1, WTNG_NOPE=5),
    )
    fill(world, one, confirmed=1)
    application(world, make_member(world, "far-waiter"), other, "ES.WAIT", WTNG_SEQ=7)
    body = apply(world, one).json()
    assert body["status"] == "WAITING" and body["waitingRank"] == 1
    mine = rows(
        world,
        "SELECT WTNG_SEQ FROM TB_ATNLC_APLY WHERE CORS_SN = :c AND APLY_STTS_CD = 'ES.WAIT'",
        c=one["CORS_SN"],
    )
    assert [r["WTNG_SEQ"] for r in mine] == [1]


def test_다른_운영묶음이_같은_멱등키를_썼어도_충돌이_아니다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    theirs_cycle = world.factory.make(
        "TB_EDU_CYCL",
        OPER_BNDL_SN=other,
        EDU_YR="2026",
        EDU_CYCL=9,
        EDU_CYCL_NM="남",
        EDU_BGNG_YMD="20261101",
        EDU_END_YMD="20261231",
        RCPT_BGNG_DT=START - DAY,
        RCPT_END_DT=START + DAY,
    )
    theirs = course(world, theirs_cycle, "남의", OPER_BNDL_SN=other)
    stranger = make_member(world, "stranger", OPER_BNDL_SN=other)
    application(world, stranger, theirs, "ES.CONFIRM", OPER_BNDL_SN=other, IDEM_KEY="shared-key-0009")
    sign_in(world, **RESIDENT)
    assert apply(world, open_course(world), "shared-key-0009").status_code == 201
