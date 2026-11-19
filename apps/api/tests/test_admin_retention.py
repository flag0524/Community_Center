# 보존·파기 검토 목록·상세(대상별 건수·기준일·예정일·상태, 정산자료 제외 이유, 묶음 전체 담당자만, 실행은 아직 없음)를 실제 앱과 MariaDB로 확인하는 시험
from datetime import date, timedelta
from typing import Any

import pytest

from tests.test_admin_refunds import call, refund, staff, use
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

TODAY = (START + timedelta(hours=9)).date()


def viewer(w: World) -> None:
    use(w, staff(w, "ret", "AU.LOG_R"))


def items(w: World) -> dict[str, Any]:
    res = call(w, "GET", "/retention")
    assert res.status_code == 200, res.text
    return {i["target"]: i for i in res.json()["items"]}


def test_로그인이_없으면_401이고_조회_권한이_없거나_동_담당자면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/retention").status_code == 401
    use(world, staff(world, "no", "AU.APLY_R"))
    assert call(world, "GET", "/retention").status_code == 403
    assert call(world, "GET", "/retention/1").status_code == 403
    use(
        world,
        staff(world, "dongret", "AU.LOG_R", kind="SK.DONG", dong_sn=world.factory.make("TB_DONG")["DONG_SN"]),
    )
    assert call(world, "GET", "/retention").status_code == 403  # 묶음 공통 자료라 묶음 전체 담당자만 본다


def test_자료가_없으면_모두_0건이고_정산자료는_제외한다고_알린다(world: World) -> None:
    viewer(world)
    res = call(world, "GET", "/retention").json()
    assert [(i["itemId"], i["target"]) for i in res["items"]] == [
        ("1", "WITHDRAWN_MEMBER"),
        ("2", "AUTH_RECORDS"),
        ("3", "AUDIT_HISTORY"),
        ("4", "REFUND_ACCOUNT"),
        ("5", "SMS_RECORDS"),
        ("6", "SESSION_RECORDS"),
        ("7", "LOGIN_FAILURES"),
    ]
    assert all(i["count"] == 0 and i["baseDate"] is None and i["dueOn"] is None for i in res["items"])
    assert [e["label"] for e in res["exclusions"]][0] == "정산자료(결제·환불 원장)"
    assert "5년" in res["exclusions"][0]["reason"]


def test_탈퇴_회원은_30일이_지난_사람만_세고_예정일이_지나면_DUE이다(world: World) -> None:
    for n, days in enumerate((45, 31, 10)):
        make_member(world, f"w{n}", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START - timedelta(days=days))
    make_member(world, "active")
    make_member(
        world, "stale", MBR_STTS_CD="MS.ACTIVE", WHDWL_DT=START - timedelta(days=90)
    )  # 탈퇴 상태가 아니면 세지 않는다
    viewer(world)
    item = items(world)["WITHDRAWN_MEMBER"]
    base = (START - timedelta(days=45) + timedelta(hours=9)).date()
    assert (item["count"], item["state"]) == (2, "DUE")
    assert (item["baseDate"], item["dueOn"]) == (base.isoformat(), (base + timedelta(days=30)).isoformat())


def test_정확히_30일이_된_탈퇴_회원은_그날부터_DUE이다(world: World) -> None:
    make_member(world, "edge", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START - timedelta(days=30))
    viewer(world)
    item = items(world)["WITHDRAWN_MEMBER"]
    assert (item["count"], item["state"], item["dueOn"]) == (1, "DUE", TODAY.isoformat())


def test_탈퇴한_지_30일이_안_된_회원만_있으면_건수는_0이고_기다린다(world: World) -> None:
    make_member(world, "w", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START - timedelta(days=10))
    viewer(world)
    item = items(world)["WITHDRAWN_MEMBER"]
    assert (item["count"], item["state"]) == (0, "WAITING")
    assert item["dueOn"] == (TODAY + timedelta(days=20)).isoformat()


def test_인증번호_요청은_30일이_지난_것만_세고_다른_묶음은_세지_않는다(world: World) -> None:
    for days in (40, 31, 5):
        world.factory.make("TB_CERT_DMND", OPER_BNDL_SN=world.bundle, REG_DT=START - timedelta(days=days))
    other = world.factory.make("TB_OPER_BNDL")
    world.factory.make("TB_CERT_DMND", OPER_BNDL_SN=other["OPER_BNDL_SN"], REG_DT=START - timedelta(days=90))
    viewer(world)
    item = items(world)["AUTH_RECORDS"]
    assert (item["count"], item["state"]) == (2, "DUE")


def session_row(world: World, member: dict[str, Any], tag: str, **values: Any) -> dict[str, Any]:
    return world.factory.make(
        "TB_LGN_SSN",
        OPER_BNDL_SN=world.bundle,
        MBR_SN=member["MBR_SN"],
        TKN_HASH_VL=tag.ljust(64, "0"),
        **values,
    )


def test_세션은_끝난_지_30일이_지난_것만_세고_쓰고_있는_세션은_세지_않는다(world: World) -> None:
    me = make_member(world, "ses")
    session_row(
        world,
        me,
        "a",
        ISSU_DT=START - timedelta(days=80),
        LAST_ACT_DT=START - timedelta(days=50),
        EXPRY_DT=START - timedelta(days=40),
    )  # 만료 40일 전
    session_row(
        world,
        me,
        "b",
        ISSU_DT=START - timedelta(days=50),
        LAST_ACT_DT=START - timedelta(days=45),
        EXPRY_DT=START + timedelta(days=5),
        DSCD_DT=START - timedelta(days=31),
        DSCD_RSN="로그아웃",
    )  # 폐기 31일 전
    session_row(
        world,
        me,
        "c",
        ISSU_DT=START - timedelta(days=20),
        LAST_ACT_DT=START - timedelta(days=10),
        EXPRY_DT=START - timedelta(days=10),
    )  # 만료 10일 전
    session_row(
        world,
        me,
        "d",
        ISSU_DT=START - timedelta(days=90),
        LAST_ACT_DT=START,
        EXPRY_DT=START + timedelta(minutes=30),
    )  # 쓰고 있다
    viewer(world)
    item = items(world)["SESSION_RECORDS"]
    assert (item["count"], item["state"]) == (2, "DUE")


def test_로그인_실패_이력은_90일이_지난_것만_센다(world: World) -> None:
    me = make_member(world, "fail")
    for n, days in enumerate((100, 91, 30)):
        world.factory.make(
            "TB_LGN_FAIL_HSTRY",
            OPER_BNDL_SN=world.bundle,
            MBR_SN=me["MBR_SN"],
            FAIL_DT=START - timedelta(days=days),
            DMND_ID=f"fail-{n}",
        )
    viewer(world)
    item = items(world)["LOGIN_FAILURES"]
    assert (item["count"], item["state"]) == (2, "DUE")
    base = (START - timedelta(days=100) + timedelta(hours=9)).date()
    assert (item["baseDate"], item["dueOn"]) == (base.isoformat(), (base + timedelta(days=90)).isoformat())


def test_감사이력은_3년이_지난_건수만_보이고_실행하지_않는_검토_상태다(world: World) -> None:
    world.factory.make("TB_JOB_HSTRY", OPER_BNDL_SN=world.bundle, REG_DT=START.replace(year=START.year - 4))
    world.factory.make("TB_JOB_HSTRY", OPER_BNDL_SN=world.bundle, REG_DT=START.replace(year=START.year - 1))
    viewer(world)
    item = items(world)["AUDIT_HISTORY"]
    assert (item["count"], item["state"]) == (1, "REVIEW_ONLY")
    assert item["dueOn"] == (date.fromisoformat(item["baseDate"]).replace(year=START.year - 1)).isoformat()


def test_이체_완료한_환불의_남은_계좌정보는_바로_대상이고_문자기록은_결과가_확정된_것이_바로_대상이다(
    world: World,
) -> None:
    done = refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=3), RFND_ACTNO_ENCPT_VL=b"x")
    sms = world.factory.make("TB_SMS_DMND", OPER_BNDL_SN=world.bundle, REG_DT=START - timedelta(days=2))
    world.factory.make(
        "TB_SMS_TRGT",
        SMS_DMND_SN=sms["SMS_DMND_SN"],
        MBR_SN=make_member(world, "sms1")["MBR_SN"],
        TRGT_STTS_CD="SS.FAIL",
    )  # 결과가 확정됐는데 수신번호가 남은 문자
    refund(world, status="RS.REQUEST")  # 계좌 없음
    refund(world, status="RS.DONE", RFND_DT=START - timedelta(days=1))  # 집행은 했지만 계좌가 없다
    refund(world, status="RS.APPROVE", RFND_ACTNO_ENCPT_VL=b"y")  # 계좌는 있지만 아직 집행 전이다
    refund(
        world, status="RS.DONE", RFND_DT=START + timedelta(hours=1), RFND_ACTNO_ENCPT_VL=b"z"
    )  # 완료 시각 전이라 아직 세지 않는다
    other = world.factory.make("TB_OPER_BNDL")
    world.factory.make("TB_SMS_DMND", OPER_BNDL_SN=other["OPER_BNDL_SN"], REG_DT=START - timedelta(days=9))
    viewer(world)
    got = items(world)
    assert (
        got["REFUND_ACCOUNT"]["count"],
        got["REFUND_ACCOUNT"]["state"],
        got["REFUND_ACCOUNT"]["dueOn"],
    ) == (
        1,
        "DUE",
        (TODAY - timedelta(days=3)).isoformat(),
    )  # 이체 완료를 확인한 날부터 바로 대상이다
    assert (got["SMS_RECORDS"]["count"], got["SMS_RECORDS"]["state"], got["SMS_RECORDS"]["dueOn"]) == (
        1,
        "DUE",
        (TODAY - timedelta(days=2)).isoformat(),
    )  # 결과가 확정된 문자는 바로 대상이다(다른 묶음의 문자는 세지 않는다)
    assert done  # 환불 한 건이 계좌와 함께 센다


def test_상세는_규칙과_처리_항목을_주고_실행_가능은_아직_false이며_없는_번호는_404이다(world: World) -> None:
    make_member(world, "w", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START - timedelta(days=60))
    viewer(world)
    one = call(world, "GET", "/retention/1").json()
    assert one["target"] == "WITHDRAWN_MEMBER" and one["count"] == 1 and one["state"] == "DUE"
    assert one["fields"] == ["이름", "휴대전화", "이메일"] and "30일" in one["rule"]
    assert one["executions"] == [] and one["canExecute"] is False
    for bad in ("0", "8", "9999999999"):
        assert call(world, "GET", f"/retention/{bad}").status_code == 404
