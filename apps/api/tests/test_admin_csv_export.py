# 관리자 목록 CSV 내보내기(공통 규칙, 권한·범위, 목록과 같은 조건, 수식 주입 방지, 한도, 작업이력)를 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin import csv_export
from app.domain.admin.csv_export import build_csv, cell, csv_response
from tests.test_admin_access import dong
from tests.test_admin_applications import member
from tests.test_admin_education import Kit, boss, cycle_body, post_cycle
from tests.test_admin_refunds import call, refund, staff, use
from tests.test_admin_transactions import pending
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_applications_read import open_course as _open_course
from tests.test_courses_public import course as make_course
from tests.test_courses_public import cycle as make_cycle
from tests.world import ADMIN, START, World

pytestmark = pytest.mark.db

DAY = timedelta(days=1)


def rows_of(response: Any) -> list[list[str]]:
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def fetch(w: World, path: str) -> Any:
    who = w.current  # type: ignore[attr-defined]
    return w.client.get(f"{ADMIN}{path}", headers={"X-CSRF-Token": who.csrf})


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


# --- 공통 규칙(DB 없이) -------------------------------------------------------------------------


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_수식으로_읽히는_글자는_앞에_작은따옴표를_붙인다(start: str) -> None:
    assert cell(f"{start}CMD()") == f"'{start}CMD()"


def test_일반_글자와_숫자와_빈_값은_그대로다() -> None:
    assert (cell("요가"), cell("a=b"), cell(None), cell("")) == ("요가", "a=b", "", "")
    assert (cell(30000), cell(-5), cell(0), cell(1.5)) == (
        "30000",
        "-5",
        "0",
        "1.5",
    )  # 숫자의 부호는 막지 않는다
    assert (cell(True), cell(False)) == ("Y", "N")


def test_시각은_한국_시각이고_날짜는_연월일이다() -> None:
    assert cell(datetime(2026, 11, 9, 15, 30, 5)) == "2026-11-10 00:30:05"  # DB의 UTC를 한국 시각으로
    assert cell(date(2026, 11, 9)) == "2026-11-09"


def test_머리글도_수식_주입을_거치고_BOM과_CRLF와_따옴표_이스케이프를_지킨다() -> None:
    raw = build_csv(["=열", "메모"], [["a,b", 'c"d'], ["줄\n바꿈", "-1"]])
    assert raw.startswith("﻿".encode())
    text_ = raw.decode("utf-8-sig")
    assert text_ == '\'=열,메모\r\n"a,b","c""d"\r\n"줄\n바꿈",\'-1\r\n'
    assert list(csv.reader(io.StringIO(text_))) == [["'=열", "메모"], ["a,b", 'c"d'], ["줄\n바꿈", "'-1"]]


def test_응답은_첨부파일로_내려가고_캐시하지_않고_한글_파일명을_함께_준다() -> None:
    response = csv_response("신청 목록.csv", b"x")
    disposition = response.headers["content-disposition"]
    assert (
        response.media_type == "text/csv; charset=utf-8" and response.headers["cache-control"] == "no-store"
    )
    assert (
        'filename="export.csv"' in disposition
        and "filename*=UTF-8''%EC%8B%A0%EC%B2%AD%20%EB%AA%A9%EB%A1%9D.csv" in disposition
    )
    assert (
        'filename="applications.csv"' in csv_response("applications.csv", b"x").headers["content-disposition"]
    )
    # 따옴표·줄바꿈이 헤더로 새지 않는다
    hostile = csv_response('a"b\r\nSet-Cookie: x=1.csv', b"x").headers["content-disposition"]
    assert "\r" not in hostile and "\n" not in hostile and 'filename="a_b_Set-Cookie_x_1.csv"' in hostile


# --- 신청 ---------------------------------------------------------------------------------------


def test_신청_CSV는_목록과_같은_조건이고_이름을_가리며_페이지_제한이_없다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = course(world)
    made = [
        application(world, member(world, "홍길동"), row, "ES.CONFIRM", APLY_DT=START - n * DAY)
        for n in range(25)
    ]
    cancelled = application(world, member(world, "박다라"), row, "ES.CANCEL", APLY_DT=START)
    payment(world, made[0], "PS.PAID")
    use(world, staff(world, "boss", "AU.APLY_R"))
    listed = call(world, "GET", "/applications").json()
    assert len(listed["items"]) == 20 and listed["total"] == 26  # 목록은 20건씩이다
    table = rows_of(fetch(world, "/applications/export.csv"))
    assert table[0] == [
        "신청번호",
        "강좌",
        "신청자",
        "신청 상태",
        "표시 상태",
        "결제 상태",
        "환불 상태",
        "신청일시",
    ]
    assert len(table) == 1 + 26  # 내보내기는 페이지 제한이 없다
    assert {r[2] for r in table[1:]} == {"홍*동", "박*라"}
    by_status = rows_of(fetch(world, "/applications/export.csv?status=CANCELLED"))
    assert [r[0] for r in by_status[1:]] == [str(cancelled["ATNLC_APLY_SN"])]
    first = table[1]  # 목록과 같은 정렬(최신 신청이 먼저)
    assert first[0] == str(cancelled["ATNLC_APLY_SN"]) and first[7] == "2026-11-09 18:00:00"  # 한국 시각
    paid = next(r for r in table[1:] if r[0] == str(made[0]["ATNLC_APLY_SN"]))
    assert paid[5] == "PAID" and paid[6] == ""
    assert monkeypatch  # 아래 한도 시험과 같은 도구를 쓴다


def test_동_담당자의_신청_CSV에는_범위_밖_강좌가_없다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    ok = application(world, member(world), course(world, DONG_SN=mine["DONG_SN"]), "ES.CONFIRM")
    application(world, member(world), course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]), "ES.CONFIRM")
    application(world, member(world), course(world, CORS_NM="공통"), "ES.CONFIRM")
    use(world, staff(world, "d", "AU.APLY_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [r[0] for r in rows_of(fetch(world, "/applications/export.csv"))[1:]] == [str(ok["ATNLC_APLY_SN"])]


def test_신청_CSV는_조회_권한이_없으면_403이고_로그인이_없으면_401이다(world: World) -> None:
    assert world.client.get(f"{ADMIN}/applications/export.csv").status_code == 401
    use(world, staff(world, "x", "AU.STLM_R"))
    assert fetch(world, "/applications/export.csv").status_code == 403


def test_수식처럼_시작하는_강좌명은_작은따옴표가_붙는다(world: World) -> None:
    application(world, member(world), course(world, CORS_NM="=HYPERLINK(1)"), "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.APLY_R"))
    assert rows_of(fetch(world, "/applications/export.csv"))[1][1] == "'=HYPERLINK(1)"


def test_한도를_넘으면_만들지_않고_거절하고_한도_정확히는_만든다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = course(world)
    for _ in range(3):
        application(world, member(world), row, "ES.CONFIRM")
    use(world, staff(world, "boss", "AU.APLY_R"))
    monkeypatch.setattr(csv_export, "MAX_ROWS", 3)
    assert len(rows_of(fetch(world, "/applications/export.csv"))) == 4  # 정확히 한도는 만든다
    monkeypatch.setattr(csv_export, "MAX_ROWS", 2)
    r = fetch(world, "/applications/export.csv")
    assert (
        r.status_code == 422 and r.json()["code"] == "RULE_REJECTED" and "조건을 좁혀" in r.json()["message"]
    )
    done = world.db.execute(text("SELECT COUNT(*) FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT'")).scalar()
    assert done == 1  # 거절한 요청은 만든 것이 아니라 기록하지 않는다


def test_만들_때마다_작업이력에_건수와_조건_이름만_남긴다(world: World) -> None:
    application(world, member(world, "김비밀"), course(world), "ES.CONFIRM")
    who = staff(world, "boss", "AU.APLY_R")
    use(world, who)
    rows_of(fetch(world, "/applications/export.csv?q=김비밀&status=CONFIRMED"))
    job = (
        world.db.execute(
            text(
                "SELECT ACTR_TYPE_CD a, MNGR_SN m, TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT'"
            )
        )
        .mappings()
        .one()
    )
    assert (job["a"], job["m"], job["t"]) == ("AK.ADMIN", who.sn, "TB_ATNLC_APLY")
    assert job["c"] == "1건 내보냄(조건: q,status)" and "김비밀" not in job["c"]


def test_모든_목록_CSV는_만들_때마다_대상_테이블과_건수를_작업이력에_남긴다(world: World) -> None:
    kit = Kit(world)
    inside = make_course(
        world,
        kit.cycle,
        "요가",
        DONG_SN=kit.dong["DONG_SN"],
        CORS_CLSF_SN=kit.category["CORS_CLSF_SN"],
        INSTR_SN=kit.instructor["INSTR_SN"],
    )
    application(world, member(world), {"CORS_SN": inside["CORS_SN"]}, "ES.CONFIRM")
    refund(world)
    pending(world)
    boss(world, "AU.CORS_R", "AU.CORS_W", "AU.CONF_W", "AU.APLY_R", "AU.RFND_A", "AU.STLM_R")
    for path in ("/applications", "/refunds", "/transactions", "/courses", "/cycles"):
        rows_of(fetch(world, f"{path}/export.csv"))
    logged = (
        world.db.execute(
            text(
                "SELECT TRGT_TBL_NM t, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT' ORDER BY JOB_HSTRY_SN"
            )
        )
        .mappings()
        .all()
    )
    assert [(r["t"], r["c"].split("건")[0]) for r in logged] == [
        ("TB_ATNLC_APLY", "3"),
        ("TB_RFND", "1"),
        ("TB_STLM", "2"),
        ("TB_CORS", "3"),
        ("TB_EDU_CYCL", "2"),  # 기준 정보의 기수와 환불·결제 도우미가 만든 기본 기수
    ]


# --- 환불 ---------------------------------------------------------------------------------------


def test_환불_CSV는_승인_권한이_있어야_하고_계좌를_담지_않는다(world: World) -> None:
    r1 = refund(
        world, amount=12000, RFND_BANK_CD="004", RFND_ACTNO_ENCPT_VL="x" * 20, RFND_DPSTR_ENCPT_VL="y" * 20
    )
    use(world, staff(world, "x", "AU.RFND_X"))
    assert fetch(world, "/refunds/export.csv").status_code == 403  # 목록과 같은 권한이다
    use(world, staff(world, "a", "AU.RFND_A"))
    table = rows_of(fetch(world, "/refunds/export.csv"))
    assert table[0] == [
        "환불번호",
        "신청번호",
        "강좌",
        "요청액",
        "상태",
        "접수일",
        "경과 영업일",
        "지연",
        "요청자",
    ]
    assert table[1][0] == str(r1["RFND_SN"]) and table[1][3] == "12000" and table[1][4] == "REQUESTED"
    assert table[1][5] == "2026-11-09" and table[1][7] == "N" and table[1][8] == "MEMBER"
    assert all(len(row) == 9 for row in table)  # 정해진 열만 있다
    dumped = "".join(",".join(r) for r in table)
    assert "004" not in dumped and "xxxx" not in dumped  # 은행·계좌 정보가 없다


def test_환불_CSV는_목록과_같은_정렬과_조건을_쓴다(world: World) -> None:
    done = refund(world, status="RS.DONE", RFND_DT=START)
    hold = refund(world, status="RS.HOLD", RFND_DMND_DT=START - 5 * DAY)
    new = refund(world, RFND_DMND_DT=START - 1 * DAY)
    use(world, staff(world, "a", "AU.RFND_A"))
    assert [r[0] for r in rows_of(fetch(world, "/refunds/export.csv"))[1:]] == [
        str(hold["RFND_SN"]),
        str(new["RFND_SN"]),
        str(done["RFND_SN"]),
    ]
    assert [r[0] for r in rows_of(fetch(world, "/refunds/export.csv?status=DONE"))[1:]] == [
        str(done["RFND_SN"])
    ]
    assert call(world, "GET", "/refunds?status=DONE").json()["total"] == 1


# --- 결제 ---------------------------------------------------------------------------------------


def test_결제_CSV는_확인_중인_금액을_상태_열로_구분하고_충돌_표시를_담는다(world: World) -> None:
    _, waiting = pending(world, STLM_DMND_DT=START - DAY)
    _, paid = pending(world, state="PS.PAID", STLM_APRV_NO="A1", STLM_APRV_DT=START, STLM_DMND_DT=START)
    world.factory.make(
        "TB_STLM_EVENT", STLM_SN=waiting["STLM_SN"], EVENT_TYPE_CD="ET.RECON", EVENT_ID="RECHECK:1"
    )
    from app.audit import record_job

    record_job(
        world.db,
        actor="AK.SYSTEM",
        job="PAY_WEBHOOK",
        table="TB_STLM",
        key=waiting["STLM_SN"],
        request_id="r",
        now=START,
        bundle_sn=world.bundle,
        result="JR.DENY",
        change="충돌",
    )
    use(world, staff(world, "s", "AU.STLM_R"))
    table = rows_of(fetch(world, "/transactions/export.csv"))
    assert table[0] == [
        "주문번호",
        "신청번호",
        "금액",
        "수단",
        "상태",
        "요청시각",
        "PG 승인시각",
        "재조회 횟수",
        "충돌 통보",
    ]
    assert [r[4] for r in table[1:]] == ["PENDING", "PAID"]  # 확인 중이 먼저다
    assert table[1][2] == "30000" and table[1][7] == "1" and table[1][8] == "Y" and table[1][6] == ""
    assert table[2][8] == "N" and table[2][6] != ""
    only = rows_of(fetch(world, "/transactions/export.csv?conflictOnly=true"))
    assert [r[0] for r in only[1:]] == [waiting["STLM_NO"]] and paid


def test_결제_CSV는_조회_권한이_없으면_403이다(world: World) -> None:
    use(world, staff(world, "x", "AU.APLY_R"))
    assert fetch(world, "/transactions/export.csv").status_code == 403


def test_결제_CSV도_동_범위를_따른다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    visible = pending(world, course(world, DONG_SN=mine["DONG_SN"]))[1]
    pending(world, course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))
    use(world, staff(world, "d", "AU.STLM_R", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [r[0] for r in rows_of(fetch(world, "/transactions/export.csv"))[1:]] == [visible["STLM_NO"]]


# --- 기수·강좌 ----------------------------------------------------------------------------------


def test_기수_CSV는_한국_날짜로_기간을_담고_기수_설정_권한이_있어야_한다(world: World) -> None:
    use(world, staff(world, "x", "AU.CORS_R"))
    assert fetch(world, "/cycles/export.csv").status_code == 403
    boss(world)
    post_cycle(world, cycle_body())
    table = rows_of(fetch(world, "/cycles/export.csv"))
    assert table[0] == [
        "기수",
        "연도",
        "차수",
        "교육 시작",
        "교육 종료",
        "접수 시작",
        "접수 종료",
        "상태",
        "강좌 수",
    ]
    assert table[1] == [
        "2027년 제1기",
        "2027",
        "1",
        "2027-01-04",
        "2027-03-31",
        "2026-12-01",
        "2026-12-10",
        "ACTIVE",
        "0",
    ]


def test_강좌_CSV는_목록과_같은_조건이고_범위_밖_강좌와_수식이_걸러진다(world: World) -> None:
    kit = Kit(world)
    other = dong(world, "나동")
    inside = make_course(
        world,
        kit.cycle,
        "=요가",
        DONG_SN=kit.dong["DONG_SN"],
        CORS_CLSF_SN=kit.category["CORS_CLSF_SN"],
        INSTR_SN=kit.instructor["INSTR_SN"],
    )
    make_course(world, make_cycle(world, "2기", EDU_CYCL=33), "탁구", DONG_SN=other["DONG_SN"])
    application(world, member(world), {"CORS_SN": inside["CORS_SN"]}, "ES.CONFIRM")
    use(world, staff(world, "d", "AU.CORS_R", kind="SK.DONG", dong_sn=kit.dong["DONG_SN"]))
    table = rows_of(fetch(world, "/courses/export.csv"))
    assert table[0][:4] == ["강좌", "기수", "분류", "강사"] and len(table) == 2
    row = table[1]
    assert row[0] == "'=요가" and row[2] == "생활체육" and row[3] == "강사님"
    assert (row[6], row[7], row[8], row[9]) == ("10", "1", "0", "30000")  # 정원·점유·대기·수강료
    boss(world)
    assert len(rows_of(fetch(world, "/courses/export.csv"))) == 3
    assert len(rows_of(fetch(world, "/courses/export.csv?q=탁"))) == 2
    assert RESIDENT
