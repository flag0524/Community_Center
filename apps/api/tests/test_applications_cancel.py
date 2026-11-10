# 본인 신청 취소와 자리 반환 뒤 대기자 자동 승격(문자 아웃박스 포함)을 실제 앱과 MariaDB로 확인하는 시험
import hashlib
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.crypto import decrypt
from tests.test_applications_read import RESIDENT, application, payment, sign_in
from tests.test_applications_read import open_course as _open_course
from tests.world import MEMBER, START, World, make_admin, make_member

pytestmark = pytest.mark.db

DAY = timedelta(days=1)
PHONE = "01012345678"


def open_course(w: World, **values: Any) -> dict[str, Any]:
    """교육 시작 전의 강좌. 승격은 교육 시작일 전까지만 하므로 기본값을 미래로 둔다."""
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def csrf(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])


def cancel(w: World, app: dict[str, Any]) -> Any:
    return w.client.post(
        f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/cancel", headers={"X-CSRF-Token": csrf(w)}
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings().all())


def one(w: World, app: dict[str, Any]) -> Any:
    return rows(w, "SELECT * FROM TB_ATNLC_APLY WHERE ATNLC_APLY_SN = :s", s=app["ATNLC_APLY_SN"])[0]


def waiter(w: World, row: dict[str, Any], login: str, seq: int, **values: Any) -> dict[str, Any]:
    member = make_member(w, login, MBL_TELNO=PHONE, **RESIDENT)
    return application(w, member, row, "ES.WAIT", WTNG_SEQ=seq, **values)


# --- 취소 ---------------------------------------------------------------------------------


def test_대기_신청을_취소하면_순번이_사라지고_다른_대기자는_그대로다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    application(world, make_member(world, "holder"), row, "ES.CONFIRM")
    first = waiter(world, row, "w1", 1)
    mine = application(world, me, row, "ES.WAIT", WTNG_SEQ=2)
    behind = waiter(world, row, "w3", 3)
    response = cancel(world, mine)
    assert response.status_code == 200
    body = response.json()
    assert (
        body["status"] == "CANCELLED" and body["displayState"] == "CANCELLED" and body["waitingRank"] is None
    )
    assert body["canCancel"] is False and body["canPay"] is False
    saved = one(world, mine)
    assert saved["APLY_STTS_CD"] == "ES.CANCEL" and saved["WTNG_SEQ"] is None
    assert saved["RTRCN_DT"] == START and saved["RTRCN_RSN"] == "본인 취소"
    assert one(world, first)["APLY_STTS_CD"] == "ES.WAIT" and one(world, behind)["WTNG_SEQ"] == 3
    assert rows(world, "SELECT 1 FROM TB_SMS_DMND") == []  # 대기가 빠지는 것은 자리를 돌려주지 않는다


def test_결제대기를_취소하면_자리를_돌려주고_첫_대기자를_바로_배정한다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, CORS_NM="요가")
    mine = application(world, me, row, "ES.HOLD")
    first, second = waiter(world, row, "w1", 1), waiter(world, row, "w2", 2)
    world.clock.advance(minutes=3)
    assert cancel(world, mine).status_code == 200
    promoted, still = one(world, first), one(world, second)
    assert promoted["APLY_STTS_CD"] == "ES.HOLD" and promoted["WTNG_SEQ"] is None
    assert promoted["SEAT_ALTMNT_DT"] == START + timedelta(minutes=3)  # 새 배정 시각(SEAT-02)
    assert promoted["STLM_DDLN_DT"] == START + timedelta(minutes=13)  # 새 배정 시각부터 10분
    assert still["APLY_STTS_CD"] == "ES.WAIT" and still["WTNG_SEQ"] == 2
    assert one(world, mine)["SEAT_ALTMNT_DT"] == START  # 반환한 신청의 배정 시각은 지우지 않는다


def test_승격_안내_문자는_아웃박스에만_쌓고_개인정보를_담지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, CORS_NM="요가 초급")
    mine = application(world, me, row, "ES.HOLD")
    target = waiter(world, row, "w1", 1)
    cancel(world, mine)
    sms = rows(world, "SELECT * FROM TB_SMS_DMND")
    assert len(sms) == 1
    message = sms[0]["SMS_CN"]
    assert "요가 초급" in message and "결제해 주세요" in message
    assert "11월 09일 18시 10분까지" in message  # 기한 09:10 UTC는 한국 시각 18:10이다
    assert f"/me/applications/{target['ATNLC_APLY_SN']}" in message
    assert "김회원" not in message and PHONE not in message
    assert sms[0]["DMND_TYPE_CD"] == "SM.AUTO" and sms[0]["TRGT_TYPE_CD"] == "SG.EVENT"
    assert sms[0]["SRC_EVENT_ID"].startswith(f"PROMO:{target['ATNLC_APLY_SN']}:")
    assert sms[0]["DMND_HASH_VL"] == hashlib.sha256(message.encode()).hexdigest()
    targets = rows(world, "SELECT * FROM TB_SMS_TRGT")
    assert (
        len(targets) == 1
        and targets[0]["MBR_SN"] == target["MBR_SN"]
        and targets[0]["TRGT_STTS_CD"] == "SS.WAIT"
    )
    assert PHONE not in targets[0]["RCPTN_TELNO_ENCPT_VL"]
    assert decrypt(world.settings.secret_key, targets[0]["RCPTN_TELNO_ENCPT_VL"]) == PHONE


def test_결제가_없는_대기자는_승격되면_바로_수강확정이고_문자도_확정_안내다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    mine = application(world, me, row, "ES.HOLD")
    free = waiter(world, row, "free", 1, TTCHG_AMT=0, STLM_PRNMNT_AMT=0)
    cancel(world, mine)
    saved = one(world, free)
    assert (
        saved["APLY_STTS_CD"] == "ES.CONFIRM"
        and saved["STLM_DDLN_DT"] is None
        and saved["SEAT_ALTMNT_DT"] == START
    )
    message = rows(world, "SELECT SMS_CN FROM TB_SMS_DMND")[0]["SMS_CN"]
    assert "수강이 확정되었습니다" in message and "결제해 주세요" not in message


def test_승격된_신청은_내_신청에서_결제할_수_있는_상태로_보인다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    other = make_member(world, "next", MBL_TELNO=PHONE, **RESIDENT)
    application(world, other, row, "ES.WAIT", WTNG_SEQ=1)
    cancel(world, holder)
    world.client.cookies.clear()
    assert (
        world.client.post(
            f"{MEMBER}/auth/login",
            json={"loginId": "next", "password": "Correct-Horse-9"},
            headers={"X-CSRF-Token": csrf(world)},
        ).status_code
        == 200
    )
    body = world.client.get(f"{MEMBER}/me/applications").json()["items"][0]
    assert body["displayState"] == "PAYMENT_DUE" and body["canPay"] is True and body["waitingRank"] is None


def test_결제창만_발급된_결제는_함께_취소하고_다른_결제는_건드리지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    ready = payment(world, app, "PS.READY")
    failed = payment(world, app, "PS.FAIL")
    assert cancel(world, app).status_code == 200
    status = {
        r["STLM_SN"]: r["STLM_STTS_CD"] for r in rows(world, "SELECT STLM_SN, STLM_STTS_CD FROM TB_STLM")
    }
    assert status[ready["STLM_SN"]] == "PS.CANCEL" and status[failed["STLM_SN"]] == "PS.FAIL"


def test_승인_결과를_기다리는_결제가_있으면_취소할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    app = application(world, me, row, "ES.HOLD")
    pending = payment(world, app, "PS.PENDING")
    target = waiter(world, row, "w1", 1)
    response = cancel(world, app)
    assert response.status_code == 422 and response.json()["code"] == "PAY_RESULT_PENDING"
    assert one(world, app)["APLY_STTS_CD"] == "ES.HOLD" and one(world, target)["APLY_STTS_CD"] == "ES.WAIT"
    assert (
        rows(world, "SELECT STLM_STTS_CD FROM TB_STLM WHERE STLM_SN = :s", s=pending["STLM_SN"])[0][
            "STLM_STTS_CD"
        ]
        == "PS.PENDING"
    )


def test_결제한_수강확정은_취소가_아니라_환불로_안내한다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.CONFIRM")
    payment(world, app, "PS.PAID")
    response = cancel(world, app)
    assert response.status_code == 422 and response.json()["code"] == "APLY_CANCEL_NOT_ALLOWED"
    assert one(world, app)["APLY_STTS_CD"] == "ES.CONFIRM"


def test_결제_없는_확정은_개강_전에_취소하고_자리를_돌려준다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261110")
    free = application(world, me, row, "ES.CONFIRM", TTCHG_AMT=0, STLM_PRNMNT_AMT=0)
    target = waiter(world, row, "w1", 1)
    assert cancel(world, free).status_code == 200
    assert one(world, free)["APLY_STTS_CD"] == "ES.CANCEL" and one(world, target)["APLY_STTS_CD"] == "ES.HOLD"


def test_개강일_당일부터는_결제_없는_확정도_취소할_수_없다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, EDU_BGNG_YMD="20261109")  # 한국 날짜로 오늘
    free = application(world, me, row, "ES.CONFIRM", TTCHG_AMT=0, STLM_PRNMNT_AMT=0)
    response = cancel(world, free)
    assert response.status_code == 422 and response.json()["code"] == "APLY_CANCEL_NOT_ALLOWED"


@pytest.mark.parametrize("state", ["ES.EXPIRE", "ES.COMPLETE"])
def test_만료_종료된_신청은_취소할_수_없다(world: World, state: str) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), state)
    response = cancel(world, app)
    assert response.status_code == 422 and response.json()["code"] == "APLY_CANCEL_NOT_ALLOWED"
    assert one(world, app)["APLY_STTS_CD"] == state


def test_이미_취소한_신청을_다시_취소해도_같은_결과이고_또_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    mine = application(world, me, row, "ES.HOLD")
    waiter(world, row, "w1", 1)
    waiter(world, row, "w2", 2)
    first, second = cancel(world, mine), cancel(world, mine)
    assert first.status_code == second.status_code == 200 and second.json()["status"] == "CANCELLED"
    assert len(rows(world, "SELECT 1 FROM TB_ATNLC_APLY WHERE APLY_STTS_CD = 'ES.HOLD'")) == 1  # 한 명만 승격
    assert (
        len(
            rows(
                world,
                "SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_CANCEL' AND ACTR_TYPE_CD = 'AK.MEMBER'",
            )
        )
        == 1
    )


def test_남의_신청_없는_신청은_404이고_형식이_틀리면_400이다(world: World) -> None:
    sign_in(world, **RESIDENT)
    theirs = application(world, make_member(world, "stranger"), open_course(world), "ES.HOLD")
    assert cancel(world, theirs).status_code == 404
    assert one(world, theirs)["APLY_STTS_CD"] == "ES.HOLD"
    assert cancel(world, {"ATNLC_APLY_SN": 99999999}).status_code == 404
    assert (
        world.client.post(
            f"{MEMBER}/me/applications/abc/cancel", headers={"X-CSRF-Token": csrf(world)}
        ).status_code
        == 400
    )


def test_로그인과_CSRF_토큰이_없으면_취소할_수_없다(world: World) -> None:
    anonymous = world.client.post(f"{MEMBER}/me/applications/1/cancel", headers={"X-CSRF-Token": csrf(world)})
    assert anonymous.status_code == 401
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    world.db.commit()  # 시험 세계의 세션 트랜잭션이 팩토리 삽입과 겹치지 않게 확정한다
    missing = world.client.post(f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/cancel")
    wrong = world.client.post(
        f"{MEMBER}/me/applications/{app['ATNLC_APLY_SN']}/cancel", headers={"X-CSRF-Token": "x" * 40}
    )
    assert missing.status_code == wrong.status_code == 403 and one(world, app)["APLY_STTS_CD"] == "ES.HOLD"


def test_취소는_작업이력에_남는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    app = application(world, me, open_course(world), "ES.HOLD")
    cancel(world, app)
    log = rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_CANCEL'")
    assert len(log) == 1 and log[0]["ACTR_TYPE_CD"] == "AK.MEMBER" and log[0]["MBR_SN"] == me["MBR_SN"]
    assert log[0]["TRGT_KEY_VL"] == str(app["ATNLC_APLY_SN"]) and "ES.HOLD" in log[0]["CHG_CN"]


# --- 승격 규칙 ----------------------------------------------------------------------------------


def test_자리가_여럿_나면_대기_순서대로_그만큼_승격한다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=3, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")  # 정원을 늘린 뒤라 자리가 3개 비게 되는 상황
    ws = [waiter(world, row, f"w{n}", n) for n in range(1, 5)]
    cancel(world, holder)
    states = [one(world, w)["APLY_STTS_CD"] for w in ws]
    assert states == ["ES.HOLD", "ES.HOLD", "ES.HOLD", "ES.WAIT"]
    assert len(rows(world, "SELECT 1 FROM TB_SMS_DMND")) == 3


def test_대기_순서가_같으면_신청_번호가_빠른_쪽이_먼저다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    early, late = waiter(world, row, "early", 4), waiter(world, row, "late", 4)
    cancel(world, holder)
    assert one(world, early)["APLY_STTS_CD"] == "ES.HOLD" and one(world, late)["APLY_STTS_CD"] == "ES.WAIT"


@pytest.mark.parametrize("state", ["MS.LOCKED", "MS.WITHDRAW"])
def test_순서가_된_회원이_탈퇴_제한이면_취소하고_다음_대기자에게_넘긴다(world: World, state: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    gone = waiter(world, row, "gone", 1)
    nxt = waiter(world, row, "next", 2)
    world.db.execute(
        text("UPDATE TB_MBR SET MBR_STTS_CD = :s WHERE MBR_SN = :m"), {"s": state, "m": gone["MBR_SN"]}
    )
    cancel(world, holder)
    lost = one(world, gone)
    assert (
        lost["APLY_STTS_CD"] == "ES.CANCEL" and lost["RTRCN_RSN"] == "자격 상실" and lost["WTNG_SEQ"] is None
    )
    assert one(world, nxt)["APLY_STTS_CD"] == "ES.HOLD"
    assert len(rows(world, "SELECT 1 FROM TB_SMS_DMND")) == 1  # 자격 없는 회원에게는 문자를 보내지 않는다


def test_교육_시작일_전이면_접수가_끝나도_승격한다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, RCPT_END_DT=START - DAY, EDU_BGNG_YMD="20261110")
    holder = application(world, me, row, "ES.HOLD")
    target = waiter(world, row, "w1", 1)
    cancel(world, holder)
    assert one(world, target)["APLY_STTS_CD"] == "ES.HOLD"


def test_교육_시작일부터는_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261109")
    holder = application(world, me, row, "ES.HOLD")
    target = waiter(world, row, "w1", 1)
    assert cancel(world, holder).status_code == 200
    assert one(world, target)["APLY_STTS_CD"] == "ES.WAIT" and rows(world, "SELECT 1 FROM TB_SMS_DMND") == []


def test_한국_날짜로_시작일_하루_전까지는_승격한다(world: World) -> None:
    # 2026-11-09 14:59 UTC는 한국 시각 23:59로 아직 11월 9일이다. 교육 시작이 11월 10일이면 승격한다
    world.clock.now = START.replace(hour=14, minute=59)
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, EDU_BGNG_YMD="20261110", RCPT_END_DT=START + DAY)
    holder = application(world, me, row, "ES.HOLD", STLM_DDLN_DT=world.clock.now + timedelta(minutes=10))
    target = waiter(world, row, "w1", 1)
    cancel(world, holder)
    assert one(world, target)["APLY_STTS_CD"] == "ES.HOLD"
    world.clock.now = START.replace(hour=15, minute=0)  # 한국 시각 자정을 넘기면 11월 10일이다


def test_수신번호가_없는_회원은_승격하되_문자는_쌓지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    nophone = make_member(world, "nophone", MBL_TELNO=None, **RESIDENT)
    target = application(world, nophone, row, "ES.WAIT", WTNG_SEQ=1)
    cancel(world, holder)
    assert one(world, target)["APLY_STTS_CD"] == "ES.HOLD"
    assert rows(world, "SELECT 1 FROM TB_SMS_DMND") == []
    note = rows(world, "SELECT CHG_CN FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_PROMOTE'")[0]["CHG_CN"]
    assert "문자 제외" in note


def test_승격은_시스템_작업으로_작업이력에_남는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    target = waiter(world, row, "w1", 1)
    cancel(world, holder)
    log = rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_PROMOTE'")
    assert len(log) == 1 and log[0]["ACTR_TYPE_CD"] == "AK.SYSTEM" and log[0]["MBR_SN"] is None  # R21
    assert log[0]["TRGT_KEY_VL"] == str(target["ATNLC_APLY_SN"])


def test_다른_강좌의_대기자는_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    other = open_course(world, CORS_NM="다른강좌", RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    stranger = waiter(world, other, "elsewhere", 1)
    cancel(world, holder)
    assert one(world, stranger)["APLY_STTS_CD"] == "ES.WAIT"


def test_취소로_자리가_나도_정원이_찬_다른_신청이_있으면_초과해서_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=2, WTNG_NOPE=5)
    application(world, make_member(world, "keeper"), row, "ES.CONFIRM")
    holder = application(world, me, row, "ES.HOLD")
    ws = [waiter(world, row, f"w{n}", n) for n in (1, 2)]
    cancel(world, holder)
    assert [one(world, w)["APLY_STTS_CD"] for w in ws] == ["ES.HOLD", "ES.WAIT"]  # 자리는 하나만 났다


def test_취소한_뒤에는_같은_강좌에_새로_신청할_수_있다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    app = application(world, me, row, "ES.HOLD")
    cancel(world, app)
    response = world.client.post(
        f"{MEMBER}/me/applications",
        json={"courseId": str(row["CORS_SN"])},
        headers={"X-CSRF-Token": csrf(world), "Idempotency-Key": "again-key-0001"},
    )
    assert response.status_code == 201 and response.json()["applicationId"] != str(app["ATNLC_APLY_SN"])


def test_다른_신청의_결제창_발급분은_취소하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world)
    mine = application(world, me, row, "ES.HOLD")
    theirs = application(world, make_member(world, "other"), row, "ES.HOLD")
    payment(world, mine, "PS.READY")
    other_ready = payment(world, theirs, "PS.READY")
    assert cancel(world, mine).status_code == 200
    status = rows(world, "SELECT STLM_STTS_CD FROM TB_STLM WHERE STLM_SN = :s", s=other_ready["STLM_SN"])[0]
    assert status["STLM_STTS_CD"] == "PS.READY"


def test_대기_신청의_취소는_자리를_돌려주는_것이_아니라서_승격하지_않는다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(
        world, RCRT_NOPE=3, WTNG_NOPE=5
    )  # 자리가 비어 있어도 대기 취소가 승격을 일으키지는 않는다
    first = waiter(world, row, "w1", 1)
    mine = application(world, me, row, "ES.WAIT", WTNG_SEQ=2)
    assert cancel(world, mine).status_code == 200
    assert one(world, first)["APLY_STTS_CD"] == "ES.WAIT" and rows(world, "SELECT 1 FROM TB_SMS_DMND") == []


@pytest.mark.parametrize("course_state", ["CS.CANCEL", "CS.END", "CS.DRAFT"])
def test_폐강되거나_끝난_강좌에서는_취소해도_승격하지_않는다(world: World, course_state: str) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5, CORS_STTS_CD=course_state)
    holder = application(world, me, row, "ES.HOLD")
    target = waiter(world, row, "w1", 1)
    assert cancel(world, holder).status_code == 200
    assert one(world, target)["APLY_STTS_CD"] == "ES.WAIT" and rows(world, "SELECT 1 FROM TB_SMS_DMND") == []


def test_수강료가_있어도_결제예정이_0원인_대기자는_승격되면_바로_확정된다(world: World) -> None:
    me = sign_in(world, **RESIDENT)
    row = open_course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    holder = application(world, me, row, "ES.HOLD")
    reviewer = make_admin(world, "free-reviewer")["MNGR_SN"]
    target = waiter(
        world,
        row,
        "full-reduction",
        1,
        TTCHG_AMT=30000,
        RDCT_AMT=30000,
        STLM_PRNMNT_AMT=0,
        RDCT_RSN="전액 감면",
        RDCT_MNGR_SN=reviewer,
    )
    cancel(world, holder)
    saved = one(world, target)
    assert saved["APLY_STTS_CD"] == "ES.CONFIRM" and saved["STLM_DDLN_DT"] is None
