# 가입(약관 동의·인증 소비의 원자성)과 아이디 찾기·비밀번호 재설정(세션 폐기)을 실제 앱과 MariaDB로 확인하는 시험
import hashlib
import re
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.auth.passwords import verify_password
from app.db import tables
from tests.test_otp import PHONE, cert_row, request_otp, sent_code
from tests.world import ITERATIONS, MEMBER, PASSWORD, START, World, login, make_member

pytestmark = pytest.mark.db

NEW_PASSWORD = "Brand-New-Pass-77"
TERMS_BODY = "이용약관 본문입니다."
PRIVACY_BODY = "개인정보 수집·이용 동의 본문입니다."
MARKET_BODY = "마케팅 정보 수신 동의 본문입니다."


def publish(
    w: World,
    content_type: str,
    content_id: str,
    body: str,
    *,
    essential: bool,
    version: str = "v1",
    **extra: Any,
) -> dict[str, Any]:
    """게시 중인 약관 문안을 만든다. 해시는 본문의 SHA-256으로 고정한다(R17)."""
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "CONTS_TYPE_CD": content_type,
        "CONTS_ID": content_id,
        "CONTS_TTL": content_id,
        "CONTS_CN": body,
        "VER_NM": version,
        "CONTS_HASH_VL": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "PSTG_YN": "Y",
        "ESNTL_YN": "Y" if essential else "N",
    }
    return w.factory.make("TB_SITE_CONTS", **{**defaults, **extra})  # 시험이 넘긴 값이 기본값을 이긴다


def publish_defaults(w: World) -> dict[str, dict[str, Any]]:
    return {
        "terms": publish(w, "CT.TERMS", "terms", TERMS_BODY, essential=True),
        "privacy": publish(w, "CT.PRIVACY", "privacy", PRIVACY_BODY, essential=True),
        "market": publish(w, "CT.MARKET", "market", MARKET_BODY, essential=False),
    }


def agreements(
    *, marketing: bool | None = None, terms: bool = True, privacy: bool = True, version: str = "v1"
) -> list[dict[str, Any]]:
    items = [
        {"termType": "TERMS_OF_USE", "version": version, "agreed": terms},
        {"termType": "PRIVACY_CONSENT", "version": version, "agreed": privacy},
    ]
    if marketing is not None:
        items.append({"termType": "MARKETING_CONSENT", "version": version, "agreed": marketing})
    return items


def csrf(w: World) -> str:
    return str(w.client.get(f"{MEMBER}/auth/session").json()["csrfToken"])


def join(
    w: World,
    cert_id: str,
    code: str,
    login_id: str = "newbie",
    password: str = "Strong-Pass-12",
    **extra: Any,
) -> Any:
    body = {
        "certRequestId": cert_id,
        "code": code,
        "loginId": login_id,
        "password": password,
        "email": "new@example.com",
        "agreements": agreements(),
        **extra,
    }
    return w.client.post(f"{MEMBER}/join", json=body, headers={"X-CSRF-Token": csrf(w)})


def issue_join(w: World, name: str = "김가입") -> tuple[str, str]:
    cert = request_otp(w, "JOIN", name=name).json()["certRequestId"]
    return str(cert), sent_code(w)


def member_count(w: World, login_id: str) -> int:
    return int(
        w.db.execute(
            select(func.count()).select_from(tables.TB_MBR).where(tables.TB_MBR.c.LGN_ID == login_id)
        ).scalar_one()
    )


# --- 가입 ----------------------------------------------------------------------


def test_가입하면_회원이_만들어지고_인증이_사용_완료로_표시되며_약관_동의가_해시와_함께_남는다(
    world: World,
) -> None:
    docs = publish_defaults(world)
    cert, code = issue_join(world)
    response = join(world, cert, code, agreements=agreements(marketing=True))
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["loginId"]) == ("김가입", "newbie") and re.fullmatch(r"\d+", body["memberId"])

    member = world.db.execute(select(tables.TB_MBR).where(tables.TB_MBR.c.LGN_ID == "newbie")).one()
    assert (member.MBL_TELNO, member.EML_ADDR, member.MBR_STTS_CD, member.MBR_TYPE_CD) == (
        PHONE,
        "new@example.com",
        "MS.ACTIVE",
        "MT.GEN",
    )
    assert member.OPER_BNDL_SN == world.bundle
    assert verify_password("Strong-Pass-12", member.PSWD_HASH_VL) and member.PSWD_HASH_VL.startswith(
        "pbkdf2_sha256$"
    )
    assert member.MBR_JOIN_DT == START  # 앱 시계

    assert cert_row(world, cert).CERT_USE_CMPTN_DT == START  # 같은 트랜잭션에서 사용 완료
    rows = world.db.execute(select(tables.TB_MBR_AGRE_HSTRY)).all()
    assert len(rows) == 3
    assert {(r.SITE_CONTS_SN, r.CONTS_HASH_VL, r.AGRE_ACT_CD) for r in rows} == {
        (docs["terms"]["SITE_CONTS_SN"], hashlib.sha256(TERMS_BODY.encode()).hexdigest(), "AA.AGREE"),
        (docs["privacy"]["SITE_CONTS_SN"], hashlib.sha256(PRIVACY_BODY.encode()).hexdigest(), "AA.AGREE"),
        (docs["market"]["SITE_CONTS_SN"], hashlib.sha256(MARKET_BODY.encode()).hexdigest(), "AA.AGREE"),
    }
    audit = world.db.execute(
        select(tables.TB_JOB_HSTRY).where(tables.TB_JOB_HSTRY.c.JOB_CD == "MEMBER_JOIN")
    ).one()
    assert (audit.ACTR_TYPE_CD, audit.MBR_SN, audit.JOB_RSLT_CD) == ("AK.MEMBER", member.MBR_SN, "JR.SUCCESS")
    assert "Strong-Pass-12" not in str(audit.CHG_CN)  # 감사 기록에는 비밀번호가 없다


def test_가입한_계정으로_바로_로그인할_수_있고_가입만으로는_로그인되지_않는다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    joined = join(world, cert, code)
    assert "jori_session" not in joined.headers.get("set-cookie", "")
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False
    assert login(world, MEMBER, "newbie", "Strong-Pass-12").status_code == 200


def test_마케팅_동의는_선택이라_동의하지_않으면_이력을_남기지_않는다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    assert join(world, cert, code, agreements=agreements(marketing=False)).status_code == 201
    assert world.db.execute(select(func.count()).select_from(tables.TB_MBR_AGRE_HSTRY)).scalar_one() == 2


def test_같은_인증으로_두_번_가입할_수_없다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    assert join(world, cert, code, login_id="first").status_code == 201
    second = join(world, cert, code, login_id="second")
    assert second.status_code == 422 and second.json()["code"] == "OTP_INVALID"
    assert member_count(world, "second") == 0


# --- 가입이 실패하면 아무것도 남기지 않는다 ---------------------------------------


def assert_nothing_created(w: World, cert: str, login_id: str = "newbie") -> None:
    assert member_count(w, login_id) == 0
    assert w.db.execute(select(func.count()).select_from(tables.TB_MBR_AGRE_HSTRY)).scalar_one() == 0
    assert cert_row(w, cert).CERT_USE_CMPTN_DT is None  # 인증은 소비되지 않았다. 다시 시도할 수 있다


def test_아이디가_이미_있으면_422이고_인증은_소비되지_않아_다른_아이디로_다시_가입할_수_있다(
    world: World,
) -> None:
    publish_defaults(world)
    make_member(world, "taken")
    cert, code = issue_join(world)
    taken = join(world, cert, code, login_id="taken")
    assert taken.status_code == 422 and taken.json()["code"] == "JOIN_LOGIN_ID_TAKEN"
    assert cert_row(world, cert).CERT_USE_CMPTN_DT is None
    assert world.db.execute(select(func.count()).select_from(tables.TB_MBR_AGRE_HSTRY)).scalar_one() == 0
    assert join(world, cert, code, login_id="fresh").status_code == 201  # 같은 인증으로 다시 가입


MARKETING_ONLY = [{"termType": "MARKETING_CONSENT", "version": "v1", "agreed": True}]


@pytest.mark.parametrize(
    "items",
    [
        agreements(terms=False),  # 이용약관 비동의
        agreements(privacy=False),  # 개인정보 비동의
        agreements()[:1],  # 개인정보 동의 항목이 아예 없음
        MARKETING_ONLY,  # 선택 동의만 있음
    ],
    ids=["이용약관_비동의", "개인정보_비동의", "개인정보_항목_없음", "선택_동의만"],
)
def test_필수_약관에_동의하지_않으면_422이고_아무것도_남지_않는다(
    world: World, items: list[dict[str, Any]]
) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    response = join(world, cert, code, agreements=items)
    assert response.status_code == 422 and "agreements" in response.json()["fields"]
    assert_nothing_created(world, cert)


def test_게시되지_않은_버전이나_다른_버전에_동의하면_거절한다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    wrong = join(world, cert, code, agreements=agreements(version="v9"))
    assert wrong.status_code == 422 and "agreements" in wrong.json()["fields"]
    assert_nothing_created(world, cert)


def test_게시_기간이_지났거나_게시하지_않은_약관에는_동의할_수_없다(world: World) -> None:
    publish(world, "CT.TERMS", "terms", TERMS_BODY, essential=True, PSTG_END_DT=START)  # 지금 종료됨
    publish(world, "CT.PRIVACY", "privacy", PRIVACY_BODY, essential=True)
    cert, code = issue_join(world)
    assert join(world, cert, code).status_code == 422  # 이용약관이 게시 중이 아니라 동의할 대상이 없다
    assert_nothing_created(world, cert)


def test_게시하지_않은_약관에는_동의할_수_없다(world: World) -> None:
    publish(world, "CT.TERMS", "terms", TERMS_BODY, essential=True, PSTG_YN="N")  # 게시 안 함
    publish(world, "CT.PRIVACY", "privacy", PRIVACY_BODY, essential=True)
    cert, code = issue_join(world)
    assert join(world, cert, code).status_code == 422
    assert_nothing_created(world, cert)


@pytest.mark.parametrize("published", ["없음", "선택_문안만"])
def test_게시된_필수_약관이_하나도_없으면_동의_항목이_비어_있어도_가입을_거절한다(
    world: World, published: str
) -> None:
    if published == "선택_문안만":
        publish(world, "CT.MARKET", "market", MARKET_BODY, essential=False)
    cert, code = issue_join(world)
    declined = [
        {"termType": "TERMS_OF_USE", "version": "v1", "agreed": False}
    ]  # 항목이 하나는 있어야 한다(스키마)
    response = join(world, cert, code, agreements=declined)
    assert response.status_code == 422 and response.json()["code"] == "RULE_REJECTED"
    assert_nothing_created(world, cert)


def test_다른_운영묶음의_인증으로는_가입할_수_없다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    # 문자 쪽 행이 인증 행을 참조하므로 이 연결에서만 외래키 검사를 끄고 인증 행의 운영묶음만 옮긴다
    world.db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    try:
        world.db.execute(
            tables.TB_CERT_DMND.update()
            .where(tables.TB_CERT_DMND.c.CERT_DMND_SN == int(cert))
            .values(OPER_BNDL_SN=other)
        )
    finally:
        world.db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    response = join(world, cert, code)
    assert response.status_code == 422 and response.json()["code"] == "OTP_INVALID"
    assert member_count(world, "newbie") == 0


def test_다른_운영묶음의_약관은_인정하지_않는다(world: World) -> None:
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    publish(world, "CT.TERMS", "terms", TERMS_BODY, essential=True, OPER_BNDL_SN=other)
    publish(world, "CT.PRIVACY", "privacy", PRIVACY_BODY, essential=True, OPER_BNDL_SN=other)
    cert, code = issue_join(world)
    assert join(world, cert, code).status_code == 422
    assert_nothing_created(world, cert)


def test_고정된_문안이_바뀌어_해시가_맞지_않으면_동의를_받지_않는다(world: World) -> None:
    docs = publish_defaults(world)
    world.db.execute(
        tables.TB_SITE_CONTS.update()
        .where(tables.TB_SITE_CONTS.c.SITE_CONTS_SN == docs["terms"]["SITE_CONTS_SN"])
        .values(CONTS_CN="몰래 바꾼 본문")
    )
    cert, code = issue_join(world)
    response = join(world, cert, code)
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert_nothing_created(world, cert)


def test_같은_약관을_두_번_보내면_400이다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    response = join(world, cert, code, agreements=agreements() + agreements()[:1])
    assert response.status_code == 400


# --- 인증이 틀린 경우 ------------------------------------------------------------


def test_틀린_코드는_422이고_실패_횟수는_오류_응답에도_남는다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    wrong = "000000" if code != "000000" else "111111"
    response = join(world, cert, wrong)
    assert response.status_code == 422 and response.json()["code"] == "OTP_INVALID"
    assert int(cert_row(world, cert).FAIL_NMTM) == 1
    assert member_count(world, "newbie") == 0


def test_5번_틀리면_맞는_코드도_쓸_수_없다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        join(world, cert, wrong)
    assert join(world, cert, code).json()["code"] == "OTP_INVALID"
    assert member_count(world, "newbie") == 0


def test_만료된_인증으로는_가입할_수_없다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    world.clock.advance(minutes=5)
    response = join(world, cert, code)
    assert response.status_code == 422 and response.json()["code"] == "OTP_EXPIRED"


def test_다른_목적의_인증으로는_가입할_수_없다(world: World) -> None:
    publish_defaults(world)
    make_member(world, "owner", MBL_TELNO=PHONE, MBR_NM="김회원")
    cert = request_otp(world, "ID_FIND", PHONE, name="김회원").json()["certRequestId"]
    response = join(world, str(cert), sent_code(world))
    assert response.status_code == 422 and response.json()["code"] == "OTP_INVALID"


def test_없는_인증_번호로는_가입할_수_없다(world: World) -> None:
    publish_defaults(world)
    assert join(world, "999999999", "123456").json()["code"] == "OTP_INVALID"


def test_가입_요청은_CSRF_토큰이_없으면_403이다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    body = {
        "certRequestId": cert,
        "code": code,
        "loginId": "newbie",
        "password": "Strong-Pass-12",
        "email": "a@b.co",
        "agreements": agreements(),
    }
    assert world.client.post(f"{MEMBER}/join", json=body).status_code == 403
    assert member_count(world, "newbie") == 0


def test_비밀번호가_10자_미만이거나_이메일_형식이_틀리면_400이다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    assert join(world, cert, code, password="short").status_code == 400
    assert join(world, cert, code, email="not-an-email").status_code == 400
    assert_nothing_created(world, cert)


# --- 아이디 찾기 ------------------------------------------------------------------


def find_id(w: World, cert_id: str, code: str) -> Any:
    return w.client.post(
        f"{MEMBER}/auth/find-id",
        json={"certRequestId": cert_id, "code": code},
        headers={"X-CSRF-Token": csrf(w)},
    )


def test_아이디_찾기는_앞_2글자만_보이고_인증을_사용_완료로_표시한다(world: World) -> None:
    make_member(world, "honggildong", MBL_TELNO=PHONE, MBR_NM="홍길동")
    cert = request_otp(world, "ID_FIND", PHONE, name="홍길동").json()["certRequestId"]
    code = sent_code(world)
    response = find_id(world, str(cert), code)
    assert response.status_code == 200 and response.json() == {"maskedLoginId": "ho*********"}
    assert cert_row(world, str(cert)).CERT_USE_CMPTN_DT == START
    assert find_id(world, str(cert), code).json()["code"] == "OTP_INVALID"  # 한 번 쓰면 다시 쓸 수 없다


@pytest.mark.parametrize(
    ("login_id", "masked"),
    [("honggildong", "ho*********"), ("hello123", "he******"), ("abc", "ab*"), ("ab", "a*"), ("a", "*")],
)
def test_아이디_마스킹은_앞_2글자만_보이고_짧은_아이디도_통째로_드러나지_않는다(
    login_id: str, masked: str
) -> None:
    from app.auth.recovery import mask_login_id

    assert mask_login_id(login_id) == masked
    assert masked != login_id and len(masked) == len(login_id)


def test_가짜_인증으로는_아이디를_알_수_없다(world: World) -> None:
    fake = request_otp(world, "ID_FIND", "01099998888", name="없는사람").json()["certRequestId"]
    for n in range(3):
        assert find_id(world, str(fake), f"{n:06d}").json().get("maskedLoginId", "무효") in ("무효", None)


def test_틀린_코드로는_아이디를_받지_못하고_횟수가_쌓인다(world: World) -> None:
    make_member(world, "honggildong", MBL_TELNO=PHONE, MBR_NM="홍길동")
    cert = str(request_otp(world, "ID_FIND", PHONE, name="홍길동").json()["certRequestId"])
    code = sent_code(world)
    wrong = "000000" if code != "000000" else "111111"
    assert find_id(world, cert, wrong).status_code == 422
    assert int(cert_row(world, cert).FAIL_NMTM) == 1


# --- 비밀번호 재설정 ---------------------------------------------------------------


def reset(
    w: World, cert_id: str, code: str, login_id: str = "owner", new_password: str = NEW_PASSWORD
) -> Any:
    body = {"certRequestId": cert_id, "code": code, "loginId": login_id, "newPassword": new_password}
    return w.client.post(f"{MEMBER}/auth/password-reset", json=body, headers={"X-CSRF-Token": csrf(w)})


def issue_reset(w: World, login_id: str = "owner") -> tuple[str, str]:
    cert = request_otp(w, "PASSWORD_RESET", PHONE, loginId=login_id).json()["certRequestId"]
    return str(cert), sent_code(w)


def test_재설정하면_새_비밀번호로만_로그인되고_인증이_소비된다(world: World) -> None:
    make_member(world, "owner", MBL_TELNO=PHONE)
    cert, code = issue_reset(world)
    assert reset(world, cert, code).status_code == 204
    world.client.cookies.clear()
    assert login(world, MEMBER, "owner", PASSWORD).status_code == 401  # 옛 비밀번호는 더 쓸 수 없다
    assert login(world, MEMBER, "owner", NEW_PASSWORD).status_code == 200
    assert cert_row(world, cert).CERT_USE_CMPTN_DT is not None
    assert reset(world, cert, code, new_password="Another-Pass-88").json()["code"] == "OTP_INVALID"


def test_재설정하면_그_회원의_기존_세션이_모두_끊긴다(world: World) -> None:
    member = make_member(world, "owner", MBL_TELNO=PHONE)
    other = make_member(world, "bystander")
    login(world, MEMBER, "owner")
    stolen = world.client.cookies.get("jori_session")
    world.client.cookies.clear()
    login(world, MEMBER, "bystander")
    bystander_cookie = world.client.cookies.get("jori_session")
    world.client.cookies.clear()
    cert, code = issue_reset(world)
    assert reset(world, cert, code).status_code == 204
    discarded = world.db.execute(
        select(tables.TB_LGN_SSN.c.MBR_SN, tables.TB_LGN_SSN.c.DSCD_RSN, tables.TB_LGN_SSN.c.DSCD_DT)
    ).all()
    by_member = {int(r.MBR_SN): (r.DSCD_RSN, r.DSCD_DT) for r in discarded}
    assert by_member[int(member["MBR_SN"])][0] == "PASSWORD_RESET"  # 이 회원의 세션은 폐기됐다
    assert by_member[int(other["MBR_SN"])] == (None, None)  # 다른 회원의 세션은 그대로다
    world.client.cookies.set("jori_session", stolen or "")
    assert (
        world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False
    )  # 훔친 세션은 더 쓸 수 없다
    world.client.cookies.set("jori_session", bystander_cookie or "")
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is True


def test_인증된_회원과_다른_아이디를_보내면_거절하고_횟수를_센다(world: World) -> None:
    make_member(world, "owner", MBL_TELNO=PHONE)
    make_member(world, "victim")
    cert, code = issue_reset(world)
    response = reset(world, cert, code, login_id="victim")  # 맞는 코드로 남의 계정을 바꾸려는 시도
    assert response.status_code == 422 and response.json()["code"] == "OTP_INVALID"
    assert int(cert_row(world, cert).FAIL_NMTM) == 1  # 맞는 코드로 아이디를 계속 시험하지 못하게 센다
    assert cert_row(world, cert).CERT_USE_CMPTN_DT is None
    world.client.cookies.clear()
    assert login(world, MEMBER, "victim", PASSWORD).status_code == 200  # 피해자 비밀번호는 그대로다


def test_가짜_인증으로는_비밀번호를_바꿀_수_없다(world: World) -> None:
    make_member(world, "victim")
    fake = str(request_otp(world, "PASSWORD_RESET", "01099998888", loginId="victim").json()["certRequestId"])
    for n in range(3):
        assert reset(world, fake, f"{n:06d}", login_id="victim").status_code == 422
    world.client.cookies.clear()
    assert login(world, MEMBER, "victim", PASSWORD).status_code == 200


def test_재설정이_성공하면_감사_기록이_남고_비밀번호는_기록되지_않는다(world: World) -> None:
    make_member(world, "owner", MBL_TELNO=PHONE)
    cert, code = issue_reset(world)
    reset(world, cert, code)
    audit = world.db.execute(
        select(tables.TB_JOB_HSTRY).where(tables.TB_JOB_HSTRY.c.JOB_CD == "PASSWORD_RESET")
    ).one()
    assert audit.JOB_RSLT_CD == "JR.SUCCESS" and NEW_PASSWORD not in str(audit.CHG_CN)


def test_새_비밀번호는_PBKDF2로_저장되고_반복_횟수가_함께_남는다(world: World) -> None:
    member = make_member(world, "owner", MBL_TELNO=PHONE)
    cert, code = issue_reset(world)
    reset(world, cert, code)
    stored = world.db.execute(
        select(tables.TB_MBR.c.PSWD_HASH_VL).where(tables.TB_MBR.c.MBR_SN == member["MBR_SN"])
    ).scalar_one()
    assert stored.startswith(f"pbkdf2_sha256${ITERATIONS}$") and NEW_PASSWORD not in stored


def test_재설정_요청은_CSRF_토큰이_없으면_403이다(world: World) -> None:
    make_member(world, "owner", MBL_TELNO=PHONE)
    cert, code = issue_reset(world)
    body = {"certRequestId": cert, "code": code, "loginId": "owner", "newPassword": NEW_PASSWORD}
    assert world.client.post(f"{MEMBER}/auth/password-reset", json=body).status_code == 403
    assert login(world, MEMBER, "owner", PASSWORD).status_code == 200  # 바뀌지 않았다
