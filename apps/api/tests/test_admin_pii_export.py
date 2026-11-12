# 개인식별 명단 암호화 ZIP 내보내기(AU.EXPORT, AES-256, 5천 행 한도, 멱등키 재전송 409, 감사 기록)를 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
import zipfile
from typing import Any

import pytest
import pyzipper
from sqlalchemy import text

from app.domain.admin import pii_export
from tests.test_admin_access import dong
from tests.test_admin_applications import member
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_applications_read import open_course as _open_course
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

PATH = "/exports/pii"


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def ask(w: World, key: str = "key-00000001", **body: Any) -> Any:
    return call(w, "POST", PATH, {"target": "APPLICATIONS", **body}, **{"Idempotency-Key": key})


def opened(response: Any, entry: str = "applicants.csv") -> list[list[str]]:
    """응답의 암호로만 열리는지 확인하고 CSV 표를 돌려준다."""
    assert response.status_code == 200, response.text
    password = response.headers["X-Export-Password"]
    with pyzipper.AESZipFile(io.BytesIO(response.content)) as z:
        z.setpassword(password.encode())
        return list(csv.reader(io.StringIO(z.read(entry).decode("utf-8-sig"))))


def seeded(w: World) -> dict[str, Any]:
    row = course(w)
    application(
        w, make_member(w, "m1", MBR_NM="홍길동", MBL_TELNO="01011112222", **RESIDENT), row, "ES.CONFIRM"
    )
    return row


def test_암호화_ZIP은_가리지_않은_이름과_연락처를_담고_응답_암호로만_열린다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    r = ask(world)
    table = opened(r)
    assert table[0] == ["신청번호", "강좌", "신청자", "휴대전화", "신청 상태", "결제 상태", "신청일시"]
    assert table[1][2:4] == ["홍길동", "01011112222"]  # 목록과 달리 가리지 않은 값
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["cache-control"] == "no-store" and "attachment" in r.headers["content-disposition"]
    assert len(r.headers["X-Export-Password"]) == 20 and pii_export.PASSWORD_LENGTH == 20


def test_ZIP은_AES_256이고_암호가_없거나_틀리면_열리지_않는다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    r = ask(world)
    raw = r.content
    with pyzipper.AESZipFile(io.BytesIO(raw)) as z:
        with pytest.raises(RuntimeError):
            z.read("applicants.csv")  # 암호 없음
        z.setpassword(b"wrong-password")
        with pytest.raises(RuntimeError):
            z.read("applicants.csv")
    assert b"01011112222" not in raw and "홍길동".encode() not in raw  # 평문이 새지 않는다
    with zipfile.ZipFile(
        io.BytesIO(raw)
    ) as plain:  # 표준 zipfile은 압축 방식을 변환하지 않고 그대로 보여 준다
        info = plain.infolist()[0]
        assert info.flag_bits & 1  # 암호화됨
        assert info.compress_type == 99  # WinZip AES(구형 ZipCrypto가 아니다)
        assert info.extra[:2] == b"\x01\x99" and info.extra[8] == 3  # AE 부가 정보의 강도 3 = AES-256


def test_요청마다_새_암호이고_새_멱등키로는_다시_만들_수_있다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    a, b = ask(world, "key-00000001"), ask(world, "key-00000002")
    assert a.headers["X-Export-Password"] != b.headers["X-Export-Password"]
    assert len(opened(b)) == 2


def test_같은_멱등키로_다시_보내면_내용이_같아도_다르면도_409이고_새_파일을_만들지_않는다(
    world: World,
) -> None:
    seeded(world)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    assert ask(world, "key-00000001").status_code == 200
    for body in ({}, {"q": "홍"}):
        r = ask(world, "key-00000001", **body)
        assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT"
        assert "X-Export-Password" not in r.headers and not r.content.startswith(b"PK")
    done = world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT'")).scalar()
    assert done == 1


def test_AU_EXPORT가_없으면_목록_권한이_있어도_403이다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "x", "AU.APLY_R"))
    assert ask(world).status_code == 403


def test_대상_목록의_조회_권한이_없으면_AU_EXPORT가_있어도_403이다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "x", "AU.EXPORT"))
    assert ask(world).status_code == 403


def test_범위는_내보내기와_목록_권한이_함께_좁힌다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    application(world, member(world, "내동"), course(world, DONG_SN=mine["DONG_SN"]), "ES.CONFIRM")
    application(
        world, member(world, "남동"), course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]), "ES.CONFIRM"
    )
    use(world, staff(world, "d", "AU.EXPORT", "AU.APLY_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [r[2] for r in opened(ask(world))[1:]] == ["내동"]


def test_내보내기_범위가_목록_범위보다_좁으면_내보내기_범위를_따른다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    application(world, member(world, "내동"), course(world, DONG_SN=mine["DONG_SN"]), "ES.CONFIRM")
    application(
        world, member(world, "남동"), course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]), "ES.CONFIRM"
    )
    boss = staff(world, "w", "AU.APLY_R")  # 목록은 전체
    from tests.test_admin_access import assign, role  # 같은 담당자에게 동 범위 내보내기 역할을 더 준다

    assign(world, boss.row, role(world, "r-exp", "AU.EXPORT"), "SK.DONG", dong_sn=mine["DONG_SN"])
    use(world, boss)
    assert [r[2] for r in opened(ask(world))[1:]] == ["내동"]


def test_목록과_같은_조건을_받는다(world: World) -> None:
    row = course(world)
    paid = application(
        world,
        make_member(world, "m1", MBR_NM="가나다", MBL_TELNO="01000000001", **RESIDENT),
        row,
        "ES.CONFIRM",
    )
    payment(world, paid, "PS.PAID")
    application(
        world,
        make_member(world, "m2", MBR_NM="라마바", MBL_TELNO="01000000002", **RESIDENT),
        row,
        "ES.CANCEL",
    )
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    assert [r[2] for r in opened(ask(world, "key-00000001", status="CONFIRMED"))[1:]] == ["가나다"]
    assert [r[2] for r in opened(ask(world, "key-00000002", q="라마"))[1:]] == ["라마바"]
    assert [r[2] for r in opened(ask(world, "key-00000003", payment_status="PAID"))[1:]] == ["가나다"]
    assert [r[2] for r in opened(ask(world, "key-00000004", course_id=str(row["CORS_SN"])))[1:]] != []


def test_조건_값이_올바르지_않으면_400이고_기록하지_않는다(world: World) -> None:
    seeded(world)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    for body in ({"status": "NOPE"}, {"payment_status": "NOPE"}, {"from": "2026-13-45"}):
        assert ask(world, **body).status_code == 400
    done = world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT'")).scalar()
    assert done == 0


def test_5천_행_한도_정확히는_만들고_넘으면_거절하며_기록하지_않는다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = course(world)
    for n in range(3):
        application(world, make_member(world, f"m{n}", MBR_NM=f"이름{n}", **RESIDENT), row, "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    monkeypatch.setattr(pii_export, "MAX_ROWS", 3)
    assert len(opened(ask(world, "key-00000001"))) == 4
    monkeypatch.setattr(pii_export, "MAX_ROWS", 2)
    r = ask(world, "key-00000002")
    assert (
        r.status_code == 422 and r.json()["code"] == "RULE_REJECTED" and "조건을 좁혀" in r.json()["message"]
    )
    done = world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT'")).scalar()
    assert done == 1


def test_거절된_요청의_멱등키는_다음에_다시_쓸_수_있다(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    row = course(world)
    for n in range(2):
        application(world, make_member(world, f"m{n}", **RESIDENT), row, "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    monkeypatch.setattr(pii_export, "MAX_ROWS", 1)
    assert ask(world, "key-00000001").status_code == 422
    assert ask(world, "key-00000001", q="없는이름").status_code == 200  # 만들지 않았으니 키를 쓴 것이 아니다


def test_만든_사실만_감사에_남기고_암호와_내용과_검색어는_남기지_않는다(world: World) -> None:
    seeded(world)
    who = staff(world, "boss", "AU.EXPORT", "AU.APLY_R")
    use(world, who)
    r = ask(world, "key-00000001", q="홍길동")
    job = (
        world.db.execute(
            text(
                "SELECT ACTR_TYPE_CD a, MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT'"
            )
        )
        .mappings()
        .one()
    )
    assert (job["a"], job["m"], job["t"]) == ("AK.ADMIN", who.sn, "TB_ATNLC_APLY")
    assert job["c"].startswith("1건 암호화 내보냄(조건: q) [idem ")
    assert (
        r.headers["X-Export-Password"] not in job["c"]
        and "홍길동" not in job["c"]
        and "01011112222" not in job["c"]
    )


def ask_members(w: World, key: str = "key-00000001", **body: Any) -> Any:
    return call(w, "POST", PATH, {"target": "MEMBERS", **body}, **{"Idempotency-Key": key})


def test_회원_명단은_가리지_않은_이름과_연락처를_담고_회원_목록과_같은_조건이다(world: World) -> None:
    make_member(
        world, "hong", MBR_NM="홍길동", MBL_TELNO="01011112222", EML_ADDR="hong@example.com", **RESIDENT
    )
    make_member(world, "gone", MBR_NM="이탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    use(world, staff(world, "boss", "AU.EXPORT", "AU.MBR_R"))
    r = ask_members(world)
    table = opened(r, "members.csv")
    assert table[0] == [
        "회원번호",
        "아이디",
        "이름",
        "휴대전화",
        "이메일",
        "회원 상태",
        "거주지 확인",
        "가입일",
    ]
    by_login = {row[1]: row for row in table[1:]}
    assert by_login["hong"][2:] == [
        "홍길동",
        "01011112222",
        "hong@example.com",
        "ACTIVE",
        "VERIFIED",
        by_login["hong"][7],
    ]
    assert by_login["gone"][5] == "WITHDRAWN" and by_login["gone"][6] == "UNVERIFIED"
    assert 'filename="members.zip"' in r.headers["content-disposition"]
    assert [
        row[1] for row in opened(ask_members(world, "key-00000002", status="WITHDRAWN"), "members.csv")[1:]
    ] == ["gone"]
    assert [row[1] for row in opened(ask_members(world, "key-00000003", q="hon"), "members.csv")[1:]] == [
        "hong"
    ]
    tables = (
        world.db.execute(
            text("SELECT TRGT_TBL_NM FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT' ORDER BY JOB_HSTRY_SN")
        )
        .scalars()
        .all()
    )
    assert tables == ["TB_MBR"] * 3


def test_회원_명단은_AU_EXPORT와_회원_조회_권한이_함께_있어야_한다(world: World) -> None:
    make_member(world, "hong", MBR_NM="홍길동")
    use(world, staff(world, "a", "AU.MBR_R"))
    assert ask_members(world).status_code == 403
    use(world, staff(world, "b", "AU.EXPORT"))
    assert ask_members(world).status_code == 403
    use(world, staff(world, "c", "AU.EXPORT", "AU.APLY_R"))  # 수강신청 조회 권한으로는 회원 명단을 못 낸다
    assert ask_members(world).status_code == 403


def test_회원_명단의_범위는_내보내기와_회원_조회_권한이_함께_좁힌다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    make_member(world, "in", MBR_NM="내동", DONG_SN=mine["DONG_SN"])
    make_member(world, "out", MBR_NM="남동", DONG_SN=other["DONG_SN"])
    make_member(world, "none", MBR_NM="무동")
    use(world, staff(world, "d", "AU.EXPORT", "AU.MBR_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [row[1] for row in opened(ask_members(world), "members.csv")[1:]] == ["in"]


def test_회원_명단도_한도를_넘으면_거절한다(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    for n in range(2):
        make_member(world, f"m{n}")
    use(world, staff(world, "boss", "AU.EXPORT", "AU.MBR_R"))
    monkeypatch.setattr(pii_export, "MAX_ROWS", 1)
    assert ask_members(world).status_code == 422


def test_로그인과_멱등키와_CSRF_없이는_거절한다(world: World) -> None:
    assert world.client.post(f"/api/admin/v1{PATH}", json={"target": "APPLICATIONS"}).status_code in (
        401,
        403,
    )
    use(world, staff(world, "boss", "AU.EXPORT", "AU.APLY_R"))
    r = call(world, "POST", PATH, {"target": "APPLICATIONS"})  # Idempotency-Key 없음
    assert r.status_code == 400


def test_멱등키는_담당자마다_따로_센다(world: World) -> None:
    seeded(world)
    first = staff(world, "a", "AU.EXPORT", "AU.APLY_R")
    second = staff(world, "b", "AU.EXPORT", "AU.APLY_R")
    use(world, first)
    assert ask(world, "key-00000001").status_code == 200
    use(world, second)
    assert ask(world, "key-00000001").status_code == 200
