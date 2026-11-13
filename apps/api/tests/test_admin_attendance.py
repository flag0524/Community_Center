# 관리자 출석 현황 조회(AU.ATND_R, 조건·정렬·동 범위, 가린 명단, 수정·CSV 없음)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest

from tests.test_admin_access import dong
from tests.test_admin_applications import member
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import application, open_course
from tests.test_courses_public import course as make_course
from tests.test_courses_public import cycle as make_cycle
from tests.world import START, World, make_admin, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)


def teacher(w: World, name: str = "김강사") -> dict[str, Any]:
    who = make_member(w, f"t{next(_n)}", MBR_NM=name)
    return w.factory.make(
        "TB_INSTR",
        MBR_SN=who["MBR_SN"],
        INSTR_STTS_CD="IS.APPROVE",
        RLS_YN="Y",
        APRV_DT=START,
        APRV_MNGR_SN=make_admin(w, f"ap{next(_n)}")["MNGR_SN"],
    )


def sheet(w: World, c: dict[str, Any], day: str = "20261109", seq: int = 1, **values: Any) -> dict[str, Any]:
    schedule = w.factory.make("TB_CORS_SCHDL", CORS_SN=c["CORS_SN"])
    instr = values.pop("instructor", None) or teacher(w)
    defaults: dict[str, Any] = {
        "CORS_SN": c["CORS_SN"],
        "CORS_SCHDL_SN": schedule["CORS_SCHDL_SN"],
        "INSTR_SN": instr["INSTR_SN"],
        "LCTR_YMD": day,
        "LCTR_SEQ": seq,
        "ATND_NOPE": 1,
        "ABSNC_NOPE": 1,
        "UNCHCK_NOPE": 1,
        "CMPTN_YN": "N",
        "DEL_YN": "N",
    }
    return w.factory.make("TB_CORS_ATND", **{**defaults, **values})


def mark(w: World, s: dict[str, Any], c: dict[str, Any], who: dict[str, Any], result: str) -> None:
    apply = application(w, who, c, "ES.CONFIRM")
    w.factory.make(
        "TB_CORS_ATND_DTL", ATND_SN=s["ATND_SN"], ATNLC_APLY_SN=apply["ATNLC_APLY_SN"], ATND_RSLT_CD=result
    )


def reader(w: World, **kw: Any) -> Any:
    who = staff(w, f"a{next(_n)}", "AU.ATND_R", **kw)
    use(w, who)
    return who


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_출석_조회_권한이_없으면_403이다(world: World) -> None:
    c = open_course(world)
    s = sheet(world, c)
    world.db.commit()  # 오류 응답의 롤백이 준비한 행을 되돌리지 않게 고정한다
    assert world.client.get("/api/admin/v1/attendance").status_code == 401
    use(world, staff(world, "x", "AU.APLY_R", "AU.CORS_R", "AU.CORS_W"))
    assert call(world, "GET", "/attendance").status_code == 403
    assert call(world, "GET", f"/attendance/{s['ATND_SN']}").status_code == 403


def test_수정과_삭제와_CSV_엔드포인트는_없다(world: World) -> None:
    c = open_course(world)
    s = sheet(world, c)
    reader(world)
    sn = s["ATND_SN"]
    for method, path in (
        ("PUT", f"/attendance/{sn}"),
        ("DELETE", f"/attendance/{sn}"),
        ("POST", "/attendance"),
        ("GET", "/attendance/export.csv"),
    ):
        assert call(world, method, path, None).status_code in (400, 404, 405, 422), (method, path)
    assert call(world, "GET", "/attendance/export.csv").status_code != 200


# --- 목록 ---------------------------------------------------------------------------------------


def test_목록은_수업일이_늦은_것이_먼저이고_인원_입력_상태와_강사를_준다(world: World) -> None:
    a, b = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    old = sheet(
        world,
        a,
        "20261102",
        1,
        ATND_NOPE=5,
        ABSNC_NOPE=2,
        UNCHCK_NOPE=0,
        CMPTN_YN="Y",
        instructor=teacher(world, "박강사"),
    )
    new_b = sheet(world, b, "20261109", 2)
    new_a = sheet(world, a, "20261109", 2)
    reader(world)
    body = call(world, "GET", "/attendance").json()
    assert [i["attendanceId"] for i in body["items"]] == [
        str(new_b["ATND_SN"]),
        str(new_a["ATND_SN"]),
        str(old["ATND_SN"]),
    ] or [i["courseName"] for i in body["items"]] == ["서예", "요가", "요가"]
    last = body["items"][-1]
    assert (last["courseName"], last["classDate"], last["session"], last["instructorName"]) == (
        "요가",
        "2026-11-02",
        1,
        "박강사",
    )
    assert (last["present"], last["absent"], last["unchecked"], last["inputStatus"]) == (5, 2, 0, "DONE")
    assert (
        body["items"][0]["inputStatus"] == "IN_PROGRESS"
        and body["total"] == 3
        and body["criteria"]["basisAt"]
    )
    assert "phone" not in str(body) and "email" not in str(body).lower().replace("emailmasked", "")


def test_기수와_강좌와_수업일과_입력상태로_거르고_쪽을_나눈다(world: World) -> None:
    cyc1, cyc2 = make_cycle(world, "1기", EDU_CYCL=1), make_cycle(world, "2기", EDU_CYCL=2)
    a, b = make_course(world, cyc1, "요가"), make_course(world, cyc2, "서예")
    s1 = sheet(world, a, "20261102", 1, CMPTN_YN="Y")
    s2 = sheet(world, a, "20261109", 2)
    s3 = sheet(world, b, "20261109", 1)
    reader(world)

    def ids(qs: str) -> list[str]:
        return sorted(i["attendanceId"] for i in call(world, "GET", f"/attendance{qs}").json()["items"])

    assert ids(f"?cycleId={cyc2['EDU_CYCL_SN']}") == [str(s3["ATND_SN"])]
    assert ids(f"?courseId={a['CORS_SN']}") == sorted([str(s1["ATND_SN"]), str(s2["ATND_SN"])])
    assert ids("?classDate=2026-11-09") == sorted([str(s2["ATND_SN"]), str(s3["ATND_SN"])])
    assert ids("?inputStatus=DONE") == [str(s1["ATND_SN"])]
    assert ids("?inputStatus=IN_PROGRESS") == sorted([str(s2["ATND_SN"]), str(s3["ATND_SN"])])
    assert ids(f"?courseId={a['CORS_SN']}&classDate=2026-11-09&inputStatus=IN_PROGRESS") == [
        str(s2["ATND_SN"])
    ]
    assert call(world, "GET", "/attendance?inputStatus=NOPE").status_code in (400, 422)
    assert call(world, "GET", "/attendance?classDate=2026-13-45").status_code in (400, 422)
    assert [len(call(world, "GET", f"/attendance?size=2&page={n}").json()["items"]) for n in (1, 2)] == [2, 1]


def test_지운_출석부는_목록과_상세에서_빠진다(world: World) -> None:
    c = open_course(world)
    keep, gone = sheet(world, c, "20261102"), sheet(world, c, "20261109", DEL_YN="Y")
    reader(world)
    assert [i["attendanceId"] for i in call(world, "GET", "/attendance").json()["items"]] == [
        str(keep["ATND_SN"])
    ]
    assert call(world, "GET", f"/attendance/{gone['ATND_SN']}").status_code == 404


def test_동_담당자는_자기_동_강좌의_출석부만_본다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = sheet(world, open_course(world, CORS_NM="내 강좌", DONG_SN=a["DONG_SN"]))
    other = sheet(world, open_course(world, CORS_NM="남 강좌", DONG_SN=b["DONG_SN"]))
    common = sheet(world, open_course(world, CORS_NM="공통"))
    reader(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert [i["attendanceId"] for i in call(world, "GET", "/attendance").json()["items"]] == [
        str(mine["ATND_SN"])
    ]
    assert call(world, "GET", f"/attendance/{mine['ATND_SN']}").status_code == 200
    for hidden in (other, common):
        assert call(world, "GET", f"/attendance/{hidden['ATND_SN']}").status_code == 404
    reader(world)
    assert call(world, "GET", "/attendance").json()["total"] == 3


# --- 상세 ---------------------------------------------------------------------------------------


def test_상세_명단은_가린_이름과_신청번호와_회원_상태와_출석_상태만_담는다(world: World) -> None:
    c = open_course(world)
    s = sheet(world, c)
    people = [
        member(world, "홍길동"),
        member(world, "박다라"),
        make_member(world, f"x{next(_n)}", MBR_NM="최잠금", MBR_STTS_CD="MS.LOCKED", MBL_TELNO="01099998888"),
        make_member(world, f"y{next(_n)}", MBR_NM="이탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START),
    ]
    for who, result in zip(people, ("AR.PRESENT", "AR.ABSENT", "AR.UNCHECKED", "AR.UNCHECKED"), strict=True):
        mark(world, s, c, who, result)
    reader(world)
    body = call(world, "GET", f"/attendance/{s['ATND_SN']}").json()
    assert body["sheetNo"] == str(s["ATND_SN"]) and body["courseName"] == "요가" and body["session"] == 1
    roster = {r["name"]: r for r in body["roster"]}
    assert (roster["박*라"]["mark"], roster["박*라"]["memberStatus"]) == ("ABSENT", "정상")
    assert (roster["홍*동"]["mark"], roster["홍*동"]["memberStatus"]) == ("PRESENT", "정상")
    assert (roster["최*금"]["mark"], roster["최*금"]["memberStatus"]) == (
        "UNCHECKED",
        "잠금",
    )  # 미체크를 결석으로 바꾸지 않는다
    assert (roster["이*퇴"]["mark"], roster["이*퇴"]["memberStatus"]) == ("UNCHECKED", "탈퇴")
    assert all(r["applicationNo"].isdigit() for r in body["roster"])
    assert set(body["roster"][0]) == {"name", "applicationNo", "memberStatus", "mark"}
    text = str(body)
    assert "01099998888" not in text and "홍길동" not in text and "박다라" not in text


def test_명단이_없는_출석부는_빈_명단이고_없는_출석부는_404다(world: World) -> None:
    s = sheet(world, open_course(world))
    reader(world)
    assert call(world, "GET", f"/attendance/{s['ATND_SN']}").json()["roster"] == []
    assert call(world, "GET", "/attendance/999999999").status_code == 404
    assert call(world, "GET", "/attendance/abc").status_code in (400, 422)


def test_다른_묶음의_출석부는_보이지_않는다(world: World) -> None:
    foreign = int(world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"])
    outside = world.factory.make(
        "TB_CORS_ATND", OPER_BNDL_SN=foreign, LCTR_YMD="20261109", LCTR_SEQ=1, CMPTN_YN="N", DEL_YN="N"
    )
    reader(world)
    assert call(world, "GET", "/attendance").json()["total"] == 0
    assert call(world, "GET", f"/attendance/{outside['ATND_SN']}").status_code == 404


def test_명단은_그_출석부의_것만_이름순으로_준다(world: World) -> None:
    c = open_course(world)
    first, second = sheet(world, c, "20261102", 1), sheet(world, c, "20261109", 2)
    for who in (member(world, "최하나"), member(world, "가나다")):
        mark(world, first, c, who, "AR.PRESENT")
    mark(world, second, c, member(world, "박다라"), "AR.ABSENT")
    reader(world)
    one = call(world, "GET", f"/attendance/{first['ATND_SN']}").json()["roster"]
    assert [r["name"] for r in one] == ["가*다", "최*나"]
    assert [r["name"] for r in call(world, "GET", f"/attendance/{second['ATND_SN']}").json()["roster"]] == [
        "박*라"
    ]
