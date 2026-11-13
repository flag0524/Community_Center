# 관리자 감면 사전심사(조회·증빙 열람·승인·반려·재심사·판정 이력, 회원 거주 동 범위, 멱등)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.admin_access import Admin
from app.domain.admin import reduction_service
from app.domain.application.pricing import find_usable_approval
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import RESIDENT, application, open_course
from tests.test_applications_read import the_cycle as make_cycle
from tests.test_courses_public import cycle as new_cycle
from tests.world import START, World, make_admin, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)
DAY = timedelta(days=1)


def person(w: World, name: str = "홍길동", **values: Any) -> dict[str, Any]:
    return make_member(w, f"r{next(_n)}", MBR_NM=name, **{**RESIDENT, **values})


def review(
    w: World,
    who: dict[str, Any] | None = None,
    cycle: dict[str, Any] | None = None,
    status: str = "DS.RECEIVED",
    **values: Any,
) -> dict[str, Any]:
    who = who or person(w)
    cycle = cycle or make_cycle(w)
    defaults: dict[str, Any] = {
        "MBR_SN": who["MBR_SN"],
        "EDU_CYCL_SN": cycle["EDU_CYCL_SN"],
        "RDCT_TYPE_CD": "DR.LIVELIHD",
        "SRNG_STTS_CD": status,
        "APLY_DT": START - DAY,
    }
    return w.factory.make("TB_RDCT_BFHD_SRNG", **{**defaults, **values})


def evidence(
    w: World, rev: dict[str, Any], name: str = "증빙.pdf", status: str = "FS.SAFE"
) -> dict[str, Any]:
    return w.factory.make(
        "TB_FILE", RDCT_BFHD_SRNG_SN=rev["RDCT_BFHD_SRNG_SN"], FILE_NM=name, FILE_SZ=1234, FILE_STTS_CD=status
    )


def worker(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"rd{next(_n)}", *(codes or ("AU.APLY_R", "AU.APLY_W")), **kw)
    use(w, who)
    return who


def decide(w: World, sn: Any, decision: str = "APPROVE", version: int = 1, **values: Any) -> Any:
    body: dict[str, Any] = {"decision": decision, "version": version}
    if decision == "APPROVE":
        body["validUntil"] = "2026-12-31"
    else:
        body["rejectReason"] = "증빙 불충분"
    return call(w, "POST", f"/reductions/{sn}/decision", {**body, **values})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한·범위 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없으면_403이다(world: World) -> None:
    rev = review(world)
    world.db.commit()  # 오류 응답의 롤백이 준비한 행을 되돌리지 않게 고정한다
    assert world.client.get("/api/admin/v1/reductions").status_code == 401
    use(world, staff(world, "x", "AU.CORS_W", "AU.INSTR_W"))
    sn = rev["RDCT_BFHD_SRNG_SN"]
    for method, path in (
        ("GET", "/reductions"),
        ("GET", f"/reductions/{sn}"),
        ("POST", f"/reductions/{sn}/decision"),
        ("POST", f"/reductions/{sn}/re-review"),
        ("GET", "/reduction-history"),
    ):
        r = call(
            world,
            method,
            path,
            {"decision": "REJECT", "rejectReason": "x", "version": 1},
            **{"Idempotency-Key": "rr-key-0001"},
        )
        assert r.status_code == 403, path


def test_조회만_있으면_심사와_재심사는_403이고_증빙은_보이지_않는다(world: World) -> None:
    rev = review(world)
    evidence(world, rev)
    worker(world, "AU.APLY_R")
    sn = rev["RDCT_BFHD_SRNG_SN"]
    assert decide(world, sn).status_code == 403
    assert (
        call(
            world, "POST", f"/reductions/{sn}/re-review", None, **{"Idempotency-Key": "rr-key-0001"}
        ).status_code
        == 403
    )
    body = call(world, "GET", f"/reductions/{sn}").json()
    assert (body["canDecide"], body["canReReview"], body["canViewEvidence"]) == (False, False, False)
    assert body["evidence"] == [] and body["evidenceViews"] == [] and body["evidenceCount"] == 1


def test_동_담당자는_회원의_거주_동_심사만_본다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    mine = review(world, person(world, "가동주민", DONG_SN=a["DONG_SN"]))
    other = review(world, person(world, "나동주민", DONG_SN=b["DONG_SN"]))
    nowhere = review(world, person(world, "무동주민"))
    worker(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    body = call(world, "GET", "/reductions").json()
    assert [i["reviewId"] for i in body["items"]] == [str(mine["RDCT_BFHD_SRNG_SN"])] and body["total"] == 1
    assert call(world, "GET", f"/reductions/{mine['RDCT_BFHD_SRNG_SN']}").status_code == 200
    for hidden in (other, nowhere):
        sn = hidden["RDCT_BFHD_SRNG_SN"]
        assert call(world, "GET", f"/reductions/{sn}").status_code == 404
        assert decide(world, sn).status_code == 404
        assert (
            call(
                world, "POST", f"/reductions/{sn}/re-review", None, **{"Idempotency-Key": "rr-key-0001"}
            ).status_code
            == 404
        )
    assert decide(world, mine["RDCT_BFHD_SRNG_SN"]).status_code == 200
    worker(world)
    assert call(world, "GET", "/reductions").json()["total"] == 3


def test_없는_심사는_404이고_번호_형식이_틀리면_거절한다(world: World) -> None:
    worker(world)
    assert call(world, "GET", "/reductions").json()["total"] == 0
    assert call(world, "GET", "/reductions/999999999").status_code == 404
    assert call(world, "GET", "/reductions/abc").status_code in (400, 422)


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_목록은_접수가_먼저이고_접수는_오래된_순_나머지는_최근_순이며_이름을_가린다(world: World) -> None:
    cyc = make_cycle(world)
    old_wait = review(world, person(world, "박다라"), cyc, APLY_DT=START - 5 * DAY, RDCT_TYPE_CD="DR.VETERAN")
    new_wait = review(
        world, person(world, "최하나"), cyc, APLY_DT=START - 1 * DAY, RDCT_TYPE_CD="DR.DISABLED"
    )
    old_done = review(
        world,
        person(world, "가나다"),
        cyc,
        "DS.APPROVED",
        APLY_DT=START - 9 * DAY,
        SRNG_MNGR_SN=make_admin(world, "ap1")["MNGR_SN"],
        SRNG_DT=START,
        VLD_END_DT=START + 30 * DAY,
    )
    new_done = review(
        world,
        person(world, "이철수"),
        cyc,
        "DS.REJECTED",
        APLY_DT=START - 2 * DAY,
        SRNG_MNGR_SN=make_admin(world, "ap2")["MNGR_SN"],
        SRNG_DT=START,
        RJCT_RSN="사유",
    )
    evidence(world, old_wait)
    evidence(world, old_wait, "삭제됨.pdf", "FS.DELETE")
    worker(world)
    body = call(world, "GET", "/reductions").json()
    assert [i["reviewId"] for i in body["items"]] == [
        str(old_wait["RDCT_BFHD_SRNG_SN"]),
        str(new_wait["RDCT_BFHD_SRNG_SN"]),
        str(new_done["RDCT_BFHD_SRNG_SN"]),
        str(old_done["RDCT_BFHD_SRNG_SN"]),
    ]
    first = body["items"][0]
    assert (
        first["memberName"],
        first["reductionType"],
        first["status"],
        first["appliedOn"],
        first["evidenceCount"],
    ) == (
        "박*라",
        "VETERAN",
        "RECEIVED",
        "2026-11-04",
        1,  # 지운 증빙은 세지 않는다
    )
    assert body["items"][1]["reductionType"] == "DISABLED" and body["items"][1]["evidenceCount"] == 0
    assert "박다라" not in str(body)


def test_상태와_기수로_거르고_쪽을_나눈다(world: World) -> None:
    c1, c2 = make_cycle(world), new_cycle(world, "2026년 3분기", EDU_CYCL=3)
    a = review(world, cycle=c1)
    b = review(
        world,
        cycle=c2,
        status="DS.REJECTED",
        RJCT_RSN="x",
        SRNG_MNGR_SN=make_admin(world, "ap3")["MNGR_SN"],
        SRNG_DT=START,
    )
    c = review(world, cycle=c2, status="DS.REVOKED")
    worker(world)

    def ids(qs: str) -> set[str]:
        return {i["reviewId"] for i in call(world, "GET", f"/reductions{qs}").json()["items"]}

    assert ids("?status=RECEIVED") == {str(a["RDCT_BFHD_SRNG_SN"])}
    assert ids("?status=REJECTED") == {str(b["RDCT_BFHD_SRNG_SN"])}
    assert ids("?status=REVOKED") == {str(c["RDCT_BFHD_SRNG_SN"])}
    assert ids(f"?cycleId={c2['EDU_CYCL_SN']}") == {str(b["RDCT_BFHD_SRNG_SN"]), str(c["RDCT_BFHD_SRNG_SN"])}
    assert ids(f"?cycleId={c2['EDU_CYCL_SN']}&status=REVOKED") == {str(c["RDCT_BFHD_SRNG_SN"])}
    assert [len(call(world, "GET", f"/reductions?size=2&page={n}").json()["items"]) for n in (1, 2)] == [2, 1]
    assert call(world, "GET", "/reductions?status=NOPE").status_code in (400, 422)


def test_상세는_증빙과_열람_기록과_거주_확인과_결정_값을_준다(world: World) -> None:
    who = person(world, "홍길동")
    rev = review(world, who)
    f1, f2 = evidence(world, rev, "수급증명.pdf"), evidence(world, rev, "검사중.pdf", "FS.PENDING")
    evidence(world, rev, "지움.pdf", "FS.DELETE")
    boss = worker(world)
    reduction_service.record_evidence_view(
        world.db,
        _admin(world, boss),
        review_sn=int(rev["RDCT_BFHD_SRNG_SN"]),
        file_sn=int(f1["FILE_SN"]),
        request_id="req-1",
        now=START,
    )
    body = call(world, "GET", f"/reductions/{rev['RDCT_BFHD_SRNG_SN']}").json()
    assert (
        body["residenceConfirmed"] is True and body["canDecide"] is True and body["canViewEvidence"] is True
    )
    assert [(e["fileName"], e["status"]) for e in body["evidence"]] == [
        ("수급증명.pdf", "SAFE"),
        ("검사중.pdf", "PENDING"),
    ]
    assert [e["fileId"] for e in body["evidence"]] == [str(f1["FILE_SN"]), str(f2["FILE_SN"])]
    [view] = body["evidenceViews"]
    assert (
        view["by"] == "김관리" and view["fileName"] == "수급증명.pdf" and view["at"].startswith("2026-11-09")
    )
    assert (
        body["reviewedBy"],
        body["reviewedAt"],
        body["reviewNote"],
        body["rejectReason"],
        body["validUntil"],
        body["version"],
    ) == (None, None, None, None, None, 1)
    assert body["memberName"] == "홍*동"
    assert "홍길동" not in str(body)


def test_거주가_확인되지_않은_회원은_거주_확인이_거짓이다(world: World) -> None:
    out = review(world, person(world, "외지인", HAB_RGN_CD="RA.PAJU_ETC"))
    waiting = review(world, person(world, "대기자", HAB_IDNTY_STTS_CD="RV.NONE"))
    worker(world)
    for rev in (out, waiting):
        assert (
            call(world, "GET", f"/reductions/{rev['RDCT_BFHD_SRNG_SN']}").json()["residenceConfirmed"]
            is False
        )


# --- 승인·반려 ----------------------------------------------------------------------------------


def test_승인하면_유효_종료일_마지막_순간까지_쓸_수_있고_이력을_남긴다(world: World) -> None:
    who = person(world)
    rev = review(world, who)
    boss = worker(world)
    r = decide(world, rev["RDCT_BFHD_SRNG_SN"], review_note="  서류 확인  ", validUntil="2026-11-30")
    assert r.status_code == 200, r.text
    out = r.json()
    assert (
        out["status"],
        out["validUntil"],
        out["reviewNote"],
        out["rejectReason"],
        out["reviewedBy"],
        out["version"],
        out["canDecide"],
        out["canReReview"],
    ) == (
        "APPROVED",
        "2026-11-30",
        "서류 확인",
        None,
        "김관리",
        2,
        False,
        True,
    )
    [row] = rows(world, "SELECT SRNG_MNGR_SN m, SRNG_DT d, VLD_END_DT v FROM TB_RDCT_BFHD_SRNG")
    assert row["m"] == boss.sn and row["d"] is not None
    assert row["v"].isoformat() == "2026-11-30T14:59:59"  # 한국 시각 23:59:59
    [job] = rows(
        world,
        "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_REVIEW_APPROVE'",
    )
    assert (job["m"], job["k"]) == (boss.sn, str(rev["RDCT_BFHD_SRNG_SN"])) and "서류" not in job["c"]
    # 신청 금액 산정이 이 승인을 그날 마지막 순간까지 쓴다
    member = (
        world.db.execute(text("SELECT * FROM TB_MBR WHERE MBR_SN=:s"), {"s": who["MBR_SN"]}).mappings().one()
    )
    cyc = int(rev["EDU_CYCL_SN"])
    assert find_usable_approval(world.db, _row(member), cyc, START) is not None
    assert find_usable_approval(world.db, _row(member), cyc, datetime(2026, 11, 30, 14, 59, 0)) is not None
    assert find_usable_approval(world.db, _row(member), cyc, datetime(2026, 11, 30, 15, 0, 1)) is None


def test_유효_종료일이_오늘이어도_승인할_수_있고_어제면_거절한다(world: World) -> None:
    rev = review(world)
    worker(world)
    assert "validUntil" in decide(world, rev["RDCT_BFHD_SRNG_SN"], validUntil="2026-11-08").json()["fields"]
    assert (
        decide(world, rev["RDCT_BFHD_SRNG_SN"], validUntil="2026-11-09").status_code == 200
    )  # 시험 시계는 2026-11-09 18:00 KST


def test_승인_규칙_위반은_422이고_아무것도_바꾸지_않는다(world: World) -> None:
    rev = review(world)
    out_of_town = review(world, person(world, "외지인", HAB_RGN_CD="RA.PAJU_ETC"))
    unverified = review(world, person(world, "미확인", HAB_IDNTY_STTS_CD="RV.NONE"))
    worker(world)
    sn = rev["RDCT_BFHD_SRNG_SN"]
    for values, field in (
        ({"validUntil": None}, "validUntil"),
        ({"rejectReason": "사유"}, "rejectReason"),
    ):
        r = decide(world, sn, **values)
        assert r.status_code == 422 and field in r.json()["fields"], values
    for other in (out_of_town, unverified):
        r = decide(world, other["RDCT_BFHD_SRNG_SN"])
        assert r.status_code == 422 and "decision" in r.json()["fields"] and "거주" in r.json()["message"]
    assert {r["s"] for r in rows(world, "SELECT SRNG_STTS_CD s FROM TB_RDCT_BFHD_SRNG")} == {"DS.RECEIVED"}
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD LIKE 'RDCT_REVIEW%'")[0]["n"] == 0
    assert decide(world, sn, "REJECT", rejectReason=None).status_code == 422  # 반려 사유 필수
    assert (
        decide(world, out_of_town["RDCT_BFHD_SRNG_SN"], "REJECT").status_code == 200
    )  # 거주 미확인도 반려는 된다


def test_반려는_사유가_필수이고_유효_종료일은_받지_않는다(world: World) -> None:
    rev = review(world)
    worker(world)
    sn = rev["RDCT_BFHD_SRNG_SN"]
    for reason in (None, "", "   "):
        r = decide(world, sn, "REJECT", rejectReason=reason)
        assert r.status_code == 422 and "rejectReason" in r.json()["fields"], reason
    r = decide(world, sn, "REJECT", validUntil="2026-12-31")
    assert r.status_code == 422 and "validUntil" in r.json()["fields"]
    done = decide(world, sn, "REJECT", rejectReason="  증빙 불충분  ", reviewNote="메모")
    assert done.status_code == 200
    out = done.json()
    assert (
        out["status"],
        out["rejectReason"],
        out["validUntil"],
        out["reviewNote"],
        out["version"],
        out["canReReview"],
    ) == ("REJECTED", "증빙 불충분", None, "메모", 2, True)
    assert rows(world, "SELECT VLD_END_DT v FROM TB_RDCT_BFHD_SRNG")[0]["v"] is None
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_REVIEW_REJECT'")[0]["n"] == 1


def test_결정한_심사는_다시_결정할_수_없고_읽은_버전이_다르면_409다(world: World) -> None:
    rev = review(world)
    worker(world)
    sn = rev["RDCT_BFHD_SRNG_SN"]
    stale = decide(world, sn, version=5)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert decide(world, sn).status_code == 200
    for decision in ("APPROVE", "REJECT"):
        again = decide(world, sn, decision, version=2)
        assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE", decision
    assert decide(world, "999999999").status_code == 404
    assert call(
        world, "POST", f"/reductions/{sn}/decision", {"decision": "NOPE", "version": 1}
    ).status_code in (400, 422)
    assert [r["s"] for r in rows(world, "SELECT SRNG_STTS_CD s FROM TB_RDCT_BFHD_SRNG")] == ["DS.APPROVED"]


def test_철회된_심사는_결정할_수_없다(world: World) -> None:
    rev = review(world, status="DS.REVOKED")
    worker(world)
    r = decide(world, rev["RDCT_BFHD_SRNG_SN"])
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"


# --- 재심사 -------------------------------------------------------------------------------------


def reopen(w: World, sn: Any, key: str = "rr-key-0001") -> Any:
    return call(w, "POST", f"/reductions/{sn}/re-review", None, **{"Idempotency-Key": key})


def test_결정된_심사를_재심사하면_새_접수건이_생기고_이전_심사는_그대로다(world: World) -> None:
    who = person(world)
    rev = review(world, who, RDCT_TYPE_CD="DR.VETERAN")
    boss = worker(world)
    decide(world, rev["RDCT_BFHD_SRNG_SN"], "REJECT")
    r = reopen(world, rev["RDCT_BFHD_SRNG_SN"])
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["reviewId"] != str(rev["RDCT_BFHD_SRNG_SN"])
    assert (
        out["status"],
        out["reductionType"],
        out["version"],
        out["evidenceCount"],
        out["canDecide"],
        out["reviewedBy"],
        out["validUntil"],
    ) == (
        "RECEIVED",
        "VETERAN",
        1,
        0,
        True,
        None,
        None,
    )
    old, new = rows(world, "SELECT * FROM TB_RDCT_BFHD_SRNG ORDER BY RDCT_BFHD_SRNG_SN")
    assert (old["SRNG_STTS_CD"], old["RJCT_RSN"], old["RCRD_VER"]) == ("DS.REJECTED", "증빙 불충분", 2)
    assert (
        new["MBR_SN"],
        new["EDU_CYCL_SN"],
        new["RDCT_TYPE_CD"],
        new["SRNG_STTS_CD"],
        new["SRNG_MNGR_SN"],
        new["RJCT_RSN"],
    ) == (
        old["MBR_SN"],
        old["EDU_CYCL_SN"],
        "DR.VETERAN",
        "DS.RECEIVED",
        None,
        None,
    )
    [job] = rows(world, "SELECT MNGR_SN m, TRGT_KEY_VL k FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_RE_REVIEW'")
    assert (job["m"], job["k"]) == (boss.sn, out["reviewId"])


def test_접수_중인_심사나_접수_중인_형제가_있으면_재심사할_수_없다(world: World) -> None:
    who = person(world)
    cyc = make_cycle(world)
    waiting = review(world, who, cyc)
    done = review(
        world,
        who,
        cyc,
        "DS.APPROVED",
        SRNG_MNGR_SN=make_admin(world, "ap4")["MNGR_SN"],
        SRNG_DT=START,
        VLD_END_DT=START + 9 * DAY,
    )
    worker(world)
    first = reopen(world, waiting["RDCT_BFHD_SRNG_SN"])
    assert (
        first.status_code == 409 and first.json()["code"] == "CONFLICT_STATE"
    )  # 접수 상태는 재심사가 아니라 결정 대상이다
    second = reopen(world, done["RDCT_BFHD_SRNG_SN"])
    assert (
        second.status_code == 409 and "접수 중" in second.json()["message"]
    )  # 같은 회원·기수에 접수 건이 있다
    assert rows(world, "SELECT COUNT(*) n FROM TB_RDCT_BFHD_SRNG")[0]["n"] == 2
    detail = call(world, "GET", f"/reductions/{done['RDCT_BFHD_SRNG_SN']}").json()
    assert detail["canReReview"] is False


def test_재심사를_같은_키로_다시_보내면_같은_건이고_다른_심사에_쓰면_409다(world: World) -> None:
    a = review(
        world,
        status="DS.REJECTED",
        SRNG_MNGR_SN=make_admin(world, "ap5")["MNGR_SN"],
        SRNG_DT=START,
        RJCT_RSN="x",
    )
    b = review(
        world,
        status="DS.REJECTED",
        SRNG_MNGR_SN=make_admin(world, "ap6")["MNGR_SN"],
        SRNG_DT=START,
        RJCT_RSN="x",
    )
    worker(world)
    first = reopen(world, a["RDCT_BFHD_SRNG_SN"], "rr-key-aaaa").json()
    again = reopen(world, a["RDCT_BFHD_SRNG_SN"], "rr-key-aaaa")
    assert again.status_code == 201 and again.json()["reviewId"] == first["reviewId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_RDCT_BFHD_SRNG")[0]["n"] == 3
    clash = reopen(world, b["RDCT_BFHD_SRNG_SN"], "rr-key-aaaa")
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", f"/reductions/{a['RDCT_BFHD_SRNG_SN']}/re-review", None).status_code in (
        400,
        422,
    )  # 키 필수


def test_재심사해도_이전_승인은_그대로_쓸_수_있다(world: World) -> None:
    who = person(world)
    rev = review(world, who)
    worker(world)
    decide(world, rev["RDCT_BFHD_SRNG_SN"])
    assert reopen(world, rev["RDCT_BFHD_SRNG_SN"]).status_code == 201
    member = (
        world.db.execute(text("SELECT * FROM TB_MBR WHERE MBR_SN=:s"), {"s": who["MBR_SN"]}).mappings().one()
    )
    assert find_usable_approval(world.db, _row(member), int(rev["EDU_CYCL_SN"]), START) is not None


# --- 판정 이력 ----------------------------------------------------------------------------------


def history(w: World, apply: dict[str, Any], result: str, day: int, **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "ATNLC_APLY_SN": apply["ATNLC_APLY_SN"],
        "DCSN_RSLT_CD": result,
        "RDCT_AMT": 15000 if result == "DR.APPROVE" else None,
        "DCSN_RSN": None if result == "DR.APPROVE" else "해제",
        "DCSN_MNGR_SN": make_admin(w, f"h{next(_n)}", MNGR_NM="처리자")["MNGR_SN"],
        "DCSN_DT": START - day * DAY,
    }
    return w.factory.make("TB_RDCT_HSTRY", **{**defaults, **values})


def test_판정_이력은_최근_순이고_결과와_기간으로_거르며_이름을_가린다(world: World) -> None:
    who = person(world, "홍길동")
    c = open_course(world)
    apply = application(world, who, c)
    old = history(world, apply, "DR.APPROVE", 5)
    new = history(world, apply, "DR.REJECT", 1)
    worker(world)
    body = call(world, "GET", "/reduction-history").json()
    assert [i["historyId"] for i in body["items"]] == [str(new["RDCT_HSTRY_SN"]), str(old["RDCT_HSTRY_SN"])]
    head, tail = body["items"]
    assert (
        head["result"],
        head["amount"],
        head["reason"],
        head["decidedBy"],
        head["memberName"],
        head["applicationNo"],
        head["evidenceCount"],
    ) == (
        "REJECT",
        None,
        "해제",
        "처리자",
        "홍*동",
        str(apply["ATNLC_APLY_SN"]),
        0,
    )
    assert (tail["result"], tail["amount"], tail["reason"]) == ("APPROVE", 15000, None) and head["cycleName"]
    assert "홍길동" not in str(body)

    def ids(qs: str) -> list[str]:
        return [i["historyId"] for i in call(world, "GET", f"/reduction-history{qs}").json()["items"]]

    assert ids("?result=APPROVE") == [str(old["RDCT_HSTRY_SN"])]
    assert ids("?result=REJECT") == [str(new["RDCT_HSTRY_SN"])]
    assert ids("?from=2026-11-08") == [str(new["RDCT_HSTRY_SN"])]
    assert ids("?to=2026-11-04") == [str(old["RDCT_HSTRY_SN"])]
    assert ids("?from=2026-11-04&to=2026-11-04") == [str(old["RDCT_HSTRY_SN"])]
    assert ids("?from=2026-12-01") == []
    assert len(call(world, "GET", "/reduction-history?size=1&page=2").json()["items"]) == 1
    assert call(world, "GET", "/reduction-history?result=NOPE").status_code in (400, 422)


def test_판정_이력의_증빙_수와_동_범위를_지킨다(world: World) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    who = person(world)
    mine = application(world, who, open_course(world, CORS_NM="가동 강좌", DONG_SN=a["DONG_SN"]))
    other = application(world, who, open_course(world, CORS_NM="나동 강좌", DONG_SN=b["DONG_SN"]))
    keep = history(world, mine, "DR.APPROVE", 2)
    history(world, other, "DR.APPROVE", 3)
    rev = review(world, who)
    f = evidence(world, rev)
    world.factory.make("TB_RDCT_HSTRY_FILE", RDCT_HSTRY_SN=keep["RDCT_HSTRY_SN"], FILE_SN=f["FILE_SN"])
    worker(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    body = call(world, "GET", "/reduction-history").json()
    assert [(i["historyId"], i["evidenceCount"]) for i in body["items"]] == [(str(keep["RDCT_HSTRY_SN"]), 1)]
    worker(world)
    assert call(world, "GET", "/reduction-history").json()["total"] == 2


def _row(mapping: Any) -> Any:
    return SimpleNamespace(**dict(mapping))


def _admin(w: World, who: Any) -> Admin:
    """감사 기록 함수는 관리자 번호와 묶음만 읽는다. 세션 기록은 필요 없다."""
    return SimpleNamespace(admin_sn=who.sn, bundle_sn=w.bundle)  # type: ignore[return-value]
