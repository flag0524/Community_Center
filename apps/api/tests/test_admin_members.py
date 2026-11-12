# 관리자 회원 조회·연락처 열람·검토 기록·거주지 확인(AU.MBR_R)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin.member_service import mask_email, mask_phone
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_applications_read import open_course as _open_course
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)


def person(w: World, name: str = "홍길동", **values: Any) -> dict[str, Any]:
    return make_member(w, f"u{next(_n)}", MBR_NM=name, **values)


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def idem(key: str = "key-00000001") -> dict[str, str]:
    return {"Idempotency-Key": key}


def jobs(w: World, code: str) -> list[dict[str, Any]]:
    rows = w.db.execute(
        text(
            "SELECT MNGR_SN m, TRGT_TBL_NM t, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD=:c ORDER BY JOB_HSTRY_SN"
        ),
        {"c": code},
    ).mappings()
    return [dict(r) for r in rows]


# --- 마스킹(DB 없이) ----------------------------------------------------------------------------


def test_연락처와_이메일은_가려서_준다() -> None:
    assert mask_phone("01012345678") == "010-****-5678"
    assert mask_phone("0111234567") == "011-****-4567"
    assert mask_phone("123") == "****" and mask_phone(None) == "" and mask_phone("") == ""
    assert mask_email("hong@example.com") == "h***@example.com"
    assert mask_email("nomail") == "***" and mask_email(None) == ""


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_조회_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/members").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R"))
    for method, path, body in (
        ("GET", "/members", None),
        ("GET", "/members/1", None),
        ("POST", "/members/1/reveal", {"reason": "문의 응대 확인"}),
        ("POST", "/members/1/reviews", {"kind": "RESTRICT", "reason": "x"}),
        ("POST", "/members/1/reviews/1/close", {"note": "x"}),
        ("POST", "/members/1/residence", {"result": "VERIFIED", "note": "x"}),
    ):
        assert call(world, method, path, body, **idem()).status_code == 403, path


def test_동_담당자는_자기_동_회원만_보고_동이_없는_회원은_묶음_전체_담당자만_본다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    a = person(world, "내동", DONG_SN=mine["DONG_SN"])
    b = person(world, "남동", DONG_SN=other["DONG_SN"])
    c = person(world, "무동")
    use(world, staff(world, "d", "AU.MBR_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    listed = call(world, "GET", "/members").json()
    assert [i["memberId"] for i in listed["items"]] == [str(a["MBR_SN"])] and listed["total"] == 1
    assert call(world, "GET", f"/members/{a['MBR_SN']}").status_code == 200
    for hidden in (b, c):  # 범위 밖과 동이 없는 회원은 없는 것과 같은 404다
        assert call(world, "GET", f"/members/{hidden['MBR_SN']}").status_code == 404
        assert (
            call(
                world, "POST", f"/members/{hidden['MBR_SN']}/reveal", {"reason": "문의 응대 확인"}
            ).status_code
            == 404
        )
        assert (
            call(
                world,
                "POST",
                f"/members/{hidden['MBR_SN']}/residence",
                {"result": "VERIFIED", "note": "확인"},
            ).status_code
            == 404
        )
        assert (
            call(
                world,
                "POST",
                f"/members/{hidden['MBR_SN']}/reviews",
                {"kind": "RESTRICT", "reason": "사유"},
                **idem(),
            ).status_code
            == 404
        )
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert {i["memberId"] for i in call(world, "GET", "/members").json()["items"]} == {
        str(x["MBR_SN"]) for x in (a, b, c)
    }


def test_다른_운영묶음의_회원은_없는_것과_같다(world: World) -> None:
    foreign_bundle = int(
        world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    )  # bundle()은 같은 묶음을 돌려주므로 새로 만든다
    stranger = world.factory.make(
        "TB_MBR", OPER_BNDL_SN=foreign_bundle, LGN_ID="far", PSWD_HASH_VL="x", MBR_NM="타지"
    )
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert call(world, "GET", "/members").json()["total"] == 0
    assert call(world, "GET", f"/members/{stranger['MBR_SN']}").status_code == 404


# --- 목록 ---------------------------------------------------------------------------------------


def test_목록은_이름을_가리고_최근_가입이_먼저이며_조건으로_거른다(world: World) -> None:
    old = person(world, "박다라", MBR_JOIN_DT=START.replace(year=2025), **RESIDENT)
    new = person(world, "홍길동", MBR_STTS_CD="MS.LOCKED")
    gone = person(world, "이탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    use(world, staff(world, "boss", "AU.MBR_R"))
    body = call(world, "GET", "/members").json()
    assert [i["memberId"] for i in body["items"]][-1] == str(old["MBR_SN"])  # 가장 오래된 가입이 끝이다
    by_id = {i["memberId"]: i for i in body["items"]}
    assert by_id[str(old["MBR_SN"])]["nameMasked"] == "박*라"
    assert by_id[str(old["MBR_SN"])]["residenceStatus"] == "VERIFIED"
    assert by_id[str(new["MBR_SN"])]["residenceStatus"] == "UNVERIFIED"
    assert by_id[str(old["MBR_SN"])]["joinedOn"] == "2025-11-09" or by_id[str(old["MBR_SN"])][
        "joinedOn"
    ].startswith("2025")
    assert {k: by_id[str(new["MBR_SN"])]["status"] for k in ("status",)}["status"] == "LOCKED"
    assert by_id[str(gone["MBR_SN"])]["status"] == "WITHDRAWN"
    assert "phone" not in str(body) and "email" not in str(body).lower().replace("emailmasked", "")
    only = call(world, "GET", "/members?status=WITHDRAWN").json()
    assert [i["memberId"] for i in only["items"]] == [str(gone["MBR_SN"])]
    assert [i["memberId"] for i in call(world, "GET", f"/members?q={new['LGN_ID']}").json()["items"]] == [
        str(new["MBR_SN"])
    ]
    assert [i["memberId"] for i in call(world, "GET", "/members?q=박다").json()["items"]] == [
        str(old["MBR_SN"])
    ]
    assert call(world, "GET", "/members?q=_").json()["total"] == 0  # 와일드카드는 글자로 다룬다
    assert call(world, "GET", "/members?status=NOPE").status_code in (400, 422)


def test_목록은_쪽을_나눈다(world: World) -> None:
    for n in range(3):
        person(world, f"이름{n}")
    use(world, staff(world, "boss", "AU.MBR_R"))
    first = call(world, "GET", "/members?size=2&page=1").json()
    second = call(world, "GET", "/members?size=2&page=2").json()
    assert (len(first["items"]), len(second["items"]), first["total"]) == (2, 1, 3)


# --- 상세 ---------------------------------------------------------------------------------------


def test_상세는_연락처를_가리고_신청과_결제_합계를_담는다(world: World) -> None:
    who = person(world, "홍길동", MBL_TELNO="01011112222", EML_ADDR="hong@example.com", **RESIDENT)
    row = course(world, CORS_NM="요가")
    paid = application(world, who, row, "ES.CONFIRM")
    payment(world, paid, "PS.PAID", STLM_AMT=30000)
    other = application(world, who, course(world, CORS_NM="서예"), "ES.CANCEL")
    use(world, staff(world, "boss", "AU.MBR_R"))
    body = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert body["phoneMasked"] == "010-****-2222" and body["emailMasked"] == "h***@example.com"
    assert body["nameMasked"] == "홍*동" and body["canReview"] is True
    assert body["applicationCount"] == 2 and body["paidTotal"] == 30000
    assert {a["courseName"] for a in body["applications"]} == {"요가", "서예"}
    assert {a["applicationNo"] for a in body["applications"]} == {
        str(paid["ATNLC_APLY_SN"]),
        str(other["ATNLC_APLY_SN"]),
    }
    assert "01011112222" not in str(body) and "hong@example.com" not in str(body)
    assert body["reviews"] == []


def test_동_담당자가_보는_신청과_합계는_자기_동_강좌만이다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    who = person(world, "홍길동", DONG_SN=mine["DONG_SN"])
    inside = application(world, who, course(world, CORS_NM="내강좌", DONG_SN=mine["DONG_SN"]), "ES.CONFIRM")
    outside = application(world, who, course(world, CORS_NM="남강좌", DONG_SN=other["DONG_SN"]), "ES.CONFIRM")
    payment(world, inside, "PS.PAID", STLM_AMT=10000)
    payment(world, outside, "PS.PAID", STLM_AMT=20000)
    use(world, staff(world, "d", "AU.MBR_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    body = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert [a["courseName"] for a in body["applications"]] == ["내강좌"]
    assert (body["applicationCount"], body["paidTotal"]) == (1, 10000)
    use(world, staff(world, "boss", "AU.MBR_R"))
    body = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert (body["applicationCount"], body["paidTotal"]) == (2, 30000)


def test_탈퇴한_회원은_검토_기록_양식이_없다고_알린다(world: World) -> None:
    gone = person(world, "이탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert call(world, "GET", f"/members/{gone['MBR_SN']}").json()["canReview"] is False


def test_상세에_없는_회원은_404이고_잘못된_번호는_검증_오류다(world: World) -> None:
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert call(world, "GET", "/members/999999999").status_code == 404
    assert call(world, "GET", "/members/abc").status_code in (400, 422)


# --- 연락처 열람 ---------------------------------------------------------------------------------


def test_사유를_적으면_원문_연락처를_주고_열람을_기록한다(world: World) -> None:
    who = person(world, "홍길동", MBL_TELNO="01011112222", EML_ADDR="hong@example.com")
    boss = staff(world, "boss", "AU.MBR_R")
    use(world, boss)
    r = call(world, "POST", f"/members/{who['MBR_SN']}/reveal", {"reason": "민원 전화 회신"})
    assert r.status_code == 200 and r.json() == {"phone": "01011112222", "email": "hong@example.com"}
    [job] = jobs(world, "MBR_REVEAL")
    assert (job["m"], job["t"], job["k"]) == (boss.sn, "TB_MBR", str(who["MBR_SN"]))
    assert (
        "민원 전화 회신" in job["c"] and "01011112222" not in job["c"] and "hong@example.com" not in job["c"]
    )


def test_사유가_짧으면_열어_주지_않고_기록도_없다(world: World) -> None:
    who = person(world, "홍길동", MBL_TELNO="01011112222")
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert call(world, "POST", f"/members/{who['MBR_SN']}/reveal", {"reason": "급함"}).status_code in (
        400,
        422,
    )
    assert call(world, "POST", f"/members/{who['MBR_SN']}/reveal", {}).status_code in (400, 422)
    assert jobs(world, "MBR_REVEAL") == []


def test_연락처가_없는_회원은_빈_값을_주고_그래도_기록한다(world: World) -> None:
    who = person(world, "홍길동", MBL_TELNO=None, EML_ADDR=None)
    use(world, staff(world, "boss", "AU.MBR_R"))
    r = call(world, "POST", f"/members/{who['MBR_SN']}/reveal", {"reason": "확인 목적입니다"})
    assert r.json() == {"phone": "", "email": ""} and len(jobs(world, "MBR_REVEAL")) == 1


# --- 검토 기록 ----------------------------------------------------------------------------------


def review(
    w: World,
    member: dict[str, Any],
    kind: str = "RESTRICT",
    reason: str = "반복 취소",
    key: str = "key-00000001",
) -> Any:
    return call(
        w, "POST", f"/members/{member['MBR_SN']}/reviews", {"kind": kind, "reason": reason}, **idem(key)
    )


def test_검토_기록은_사유만_남기고_회원_상태는_바꾸지_않는다(world: World) -> None:
    who = person(world, "홍길동")
    boss = staff(world, "boss", "AU.MBR_R")
    use(world, boss)
    r = review(world, who)
    assert r.status_code == 201
    made = r.json()
    assert (made["kind"], made["state"], made["reason"]) == ("RESTRICT", "OPEN", "반복 취소")
    assert made["recordedBy"] == "김관리" and made["closedNote"] is None and made["closedAt"] is None
    detail = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert [x["reviewId"] for x in detail["reviews"]] == [made["reviewId"]] and detail["status"] == "ACTIVE"
    row = world.db.execute(
        text("SELECT MBR_STTS_CD s, RCRD_VER v FROM TB_MBR WHERE MBR_SN=:m"), {"m": who["MBR_SN"]}
    ).one()
    assert (row.s, int(row.v)) == ("MS.ACTIVE", int(who["RCRD_VER"]))


def test_같은_종류가_검토_중이면_새로_남기지_않고_다른_종류는_남긴다(world: World) -> None:
    who = person(world, "홍길동")
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert review(world, who, "RESTRICT", key="key-00000001").status_code == 201
    r = review(world, who, "RESTRICT", reason="또 다른 사유", key="key-00000002")
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert review(world, who, "WITHDRAW", key="key-00000003").status_code == 201
    assert review(world, who, "NAME_CHANGE", key="key-00000004").status_code == 201
    assert len(call(world, "GET", f"/members/{who['MBR_SN']}").json()["reviews"]) == 3


def test_같은_키로_다시_보내면_처음_결과를_주고_내용이_다르면_409다(world: World) -> None:
    who = person(world, "홍길동")
    use(world, staff(world, "boss", "AU.MBR_R"))
    first = review(world, who).json()
    again = review(world, who)
    assert again.status_code == 201 and again.json()["reviewId"] == first["reviewId"]
    assert len(jobs(world, "MBR_REVIEW")) == 1
    diff = review(world, who, reason="다른 사유")
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    other_kind = review(world, who, kind="WITHDRAW")
    assert other_kind.status_code == 409 and other_kind.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_검토를_닫으면_처리_완료가_되고_다시_닫을_수_없으며_새로_남길_수_있다(world: World) -> None:
    who = person(world, "홍길동")
    use(world, staff(world, "boss", "AU.MBR_R"))
    made = review(world, who).json()
    path = f"/members/{who['MBR_SN']}/reviews/{made['reviewId']}/close"
    closed = call(world, "POST", path, {"note": "안내 후 종결"})
    assert closed.status_code == 200
    body = closed.json()
    assert (body["state"], body["closedNote"]) == ("CLOSED", "안내 후 종결") and body["closedAt"] is not None
    assert body["reason"] == "반복 취소" and body["reviewId"] == made["reviewId"]
    again = call(world, "POST", path, {"note": "또"})
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"
    assert review(world, who, key="key-00000009").status_code == 201  # 닫았으니 같은 종류를 다시 남길 수 있다
    detail = call(world, "GET", f"/members/{who['MBR_SN']}").json()["reviews"]
    assert [r["state"] for r in detail] == ["OPEN", "CLOSED"]  # 최근 기록이 먼저다


def test_없는_검토나_다른_회원의_검토는_닫을_수_없다(world: World) -> None:
    a, b = person(world, "가"), person(world, "나")
    use(world, staff(world, "boss", "AU.MBR_R"))
    made = review(world, a).json()
    assert (
        call(world, "POST", f"/members/{a['MBR_SN']}/reviews/999999/close", {"note": "x"}).status_code == 404
    )
    assert (
        call(
            world, "POST", f"/members/{b['MBR_SN']}/reviews/{made['reviewId']}/close", {"note": "x"}
        ).status_code
        == 404
    )
    assert call(world, "GET", f"/members/{a['MBR_SN']}").json()["reviews"][0]["state"] == "OPEN"


def test_탈퇴한_회원에게는_검토도_거주지_기록도_남기지_않는다(world: World) -> None:
    gone = person(world, "이탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    use(world, staff(world, "boss", "AU.MBR_R"))
    r = review(world, gone)
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    r = call(world, "POST", f"/members/{gone['MBR_SN']}/residence", {"result": "VERIFIED", "note": "확인"})
    assert r.status_code == 409
    assert jobs(world, "MBR_REVIEW") == [] and jobs(world, "MBR_RESIDENCE") == []


def test_검토_사유는_검증하고_작업이력에_담당자와_함께_남긴다(world: World) -> None:
    who = person(world, "홍길동")
    boss = staff(world, "boss", "AU.MBR_R")
    use(world, boss)
    assert review(world, who, reason="").status_code in (400, 422)
    assert review(world, who, kind="NOPE").status_code in (400, 422)
    assert call(
        world, "POST", f"/members/{who['MBR_SN']}/reviews", {"kind": "RESTRICT", "reason": "사유"}
    ).status_code in (400, 422)  # 멱등키 없음
    assert review(world, who).status_code == 201
    [job] = jobs(world, "MBR_REVIEW")
    assert (job["m"], job["t"], job["k"]) == (boss.sn, "TB_MBR", str(who["MBR_SN"])) and job["c"].startswith(
        "[RESTRICT] 반복 취소 [idem "
    )


# --- 거주지 확인 --------------------------------------------------------------------------------


def residence(
    w: World, member: dict[str, Any], result: str = "VERIFIED", note: str = "주민등록 등본 확인"
) -> Any:
    return call(w, "POST", f"/members/{member['MBR_SN']}/residence", {"result": result, "note": note})


def fields(w: World, member: dict[str, Any]) -> Any:
    return w.db.execute(
        text(
            "SELECT HAB_RGN_CD r, HAB_IDNTY_STTS_CD s, HAB_IDNTY_DT d, HAB_IDNTY_MNS_CD m, HAB_IDNTY_MNGR_SN g, HAB_IDNTY_BSS_ID b, RCRD_VER v FROM TB_MBR WHERE MBR_SN=:m"
        ),
        {"m": member["MBR_SN"]},
    ).one()


def test_확인_완료를_기록하면_조리읍_거주로_남고_확인자와_근거가_채워진다(world: World) -> None:
    who = person(world, "홍길동")
    boss = staff(world, "boss", "AU.MBR_R")
    use(world, boss)
    r = residence(world, who)
    assert r.status_code == 200 and r.json()["residenceStatus"] == "VERIFIED"
    row = fields(world, who)
    assert (row.r, row.s, row.m, int(row.g)) == ("RA.JORI", "RV.OK", "RM.MANUAL", boss.sn)
    assert row.d is not None and row.b and int(row.v) == int(who["RCRD_VER"]) + 1
    [job] = jobs(world, "MBR_RESIDENCE")
    assert job["c"] == "거주지 VERIFIED: 주민등록 등본 확인" and job["m"] == boss.sn


def test_미확인으로_되돌리면_확인_정보를_비우고_거주구분을_미확인으로_돌린다(world: World) -> None:
    who = person(world, "홍길동", **RESIDENT, HAB_IDNTY_DT=START, HAB_IDNTY_MNS_CD="RM.MANUAL")
    use(world, staff(world, "boss", "AU.MBR_R"))
    r = residence(world, who, "UNVERIFIED", "확인 철회")
    assert r.status_code == 200 and r.json()["residenceStatus"] == "UNVERIFIED"
    row = fields(world, who)
    assert (row.r, row.s, row.d, row.m, row.g, row.b) == ("RA.UNKNOWN", "RV.NONE", None, None, None, None)


def test_확인_완료를_기록하면_우선접수와_감면_판정이_조리읍_회원으로_본다(world: World) -> None:
    from app.domain.application.pricing import is_resident  # noqa: PLC0415

    who = person(world, "홍길동")
    use(world, staff(world, "boss", "AU.MBR_R"))
    residence(world, who)
    row = world.db.execute(
        text("SELECT HAB_RGN_CD, HAB_IDNTY_STTS_CD FROM TB_MBR WHERE MBR_SN=:m"), {"m": who["MBR_SN"]}
    ).one()
    assert is_resident(row)


def test_거주지_기록은_사유가_필요하고_회원의_다른_정보는_바꾸지_않는다(world: World) -> None:
    who = person(world, "홍길동", MBL_TELNO="01011112222", DONG_SN=None)
    use(world, staff(world, "boss", "AU.MBR_R"))
    assert call(world, "POST", f"/members/{who['MBR_SN']}/residence", {"result": "VERIFIED"}).status_code in (
        400,
        422,
    )
    assert call(
        world, "POST", f"/members/{who['MBR_SN']}/residence", {"result": "VERIFIED", "note": ""}
    ).status_code in (400, 422)
    assert call(
        world, "POST", f"/members/{who['MBR_SN']}/residence", {"result": "NOPE", "note": "x"}
    ).status_code in (400, 422)
    assert jobs(world, "MBR_RESIDENCE") == []
    residence(world, who)
    row = world.db.execute(
        text("SELECT MBL_TELNO p, MBR_NM n, MBR_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m"), {"m": who["MBR_SN"]}
    ).one()
    assert (row.p, row.n, row.s) == ("01011112222", "홍길동", "MS.ACTIVE")


def test_결제완료가_아닌_결제는_합계에_넣지_않는다(world: World) -> None:
    who = person(world, "홍길동")
    row = course(world)
    payment(world, application(world, who, row, "ES.CONFIRM"), "PS.PAID", STLM_AMT=30000)
    payment(
        world, application(world, who, course(world, CORS_NM="서예"), "ES.HOLD"), "PS.PENDING", STLM_AMT=50000
    )
    payment(
        world, application(world, who, course(world, CORS_NM="공예"), "ES.CANCEL"), "PS.FAIL", STLM_AMT=70000
    )
    use(world, staff(world, "boss", "AU.MBR_R"))
    body = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert (body["applicationCount"], body["paidTotal"]) == (3, 30000)


def test_상세의_신청은_최근_것만_보이고_전체_건수는_따로_준다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.domain.admin import member_service  # noqa: PLC0415

    who = person(world, "홍길동")
    for n in range(3):
        application(
            world, who, course(world, CORS_NM=f"강좌{n}"), "ES.CONFIRM", APLY_DT=START - timedelta(days=n)
        )
    use(world, staff(world, "boss", "AU.MBR_R"))
    monkeypatch.setattr(member_service, "APPLICATION_LIMIT", 2)
    body = call(world, "GET", f"/members/{who['MBR_SN']}").json()
    assert [a["courseName"] for a in body["applications"]] == ["강좌0", "강좌1"] and body[
        "applicationCount"
    ] == 3
