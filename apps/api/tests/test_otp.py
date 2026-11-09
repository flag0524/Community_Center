# 본인확인 OTP 발급·확인(6자리·5분·실패 5회·재전송 60초, 계정 존재 숨기기, 원문 비저장, 문자 기록)을 확인하는 시험
import logging
import re
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.adapters.sms.base import SendOutcome
from app.auth.crypto import DecryptError, decrypt, encrypt
from app.auth.otp import code_hash, gate_blocks, make_gate, new_code
from app.db import tables
from tests.world import MEMBER, START, World, anonymous_token, make_member

pytestmark = pytest.mark.db

PHONE = "01012345678"


def request_otp(w: World, purpose: str = "JOIN", phone: str = PHONE, **extra: Any) -> Any:
    token = anonymous_token(w.client, MEMBER)
    body = {"purpose": purpose, "phone": phone, **extra}
    return w.client.post(f"{MEMBER}/auth/otp", json=body, headers={"X-CSRF-Token": token})


def sent_code(w: World) -> str:
    """모의 발송기가 받은 마지막 문자에서 인증번호를 읽는다. 서버 DB에는 원문이 없다."""
    found = re.search(r"\d{6}", w.sms.outbox[-1].text)
    assert found
    return found.group(0)


def verify(w: World, cert_id: str, code: str) -> Any:
    token = w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"]
    return w.client.post(
        f"{MEMBER}/auth/otp/verify",
        json={"certRequestId": cert_id, "code": code},
        headers={"X-CSRF-Token": token},
    )


def cert_row(w: World, cert_id: str) -> Any:
    return w.db.execute(
        select(tables.TB_CERT_DMND).where(tables.TB_CERT_DMND.c.CERT_DMND_SN == int(cert_id))
    ).one()


# --- 발급 ----------------------------------------------------------------------


def test_가입_인증은_회원_없이_발급되고_문자가_나가며_만료와_재전송_시각을_준다(world: World) -> None:
    response = request_otp(world, name="김가입")
    assert response.status_code == 200
    body = response.json()
    assert body["expiresAt"].startswith("2026-11-09T09:05:00") and body["resendAvailableAt"].startswith(
        "2026-11-09T09:01:00"
    )
    assert len(world.sms.outbox) == 1
    message = world.sms.outbox[0]
    assert message.to == PHONE and message.sender == "TBD"  # 발신번호는 미정이라 값을 지어내지 않았다
    assert "인증번호는" in message.text and "5분" in message.text and "{code}" not in message.text
    row = cert_row(world, body["certRequestId"])
    assert (row.CERT_PRPS_CD, row.MBR_SN, int(row.FAIL_NMTM)) == ("AP.JOIN", None, 0)
    assert row.KEY_VER_ID == "v1" and row.CERT_USE_CMPTN_DT is None


def test_인증번호_원문은_DB와_로그와_저장된_문안에_남지_않는다(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        body = request_otp(world).json()
    code = sent_code(world)
    assert re.fullmatch(r"\d{6}", code)
    dump = world.db.execute(
        text(
            "SELECT CONCAT_WS('|', c.OTP_HASH_VL, c.TELNO_ENCPT_VL, c.CERT_DMND_ID, d.SMS_CN, t.RCPTN_TELNO_ENCPT_VL, "
            "COALESCE(h.SPLR_MSG_ID,''), COALESCE(h.FAIL_CD,'')) FROM TB_CERT_DMND c "
            "JOIN TB_SMS_DMND d ON d.SRC_EVENT_ID = CONCAT('CERT:', c.CERT_DMND_SN) "
            "JOIN TB_SMS_TRGT t ON t.SMS_DMND_SN = d.SMS_DMND_SN "
            "LEFT JOIN TB_SMS_SNDNG_HSTRY h ON h.SMS_TRGT_SN = t.SMS_TRGT_SN"
        )
    ).scalar_one()
    assert code not in str(dump)  # 인증번호 원문은 어디에도 없다
    assert "{code}" in str(dump)  # 저장 문안은 코드 자리만 비워 둔 템플릿이다
    assert PHONE not in str(dump)  # 전화번호는 암호문이다
    assert code not in " ".join(r.getMessage() for r in caplog.records)
    assert body["certRequestId"]


def test_전화번호는_AES_암호문으로_저장되고_복호화하면_원래_값이_나온다(world: World) -> None:
    body = request_otp(world, name="김가입").json()
    stored = cert_row(world, body["certRequestId"]).TELNO_ENCPT_VL
    assert stored.startswith("v1:") and PHONE not in stored
    import json

    assert json.loads(decrypt(world.settings.secret_key, stored)) == {"p": PHONE, "n": "김가입"}
    assert encrypt("k" * 40, "같은 값") != encrypt("k" * 40, "같은 값")  # 같은 값도 매번 다른 암호문
    with pytest.raises(DecryptError):
        decrypt("다른" * 20, stored)  # 다른 키로는 열리지 않는다
    with pytest.raises(DecryptError):
        decrypt(world.settings.secret_key, stored[:-4] + "AAAA")  # 변조하면 열리지 않는다


def test_문자_요청과_수신_대상과_발송_이력이_남고_공급자_접수는_발송중으로_기록한다(world: World) -> None:
    request_otp(world)
    dmnd = world.db.execute(select(tables.TB_SMS_DMND)).one()
    assert (dmnd.DMND_TYPE_CD, dmnd.TRGT_TYPE_CD, dmnd.DSPTCH_TELNO) == (
        "SM.AUTO",
        "SG.EVENT",
        "TBD",
    )  # 발신번호는 미정
    target = world.db.execute(select(tables.TB_SMS_TRGT)).one()
    assert target.MBR_SN is None and target.CERT_DMND_SN is not None  # 가입은 회원이 없어 인증 요청에 연결
    history = world.db.execute(select(tables.TB_SMS_SNDNG_HSTRY)).one()
    assert (history.PRCS_STTS_CD, int(history.SNDNG_SEQ), history.SPLR_NM) == ("SS.SENDING", 1, "mock")
    assert target.TRGT_STTS_CD == "SS.SENDING"  # 최종 성공(SS.SENT)은 공급자 조회 뒤 워커가 확정한다


def test_공급자가_거절하면_실패를_기록하고_오류로_답하며_자동으로_다시_보내지_않는다(world: World) -> None:
    world.sms.next_outcome = SendOutcome.REJECTED
    response = request_otp(world)
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert world.sms.outbox == []
    history = world.db.execute(select(tables.TB_SMS_SNDNG_HSTRY)).one()
    assert (history.PRCS_STTS_CD, history.FAIL_CD) == (
        "SS.FAIL",
        "MOCK_REJECTED",
    )  # 오류 응답에도 기록은 남는다
    count = world.db.execute(select(func.count()).select_from(tables.TB_SMS_SNDNG_HSTRY)).scalar_one()
    assert count == 1  # 재시도 행이 자동으로 생기지 않았다


def test_결과를_알_수_없으면_알_수_없음으로_기록한다(world: World) -> None:
    world.sms.next_outcome = SendOutcome.UNKNOWN
    response = request_otp(world)
    assert response.status_code == 200  # 사용자는 다시 요청할 수 있다
    history = world.db.execute(select(tables.TB_SMS_SNDNG_HSTRY)).one()
    assert history.PRCS_STTS_CD == "SS.UNKNOWN"


# --- 계정 존재 숨기기 ------------------------------------------------------------


def test_아이디_찾기는_일치하는_회원이_있든_없든_같은_모양으로_답한다(world: World) -> None:
    member = make_member(world, "found", MBL_TELNO=PHONE, MBR_NM="김회원")
    hit = request_otp(world, "ID_FIND", PHONE, name="김회원")
    world.client.cookies.clear()
    miss = request_otp(world, "ID_FIND", "01099998888", name="없는사람")
    assert hit.status_code == miss.status_code == 200
    assert set(hit.json()) == set(miss.json())
    assert len(world.sms.outbox) == 1  # 일치하는 회원에게만 문자가 간다
    real = cert_row(world, hit.json()["certRequestId"])
    decoy = cert_row(world, miss.json()["certRequestId"])
    assert member["MBR_SN"] == real.MBR_SN and decoy.MBR_SN is None


def test_없는_대상의_인증도_확인하면_실제와_같은_모양으로_실패한다(world: World) -> None:
    make_member(world, "found", MBL_TELNO=PHONE, MBR_NM="김회원")
    real = request_otp(world, "ID_FIND", PHONE, name="김회원").json()["certRequestId"]
    world.client.cookies.clear()
    fake = request_otp(world, "ID_FIND", "01099998888", name="없는사람").json()["certRequestId"]
    wrong_real = verify(world, real, "000000" if sent_code(world) != "000000" else "111111")
    wrong_fake = verify(world, fake, "123456")
    assert wrong_real.status_code == wrong_fake.status_code == 200
    assert wrong_real.json() == wrong_fake.json() == {"verified": False, "remainingAttempts": 4}


def test_가짜_인증에는_맞는_코드가_없어_어떤_코드도_통과하지_못한다(world: World) -> None:
    fake = request_otp(world, "ID_FIND", "01099998888", name="없는사람").json()["certRequestId"]
    results = {verify(world, fake, f"{n:06d}").json().get("verified") for n in range(0, 4)}
    assert results == {False}


def test_비밀번호_재설정은_아이디와_전화번호가_함께_맞아야_대상이_된다(world: World) -> None:
    make_member(world, "found", MBL_TELNO=PHONE, MBR_NM="김회원")
    wrong_id = request_otp(world, "PASSWORD_RESET", PHONE, loginId="other")
    assert wrong_id.status_code == 200 and world.sms.outbox == []
    world.client.cookies.clear()
    ok = request_otp(world, "PASSWORD_RESET", PHONE, loginId="found")
    assert ok.status_code == 200 and len(world.sms.outbox) == 1


def test_탈퇴한_회원은_대상이_되지_않는다(world: World) -> None:
    make_member(world, "gone", MBL_TELNO=PHONE, MBR_NM="김회원", MBR_STTS_CD="MS.WITHDRAW")
    assert request_otp(world, "ID_FIND", PHONE, name="김회원").status_code == 200
    assert world.sms.outbox == []


def test_아이디_찾기에는_이름이_비밀번호_재설정에는_아이디가_필요하다(world: World) -> None:
    assert request_otp(world, "ID_FIND", PHONE).status_code == 400
    assert request_otp(world, "PASSWORD_RESET", PHONE).status_code == 400


def test_전화번호_변경_목적은_아직_구현되지_않았다(world: World) -> None:
    assert request_otp(world, "PHONE_CHANGE").status_code == 501


# --- 재전송 60초 -------------------------------------------------------------------


def test_가입_인증은_쿠키로_60초_안에_다시_요청할_수_없다(world: World) -> None:
    assert request_otp(world).status_code == 200
    world.clock.advance(seconds=59)
    second = request_otp(world)
    assert second.status_code == 429 and second.json()["code"] == "OTP_RESEND_TOO_SOON"
    assert len(world.sms.outbox) == 1  # 제한된 요청은 문자를 보내지 않는다
    world.clock.advance(seconds=1)
    assert request_otp(world).status_code == 200


def test_회원_대상_인증은_쿠키를_지워도_DB의_직전_요청으로_60초_제한이_걸린다(world: World) -> None:
    make_member(world, "found", MBL_TELNO=PHONE, MBR_NM="김회원")
    assert request_otp(world, "ID_FIND", PHONE, name="김회원").status_code == 200
    world.client.cookies.clear()  # 쿠키 제한을 우회해도
    world.clock.advance(seconds=30)
    again = request_otp(world, "ID_FIND", PHONE, name="김회원")
    assert again.status_code == 429 and len(world.sms.outbox) == 1  # 피해자에게 문자가 쏟아지지 않는다
    world.client.cookies.clear()
    world.clock.advance(seconds=31)
    assert request_otp(world, "ID_FIND", PHONE, name="김회원").status_code == 200


def test_위조하거나_손상된_재전송_쿠키는_제한을_우회하는_값으로_쓰이지_않는다() -> None:
    secret = "s" * 40
    valid = make_gate(secret, START)
    assert gate_blocks(secret, valid, START)
    assert not gate_blocks(
        secret, valid.replace(valid.split(".")[1][:4], "ffff"), START
    )  # 서명이 틀리면 무시
    assert not gate_blocks(secret, "abc", START) and not gate_blocks(secret, None, START)
    assert not gate_blocks("x" * 40, valid, START)  # 다른 비밀키로 만든 값은 통하지 않는다
    assert not gate_blocks(secret, valid, START.replace(minute=2))  # 60초가 지나면 풀린다


# --- 확인 ----------------------------------------------------------------------


def test_맞는_코드는_verified_true이고_사용_완료로_표시하지_않는다(world: World) -> None:
    cert = request_otp(world).json()["certRequestId"]
    ok = verify(world, cert, sent_code(world))
    assert ok.status_code == 200 and ok.json() == {"verified": True, "remainingAttempts": None}
    assert cert_row(world, cert).CERT_USE_CMPTN_DT is None  # 최종 업무 API가 다시 검증하고 표시한다
    assert verify(world, cert, sent_code(world)).json()["verified"] is True  # 확인은 여러 번 해도 같다


def test_틀린_코드는_횟수를_세고_5번째에_무효가_된다(world: World) -> None:
    cert = request_otp(world).json()["certRequestId"]
    real = sent_code(world)
    wrong = "000000" if real != "000000" else "111111"
    results = [verify(world, cert, wrong).json() for _ in range(5)]
    assert [r["remainingAttempts"] for r in results] == [4, 3, 2, 1, 0]
    assert all(r["verified"] is False for r in results)
    blocked = verify(world, cert, real)  # 5번 틀린 뒤에는 맞는 코드도 쓸 수 없다
    assert blocked.status_code == 422 and blocked.json()["code"] == "OTP_INVALID"


def test_틀린_횟수는_응답이_오류가_아니어도_저장된다(world: World) -> None:
    cert = request_otp(world).json()["certRequestId"]
    real = sent_code(world)
    verify(world, cert, "000000" if real != "000000" else "111111")
    assert int(cert_row(world, cert).FAIL_NMTM) == 1


def test_5분이_지나면_만료되고_정확히_5분_직전까지는_유효하다(world: World) -> None:
    cert = request_otp(world).json()["certRequestId"]
    code = sent_code(world)
    world.clock.advance(minutes=4, seconds=59)
    assert verify(world, cert, code).json()["verified"] is True
    world.clock.advance(seconds=1)
    expired = verify(world, cert, code)
    assert expired.status_code == 422 and expired.json()["code"] == "OTP_EXPIRED"


def test_없는_인증_번호와_사용한_인증은_무효다(world: World) -> None:
    assert verify(world, "999999999", "123456").json()["code"] == "OTP_INVALID"
    cert = request_otp(world).json()["certRequestId"]
    world.db.execute(
        tables.TB_CERT_DMND.update()
        .where(tables.TB_CERT_DMND.c.CERT_DMND_SN == int(cert))
        .values(CERT_USE_CMPTN_DT=START)
    )
    assert verify(world, cert, sent_code(world)).json()["code"] == "OTP_INVALID"


def test_코드_형식이_틀리면_검증_오류다(world: World) -> None:
    cert = request_otp(world).json()["certRequestId"]
    assert verify(world, cert, "12345").status_code == 400
    assert verify(world, cert, "abcdef").status_code == 400


# --- 보안 입력 -----------------------------------------------------------------


def test_CSRF_토큰이_없으면_발급도_확인도_403이다(world: World) -> None:
    world.client.get(f"{MEMBER}/auth/session")
    assert (
        world.client.post(f"{MEMBER}/auth/otp", json={"purpose": "JOIN", "phone": PHONE}).status_code == 403
    )
    assert (
        world.client.post(
            f"{MEMBER}/auth/otp/verify", json={"certRequestId": "1", "code": "123456"}
        ).status_code
        == 403
    )
    assert world.sms.outbox == []


def test_휴대전화_형식이_틀리면_400이고_문자를_보내지_않는다(world: World) -> None:
    assert request_otp(world, phone="02-123-4567").status_code == 400
    assert world.sms.outbox == []


def test_인증번호는_6자리_숫자이고_분포가_고르다() -> None:
    codes = [new_code() for _ in range(2000)]
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
    assert len(set(codes)) > 1900  # 거의 겹치지 않는다
    assert any(c.startswith("0") for c in codes)  # 앞자리 0도 나온다(6자리 고정)


def test_검증값은_요청과_코드에_묶여_다른_요청의_같은_코드는_다른_값이다() -> None:
    secret = "s" * 40
    assert code_hash(secret, "a", "123456") != code_hash(secret, "b", "123456")
    assert code_hash(secret, "a", "123456") != code_hash("t" * 40, "a", "123456")
    assert code_hash(secret, "a", "123456") == code_hash(secret, "a", "123456")


def test_아이디_중복_확인은_로그인_없이_가능하고_존재만_알려_준다(world: World) -> None:
    make_member(world, "taken")
    assert world.client.get(f"{MEMBER}/join/check-id", params={"loginId": "taken"}).json() == {
        "available": False
    }
    assert world.client.get(f"{MEMBER}/join/check-id", params={"loginId": "fresh"}).json() == {
        "available": True
    }


def test_문자는_인증_요청을_커밋한_뒤에_보내고_공급자_호출은_트랜잭션_밖이다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공급자 호출이 길어져도 DB 잠금을 쥐고 있지 않게, 문자를 보내는 순간 요청 행이 이미 확정돼 있어야 한다."""
    token = anonymous_token(world.client, MEMBER)  # 이 GET의 커밋이 순서 판정에 섞이지 않게 감시 전에 끝낸다
    events: list[str] = []
    original_commit = world.db.commit
    original_send = world.sms.send

    def spy_commit() -> None:
        events.append("commit")
        original_commit()

    def spy_send(**kwargs: Any) -> Any:
        events.append("send")
        return original_send(**kwargs)

    monkeypatch.setattr(world.db, "commit", spy_commit)
    monkeypatch.setattr(world.sms, "send", spy_send)
    body = {"purpose": "JOIN", "phone": PHONE}
    assert (
        world.client.post(f"{MEMBER}/auth/otp", json=body, headers={"X-CSRF-Token": token}).status_code == 200
    )
    # 서비스가 문자를 보내기 전에 한 번 확정하고, 요청이 끝날 때 결과 기록을 다시 확정한다
    assert events == ["commit", "send", "commit"]


def test_공급자_호출_뒤에도_발송_이력이_저장된다(world: World) -> None:
    """발송 결과 기록은 커밋 뒤의 별도 쓰기라 응답 처리 중에 사라지지 않는다."""
    request_otp(world)
    assert world.db.execute(select(func.count()).select_from(tables.TB_SMS_SNDNG_HSTRY)).scalar_one() == 1
