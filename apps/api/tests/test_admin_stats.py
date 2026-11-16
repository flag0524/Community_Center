# 관리자 대시보드와 수요·정산·출석 통계(좌석점유·유효수요·순수납·출석률 정의, 강좌 동 범위)와 수요·정산 CSV를 실제 앱과 MariaDB로 확인하는 시험
import csv
import io
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_attendance import mark, sheet, teacher
from tests.test_admin_refunds import call, refund, staff, use
from tests.test_applications_read import RESIDENT, application, open_course, payment, the_cycle
from tests.test_board_public import board
from tests.test_courses_public import cycle as new_cycle
from tests.test_instructor_member import category
from tests.test_member_inquiries import answered, asked
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)
DAY = timedelta(days=1)


def who(w: World, name: str = "홍길동") -> dict[str, Any]:
    return make_member(w, f"st{next(_n)}", MBR_NM=name, **RESIDENT)


def taken(w: World, c: dict[str, Any], state: str, **values: Any) -> dict[str, Any]:
    return application(w, who(w), c, state, **values)


def viewer(w: World, *codes: str, **kw: Any) -> Any:
    actor = staff(w, f"sv{next(_n)}", "AU.STAT_R", *codes, **kw)
    use(w, actor)
    return actor


def rows_of(w: World, qs: str = "") -> dict[str, Any]:
    res = call(w, "GET", f"/stats/demand{qs}")
    assert res.status_code == 200, res.text
    return {r["courseName"]: r for r in res.json()["rows"]}


# --- 권한·입력 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_통계_권한이_없으면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/dashboard").status_code == 401
    use(world, staff(world, "nobody", "AU.APLY_R", "AU.STLM_R"))
    for path in (
        "/dashboard",
        "/stats/demand",
        "/stats/settlement",
        "/stats/attendance",
        "/stats/demand/export.csv",
        "/stats/settlement/export.csv",
    ):
        assert call(world, "GET", path).status_code == 403, path


def test_종료일이_시작일보다_앞서면_422다(world: World) -> None:
    viewer(world)
    for path in ("/stats/demand", "/stats/settlement", "/stats/attendance", "/stats/demand/export.csv"):
        res = call(world, "GET", f"{path}?from=2026-11-10&to=2026-11-09")
        assert res.status_code == 422 and "to" in res.json()["fields"], path


# --- 수요 ---------------------------------------------------------------------------------------


def test_수요는_좌석점유와_유효수요를_정의대로_세고_없는_수요는_0이다(world: World) -> None:
    sports = category(world, "생활체육")
    big = open_course(world, CORS_NM="요가", RCRT_NOPE=3, CORS_CLSF_SN=sports["CORS_CLSF_SN"])
    empty = open_course(world, CORS_NM="서예", RCRT_NOPE=10)
    repeat = who(world)
    application(world, repeat, big, "ES.CONFIRM")
    application(world, repeat, big, "ES.CANCEL", RTRCN_DT=START, RTRCN_RSN="취소")  # 같은 사람의 다른 신청
    taken(world, big, "ES.COMPLETE")
    taken(world, big, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START + timedelta(minutes=10))
    unknown = taken(world, big, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START + timedelta(minutes=10))
    payment(world, unknown, "PS.PENDING")
    taken(world, big, "ES.WAIT", WTNG_SEQ=1)
    taken(world, big, "ES.EXPIRE", RTRCN_DT=START, RTRCN_RSN="만료")
    viewer(world)
    out = rows_of(world)
    y = out["요가"]
    assert (y["categoryName"], y["capacity"], y["applications"], y["uniqueApplicants"]) == (
        "생활체육",
        3,
        7,
        6,
    )
    assert (y["confirmed"], y["hold"], y["paymentUnknown"], y["waiting"], y["cancelled"]) == (2, 1, 1, 1, 2)
    assert (y["seatsHeld"], y["effectiveDemand"], y["demandRatio"]) == (4, 5, 1.6667)
    s = out["서예"]
    assert (s["categoryName"], s["applications"], s["effectiveDemand"], s["demandRatio"]) == (
        "미분류",
        0,
        0,
        0.0,
    )
    names = [r["courseName"] for r in call(world, "GET", "/stats/demand").json()["rows"]]
    assert names == ["요가", "서예"]  # 유효수요가 큰 강좌가 먼저다
    assert empty["CORS_SN"] and call(world, "GET", "/stats/demand").json()["basis"]["basisAt"]


def test_수요는_기수와_분야와_신청일로_거른다(world: World) -> None:
    c1 = the_cycle(world)
    c2 = new_cycle(world, "다른 기수", EDU_CYCL=3)
    sports, arts = category(world, "생활체육"), category(world, "문화예술")
    a = open_course(world, CORS_NM="요가", CORS_CLSF_SN=sports["CORS_CLSF_SN"])
    from tests.test_courses_public import course as make_course  # noqa: PLC0415

    b = make_course(world, c2, "서예", CORS_CLSF_SN=arts["CORS_CLSF_SN"])
    taken(world, a, "ES.CONFIRM", APLY_DT=START - 5 * DAY)
    taken(world, a, "ES.CONFIRM", APLY_DT=START)
    taken(world, b, "ES.CONFIRM", APLY_DT=START)
    viewer(world)
    assert set(rows_of(world, f"?cycleId={c1['EDU_CYCL_SN']}")) == {"요가"}
    assert set(rows_of(world, f"?cycleId={c2['EDU_CYCL_SN']}")) == {"서예"}
    assert set(rows_of(world, f"?categoryId={arts['CORS_CLSF_SN']}")) == {"서예"}
    assert rows_of(world, "?from=2026-11-09")["요가"]["applications"] == 1  # 신청일(한국 날짜) 기준
    assert rows_of(world, "?to=2026-11-04")["요가"]["applications"] == 1
    assert rows_of(world, "?from=2026-11-04&to=2026-11-09")["요가"]["applications"] == 2
    assert rows_of(world, "?from=2026-12-01")["요가"]["applications"] == 0
    body = call(
        world, "GET", f"/stats/demand?cycleId={c1['EDU_CYCL_SN']}&from=2026-11-04&to=2026-11-09"
    ).json()["basis"]
    assert (body["cycleId"], body["fromDate"], body["toDate"]) == (
        str(c1["EDU_CYCL_SN"]),
        "2026-11-04",
        "2026-11-09",
    )


def test_동_담당자는_자기_동_강좌만_집계하고_동이_없는_강좌는_뺀다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = open_course(world, CORS_NM="가동 강좌", DONG_SN=a["DONG_SN"])
    other = open_course(world, CORS_NM="나동 강좌", DONG_SN=b["DONG_SN"])
    common = open_course(world, CORS_NM="공통 강좌")
    for c in (mine, other, common):
        taken(world, c, "ES.CONFIRM")
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert set(rows_of(world)) == {"가동 강좌"}
    viewer(world)
    assert set(rows_of(world)) == {"가동 강좌", "나동 강좌", "공통 강좌"}


# --- 정산 ---------------------------------------------------------------------------------------


def test_정산은_승인액에서_완료_환불액을_빼고_확인_중_금액은_따로_둔다(world: World) -> None:
    c = open_course(world)
    card = taken(world, c, "ES.CONFIRM")
    bank = taken(world, c, "ES.CONFIRM")
    p_card = payment(world, card, "PS.PAID", STLM_MNS_CD="PM.CARD", STLM_AMT=30000)
    payment(world, bank, "PS.PAID", STLM_MNS_CD="PM.TRANSFER", STLM_AMT=20000)
    payment(
        world,
        taken(world, c, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START),
        "PS.PENDING",
        STLM_AMT=15000,
    )
    payment(world, taken(world, c, "ES.CANCEL", RTRCN_DT=START, RTRCN_RSN="x"), "PS.FAIL", STLM_AMT=9000)
    payment(world, taken(world, c, "ES.CANCEL", RTRCN_DT=START, RTRCN_RSN="x"), "PS.CANCEL", STLM_AMT=8000)
    for status, amount, extra in (("RS.DONE", 10000, {"RFND_DT": START}), ("RS.REQUEST", 5000, {})):
        world.factory.make(
            "TB_RFND",
            STLM_SN=p_card["STLM_SN"],
            RFND_AMT=amount,
            RFND_STTS_CD=status,
            RFND_DMND_DT=START,
            DMND_MBR_SN=card["MBR_SN"],
            **extra,
        )
    viewer(world)
    out = call(world, "GET", "/stats/settlement").json()
    assert (out["approvedAmount"], out["refundedAmount"], out["netRevenue"], out["unknownAmount"]) == (
        50000,
        10000,
        40000,
        15000,
    )
    methods = {m["method"]: m for m in out["byMethod"]}
    assert [m["method"] for m in out["byMethod"]] == ["CARD", "TRANSFER"]
    assert (methods["CARD"]["approved"], methods["CARD"]["refunded"], methods["CARD"]["net"]) == (
        30000,
        10000,
        20000,
    )
    assert (methods["TRANSFER"]["approved"], methods["TRANSFER"]["refunded"], methods["TRANSFER"]["net"]) == (
        20000,
        0,
        20000,
    )
    assert out["approvedAmount"] == sum(m["approved"] for m in out["byMethod"])


def test_정산은_승인일과_기수와_동으로_거른다(world: World) -> None:
    c1 = the_cycle(world)
    c2 = new_cycle(world, "다른 기수", EDU_CYCL=3)
    from tests.test_courses_public import course as make_course  # noqa: PLC0415

    a = dong(world, "가동")
    mine = open_course(world, CORS_NM="가동", DONG_SN=a["DONG_SN"])
    other = make_course(world, c2, "다른 기수 강좌")
    payment(world, taken(world, mine, "ES.CONFIRM"), "PS.PAID", STLM_AMT=30000, STLM_APRV_DT=START - 5 * DAY)
    payment(world, taken(world, mine, "ES.CONFIRM"), "PS.PAID", STLM_AMT=20000, STLM_APRV_DT=START)
    payment(world, taken(world, other, "ES.CONFIRM"), "PS.PAID", STLM_AMT=10000, STLM_APRV_DT=START)
    viewer(world)

    def amount(qs: str) -> int:
        return int(call(world, "GET", f"/stats/settlement{qs}").json()["approvedAmount"])

    assert amount("") == 60000
    assert (
        amount(f"?cycleId={c1['EDU_CYCL_SN']}") == 50000 and amount(f"?cycleId={c2['EDU_CYCL_SN']}") == 10000
    )
    assert amount("?from=2026-11-09") == 30000 and amount("?to=2026-11-04") == 30000
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert amount("") == 50000


# --- 출석 ---------------------------------------------------------------------------------------


def test_출석률은_체크한_건만_분모로_하고_지운_출석부와_범위_밖은_뺀다(world: World) -> None:
    a = dong(world, "가동")
    teacher_row = teacher(world, "김강사")
    c = open_course(world, CORS_NM="요가", DONG_SN=a["DONG_SN"], INSTR_SN=teacher_row["INSTR_SN"])
    quiet = open_course(world, CORS_NM="조용한 강좌", DONG_SN=a["DONG_SN"])
    far = open_course(world, CORS_NM="다른 동")
    s1 = sheet(world, c, "20261102", 1, instructor=teacher_row)
    s2 = sheet(world, c, "20261109", 2, instructor=teacher_row)
    gone = sheet(world, c, "20261109", 3, DEL_YN="Y", instructor=teacher_row)
    for result in ("AR.PRESENT", "AR.PRESENT", "AR.ABSENT", "AR.UNCHECKED"):
        mark(world, s1, c, who(world), result)
    mark(world, s2, c, who(world), "AR.ABSENT")
    mark(world, gone, c, who(world), "AR.ABSENT")  # 지운 출석부
    mark(world, sheet(world, far, "20261109", 1), far, who(world), "AR.PRESENT")
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    out = call(world, "GET", "/stats/attendance").json()["rows"]
    assert [r["courseName"] for r in out] == ["요가"]  # 출석부가 없는 강좌와 다른 동은 없다
    assert (out[0]["instructorName"], out[0]["present"], out[0]["absent"], out[0]["rate"]) == (
        "김강사",
        2,
        2,
        50.0,
    )
    first = call(world, "GET", "/stats/attendance?from=2026-11-02&to=2026-11-02").json()["rows"][0]
    assert (first["present"], first["absent"], first["rate"]) == (2, 1, 66.7)
    viewer(world)
    names = {r["courseName"] for r in call(world, "GET", "/stats/attendance").json()["rows"]}
    assert names == {"요가", "다른 동"} and quiet["CORS_SN"]
    assert call(world, "GET", "/stats/attendance/export.csv").status_code in (
        404,
        405,
    )  # 출석은 내보내지 않는다


def test_체크한_건이_없는_강좌의_출석률은_null이다(world: World) -> None:
    c = open_course(world)
    mark(world, sheet(world, c, "20261102", 1), c, who(world), "AR.UNCHECKED")
    viewer(world)
    [row] = call(world, "GET", "/stats/attendance").json()["rows"]
    assert (row["present"], row["absent"], row["rate"]) == (0, 0, None)


# --- 대시보드 -----------------------------------------------------------------------------------


def test_신청이_없으면_요약은_null이고_0과_구분한다(world: World) -> None:
    viewer(world)
    out = call(world, "GET", "/dashboard").json()
    assert out["summary"] is None and out["demand"] == [] and out["tasks"] == [] and out["recent"] == []
    the_cycle(world)
    world.db.commit()
    out = call(world, "GET", "/dashboard").json()
    assert out["summary"] is None and out["basis"]["cycleId"] is not None


def test_대시보드는_가장_최근_기수를_기본으로_접수_현황을_요약한다(world: World) -> None:
    older = new_cycle(world, "지난 기수", EDU_CYCL=1)
    latest = the_cycle(world)
    from tests.test_courses_public import course as make_course  # noqa: PLC0415

    old_course = make_course(world, older, "지난 강좌")
    c = open_course(world, CORS_NM="요가", RCRT_NOPE=2)
    taken(world, old_course, "ES.CONFIRM")
    done = taken(world, c, "ES.CONFIRM")
    taken(world, c, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START)
    taken(world, c, "ES.WAIT", WTNG_SEQ=1)
    taken(world, c, "ES.CANCEL", RTRCN_DT=START, RTRCN_RSN="x")
    payment(world, done, "PS.PAID", STLM_AMT=30000, STLM_MNS_CD="PM.CARD")
    refund(world, status="RS.DONE", amount=10000, row=c, RFND_DT=START)
    viewer(world)
    out = call(world, "GET", "/dashboard").json()
    assert out["basis"]["cycleId"] == str(latest["EDU_CYCL_SN"])
    s = out["summary"]
    assert (
        s["applications"],
        s["uniqueApplicants"],
        s["confirmed"],
        s["seatsHeld"],
        s["waiting"],
        s["cancelled"],
    ) == (5, 5, 1, 2, 1, 2)  # 환불 시험 도우미가 취소된 신청 한 건을 함께 만든다
    assert s["netRevenue"] == 50000  # 승인 30000 + 환불 시험 도우미가 만든 결제 30000 − 완료 환불 10000
    assert [d["courseName"] for d in out["demand"]][:1] == ["요가"]
    older_out = call(world, "GET", f"/dashboard?cycleId={older['EDU_CYCL_SN']}").json()
    assert older_out["summary"]["applications"] == 1 and older_out["basis"]["cycleId"] == str(
        older["EDU_CYCL_SN"]
    )
    assert call(world, "GET", "/dashboard?cycleId=999999999").json()["summary"] is None


def test_강좌별_수요는_열_개까지_유효수요_순이다(world: World) -> None:
    for n in range(12):
        c = open_course(world, CORS_NM=f"강좌{n:02d}")
        for _ in range(n % 4):
            taken(world, c, "ES.CONFIRM")
    viewer(world)
    demand = call(world, "GET", "/dashboard").json()["demand"]
    assert len(demand) == 10
    ratios = [d["effectiveDemand"] for d in demand]
    assert ratios == sorted(ratios, reverse=True) and ratios[0] == 3


def test_확인할_업무는_권한이_있는_종류만_그_범위의_개수로_나온다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = open_course(world, CORS_NM="가동", DONG_SN=a["DONG_SN"])
    elsewhere = open_course(world, CORS_NM="나동", DONG_SN=b["DONG_SN"])
    for c in (mine, mine, elsewhere):
        payment(world, taken(world, c, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START), "PS.PENDING")
    refund(world, status="RS.REQUEST", row=mine)
    refund(world, status="RS.HOLD", row=mine)
    refund(world, status="RS.REQUEST", row=elsewhere)
    refund(world, status="RS.DONE", row=mine, RFND_DT=START)
    world.factory.make(
        "TB_INSTR_APLY",
        SRNG_STTS_CD="IA.WAIT",
        RCPT_CHNL_CD="IC.ONLINE",
        APLCT_NM="지원",
        TELNO_ENCPT_VL="x",
        HOPE_CORS_NM="y",
        RLS_HOPE_YN="N",
        SBMSN_DT=START,
    )
    qna = board(world, "qna", MBR_WRT_YN="Y", ANS_USE_YN="Y")
    asker = who(world)
    asked(world, qna, asker, "미답변 1", DONG_SN=a["DONG_SN"])
    asked(world, qna, asker, "미답변 2", DONG_SN=b["DONG_SN"])
    answered(world, asked(world, qna, asker, "답변 있음", DONG_SN=a["DONG_SN"]))
    viewer(world)
    assert call(world, "GET", "/dashboard").json()["tasks"] == []  # 통계 권한만으로는 업무를 보지 않는다
    viewer(world, "AU.STLM_W", "AU.RFND_A", "AU.INSTR_W", "AU.POST_W", kind="SK.GROUP")
    tasks = {t["kind"]: t["count"] for t in call(world, "GET", "/dashboard").json()["tasks"]}
    assert tasks == {"PAYMENT_UNKNOWN": 3, "REFUND_REVIEW": 3, "INSTRUCTOR_REVIEW": 1, "INQUIRY_ANSWER": 2}
    viewer(world, "AU.STLM_W", "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"])
    tasks = {t["kind"]: t["count"] for t in call(world, "GET", "/dashboard").json()["tasks"]}
    assert tasks == {"PAYMENT_UNKNOWN": 2, "INQUIRY_ANSWER": 1}


def test_최근_작업은_작업이력_조회_권한이_있을_때만_최근_순으로_나온다(world: World) -> None:
    boss = staff(world, "boss", "AU.STAT_R", "AU.LOG_R")
    world.db.execute(
        text(
            "INSERT INTO TB_JOB_HSTRY (OPER_BNDL_SN, ACTR_TYPE_CD, MNGR_SN, MBR_SN, JOB_CD, TRGT_TBL_NM, TRGT_KEY_VL, JOB_RSLT_CD, DMND_ID, REG_DT)"
            " VALUES (:b, 'AK.ADMIN', :m, NULL, 'RFND_APPROVE', 'TB_RFND', '77', 'JR.SUCCESS', 'r1', :t1),"
            "        (:b, 'AK.SYSTEM', NULL, NULL, 'PAY_EXPIRE', 'TB_ATNLC_APLY', '88', 'JR.SUCCESS', 'r2', :t2),"
            "        (:b, 'AK.MEMBER', NULL, :mb, 'APLY_CREATE', 'TB_ATNLC_APLY', '99', 'JR.SUCCESS', 'r3', :t2)"
        ),
        {
            "b": world.bundle,
            "m": boss.sn,
            "mb": who(world)["MBR_SN"],
            "t1": START - timedelta(hours=2),
            "t2": START - timedelta(hours=1),
        },
    )
    use(world, boss)
    recent = call(world, "GET", "/dashboard").json()["recent"]
    mine = [r for r in recent if r["action"] in ("RFND_APPROVE", "PAY_EXPIRE", "APLY_CREATE")]
    assert [(r["action"], r["actor"], r["target"]) for r in mine] == [
        ("PAY_EXPIRE", "SYSTEM", "TB_ATNLC_APLY 88"),
        ("RFND_APPROVE", "김관리", "TB_RFND 77"),
    ]  # 회원의 작업은 보이지 않는다
    viewer(world)
    assert call(world, "GET", "/dashboard").json()["recent"] == []


# --- CSV ----------------------------------------------------------------------------------------


def test_수요_CSV는_첫_줄에_집계_조건을_넣고_수식을_막으며_작업이력을_남긴다(world: World) -> None:
    c = open_course(world, CORS_NM="=SUM(A1) 요가", RCRT_NOPE=4)
    taken(world, c, "ES.CONFIRM")
    taken(world, c, "ES.WAIT", WTNG_SEQ=1)
    me = viewer(world)
    res = call(world, "GET", "/stats/demand/export.csv?from=2026-11-01&to=2026-11-30")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    assert res.content.startswith("﻿".encode()) and "no-store" in res.headers["cache-control"]
    table = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert (
        table[0][0].startswith("# 집계 조건: 기간 2026-11-01~2026-11-30, 기수 전체") and "생성" in table[0][0]
    )
    assert table[1][:3] == ["강좌", "분야", "정원"]
    assert table[2] == [
        "'=SUM(A1) 요가",
        "미분류",
        "4",
        "2",
        "2",
        "1",
        "0",
        "0",
        "1",
        "0",
        "1",
        "2",
        "0.5",
    ]  # 수식으로 읽히지 않는다
    [job] = [
        j for j in world.db.execute(text("SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD='CSV_EXPORT'")).mappings()
    ]
    assert (job["MNGR_SN"], job["TRGT_TBL_NM"]) == (me.sn, "STATS_DEMAND")


def test_정산_CSV는_수단별_줄과_합계와_확인_중_금액_열을_둔다(world: World) -> None:
    c = open_course(world)
    payment(world, taken(world, c, "ES.CONFIRM"), "PS.PAID", STLM_MNS_CD="PM.CARD", STLM_AMT=30000)
    payment(
        world,
        taken(world, c, "ES.HOLD", SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START),
        "PS.PENDING",
        STLM_AMT=7000,
    )
    viewer(world)
    res = call(world, "GET", "/stats/settlement/export.csv")
    lines = [line.split(",") for line in res.content.decode("utf-8-sig").split("\r\n") if line]
    assert lines[1] == ["결제수단", "승인금액", "완료 환불액", "순수납", "확인 중 금액"]
    assert [row[:4] for row in lines[2:]] == [
        ["CARD", "30000", "0", "30000"],
        ["TRANSFER", "0", "0", "0"],
        ["합계", "30000", "0", "30000"],
    ]
    assert lines[-1][4] == "7000" and lines[2][4] == ""  # 확인 중 금액은 순수납과 따로 합계 줄에만 둔다


def test_동_담당자의_CSV는_자기_동_강좌만_담는다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    taken(world, open_course(world, CORS_NM="가동 강좌", DONG_SN=a["DONG_SN"]), "ES.CONFIRM")
    taken(world, open_course(world, CORS_NM="나동 강좌", DONG_SN=b["DONG_SN"]), "ES.CONFIRM")
    viewer(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    text = call(world, "GET", "/stats/demand/export.csv").content.decode("utf-8-sig")
    assert "가동 강좌" in text and "나동 강좌" not in text
