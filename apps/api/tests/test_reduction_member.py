# 주민 쪽 감면 사전심사의 신청·조회·철회·증빙과 관리자 증빙 열람 기록을 실제 앱과 DB로 확인하는 시험
import itertools
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import RESIDENT
from tests.test_applications_read import the_cycle as make_cycle
from tests.test_courses_public import cycle as new_cycle
from tests.test_files_admin import PDF, files_of, put
from tests.test_files_admin import root as root  # 저장소를 임시 폴더로 바꾸는 픽스처
from tests.test_member_inquiries import as_member, csrf, person
from tests.world import MEMBER, START, World, make_admin

pytestmark = pytest.mark.db

_n = itertools.count(1)
DAY = timedelta(days=1)


def resident(w: World, name: str = "홍길동", **values: Any) -> dict[str, Any]:
    return person(w, name, **{**RESIDENT, **values})


def send(w: World, method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None) -> Any:
    headers = {**csrf(w), **({"Idempotency-Key": key} if key else {})}
    return w.client.request(method, f"{MEMBER}{path}", json=body, headers=headers)


def apply(w: World, cycle: dict[str, Any], kind: str = "LIVELIHOOD", key: str | None = None) -> Any:
    body = {"cycleId": str(cycle["EDU_CYCL_SN"]), "reductionType": kind}
    return send(w, "POST", "/me/reduction-reviews", body, key or f"red-key-{next(_n):06d}")


def seed(
    w: World, who: dict[str, Any], cycle: dict[str, Any], status: str = "DS.RECEIVED", **values: Any
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "MBR_SN": who["MBR_SN"],
        "EDU_CYCL_SN": cycle["EDU_CYCL_SN"],
        "RDCT_TYPE_CD": "DR.LIVELIHD",
        "SRNG_STTS_CD": status,
        "APLY_DT": START - DAY,
    }
    if status in ("DS.APPROVED", "DS.REJECTED"):
        defaults.update(
            SRNG_MNGR_SN=make_admin(w, f"sd{next(_n)}", MNGR_NM="심사자")["MNGR_SN"], SRNG_DT=START
        )
    return w.factory.make("TB_RDCT_BFHD_SRNG", **{**defaults, **values})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def up(w: World, review_sn: Any, name: str = "증빙.pdf", data: bytes = PDF, idem: str | None = None) -> Any:
    headers = {**csrf(w), "Idempotency-Key": idem or f"rfile-{next(_n):08d}"}
    return w.client.post(
        f"{MEMBER}/me/reduction-reviews/{review_sn}/files",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )


# --- 인증·옵션 ----------------------------------------------------------------------------------


def test_로그인이_없으면_모두_401이다(world: World) -> None:
    for method, path in (
        ("GET", "/me/reduction-options"),
        ("GET", "/me/reduction-reviews"),
        ("POST", "/me/reduction-reviews"),
        ("GET", "/me/reduction-reviews/1"),
        ("POST", "/me/reduction-reviews/1/withdraw"),
        ("GET", "/me/reduction-reviews/1/files"),
        ("POST", "/me/reduction-reviews/1/files"),
    ):
        assert world.client.request(method, f"{MEMBER}{path}").status_code == 401, path


def test_거주가_확인된_회원은_진행_중인_기수를_고를_수_있다(world: World) -> None:
    current = make_cycle(world)
    new_cycle(world, "종료된 기수", EDU_CYCL=1, EDU_BGNG_YMD="20250101", EDU_END_YMD="20250331")
    new_cycle(world, "쓰지 않는 기수", EDU_CYCL=2, USE_YN="N")
    me = resident(world)
    as_member(world, me)
    body = send(world, "GET", "/me/reduction-options").json()
    assert body == {
        "cycles": [{"id": str(current["EDU_CYCL_SN"]), "name": current["EDU_CYCL_NM"]}],
        "canApply": True,
        "blockReason": None,
    }


def test_거주가_확인되지_않은_회원은_신청할_수_없고_이유를_받는다(world: World) -> None:
    make_cycle(world)
    for name, kw in (("외지", {"HAB_RGN_CD": "RA.PAJU_ETC"}), ("미확인", {"HAB_IDNTY_STTS_CD": "RV.NONE"})):
        as_member(world, resident(world, name, **kw))
        body = send(world, "GET", "/me/reduction-options").json()
        assert body["canApply"] is False and body["cycles"] == [] and "거주" in body["blockReason"], name


# --- 신청 ---------------------------------------------------------------------------------------


def test_신청하면_접수_상태로_만들고_금액은_받지_않는다(world: World) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    as_member(world, me)
    r = apply(world, cyc, "DISABLED")
    assert r.status_code == 201, r.text
    out = r.json()
    assert (
        out["status"],
        out["reductionType"],
        out["cycleName"],
        out["evidenceCount"],
        out["validUntil"],
        out["rejectReason"],
        out["canAddEvidence"],
        out["canWithdraw"],
    ) == (
        "RECEIVED",
        "DISABLED",
        cyc["EDU_CYCL_NM"],
        0,
        None,
        None,
        True,
        True,
    )
    assert out["appliedOn"] == "2026-11-09"
    [row] = rows(world, "SELECT * FROM TB_RDCT_BFHD_SRNG")
    assert (
        row["MBR_SN"],
        row["EDU_CYCL_SN"],
        row["RDCT_TYPE_CD"],
        row["SRNG_STTS_CD"],
        row["RCRD_VER"],
        row["SRNG_MNGR_SN"],
    ) == (
        me["MBR_SN"],
        cyc["EDU_CYCL_SN"],
        "DR.DISABLED",
        "DS.RECEIVED",
        1,
        None,
    )
    [job] = rows(
        world, "SELECT ACTR_TYPE_CD a, MBR_SN m, MNGR_SN g FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_APPLY'"
    )
    assert (job["a"], job["m"], job["g"]) == ("AK.MEMBER", me["MBR_SN"], None)


def test_신청_규칙_위반은_422이고_아무것도_만들지_않는다(world: World) -> None:
    cyc = make_cycle(world)
    ended = new_cycle(world, "종료", EDU_CYCL=1, EDU_BGNG_YMD="20250101", EDU_END_YMD="20250331")
    unused = new_cycle(world, "미사용", EDU_CYCL=2, USE_YN="N")
    out = resident(world, "외지", HAB_RGN_CD="RA.PAJU_ETC")
    as_member(world, out)
    r = apply(world, cyc)
    assert r.status_code == 422 and "거주" in r.json()["message"]
    me = resident(world)
    as_member(world, me)
    for bad in (ended, unused, {"EDU_CYCL_SN": 999999999}):
        r = apply(world, bad)
        assert r.status_code == 422 and "cycleId" in r.json()["fields"], bad
    assert send(
        world,
        "POST",
        "/me/reduction-reviews",
        {"cycleId": str(cyc["EDU_CYCL_SN"]), "reductionType": "NOPE"},
        "red-key-bad001",
    ).status_code in (400, 422)
    assert rows(world, "SELECT COUNT(*) n FROM TB_RDCT_BFHD_SRNG")[0]["n"] == 0


def test_같은_기수에_접수_중이거나_유효한_승인이_있으면_신청할_수_없다(world: World) -> None:
    cyc = make_cycle(world)
    other_cycle = new_cycle(world, "다른 기수", EDU_CYCL=3)
    me = resident(world)
    waiting = seed(world, me, cyc)
    as_member(world, me)
    r = apply(world, cyc)
    assert r.status_code == 422 and "cycleId" in r.json()["fields"]
    assert apply(world, other_cycle).status_code == 201  # 다른 기수는 따로다
    send(world, "POST", f"/me/reduction-reviews/{waiting['RDCT_BFHD_SRNG_SN']}/withdraw")
    world.db.execute(
        text(
            "UPDATE TB_RDCT_BFHD_SRNG SET SRNG_STTS_CD='DS.APPROVED', SRNG_MNGR_SN=:g, SRNG_DT=:d,"
            " VLD_END_DT=:v WHERE RDCT_BFHD_SRNG_SN=:s"
        ),
        {
            "g": make_admin(world, "ap-x")["MNGR_SN"],
            "d": START,
            "v": START + 30 * DAY,
            "s": waiting["RDCT_BFHD_SRNG_SN"],
        },
    )
    assert apply(world, cyc).status_code == 422  # 유효한 승인이 있다
    world.db.execute(
        text("UPDATE TB_RDCT_BFHD_SRNG SET VLD_END_DT=:v WHERE RDCT_BFHD_SRNG_SN=:s"),
        {"v": START - DAY, "s": waiting["RDCT_BFHD_SRNG_SN"]},
    )
    assert apply(world, cyc).status_code == 201  # 기간이 끝난 승인은 막지 않는다


def test_반려와_철회된_심사는_다시_신청을_막지_않는다(world: World) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    seed(world, me, cyc, "DS.REJECTED", RJCT_RSN="증빙 불충분")
    seed(world, me, cyc, "DS.REVOKED")
    as_member(world, me)
    assert apply(world, cyc).status_code == 201


def test_같은_키로_다시_보내면_같은_신청이고_내용이_다르면_409다(world: World) -> None:
    cyc = make_cycle(world)
    as_member(world, resident(world))
    first = apply(world, cyc, key="red-key-same01").json()
    again = apply(world, cyc, key="red-key-same01")
    assert again.status_code == 201 and again.json()["reviewId"] == first["reviewId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_RDCT_BFHD_SRNG")[0]["n"] == 1
    other = apply(world, cyc, "VETERAN", key="red-key-same01")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert send(
        world,
        "POST",
        "/me/reduction-reviews",
        {"cycleId": str(cyc["EDU_CYCL_SN"]), "reductionType": "VETERAN"},
    ).status_code in (400, 422)  # 키 필수


# --- 조회·철회 ----------------------------------------------------------------------------------


def test_목록은_내_신청만_최근_순이고_결과만_보인다(world: World) -> None:
    cyc = make_cycle(world)
    me, other = resident(world), resident(world, "박다라")
    old = seed(world, me, cyc, "DS.REJECTED", RJCT_RSN="증빙 불충분", APLY_DT=START - 5 * DAY)
    new = seed(world, me, cyc, APLY_DT=START - DAY, RDCT_TYPE_CD="DR.VETERAN")
    theirs = seed(world, other, cyc)
    approved = seed(world, other, cyc, "DS.APPROVED", VLD_END_DT=START + 20 * DAY, SRNG_CN="내부 메모")
    as_member(world, me)
    body = send(world, "GET", "/me/reduction-reviews").json()
    assert [i["reviewId"] for i in body["items"]] == [
        str(new["RDCT_BFHD_SRNG_SN"]),
        str(old["RDCT_BFHD_SRNG_SN"]),
    ]
    detail = send(world, "GET", f"/me/reduction-reviews/{old['RDCT_BFHD_SRNG_SN']}").json()
    assert (
        detail["status"],
        detail["rejectReason"],
        detail["validUntil"],
        detail["canWithdraw"],
        detail["canAddEvidence"],
    ) == ("REJECTED", "증빙 불충분", None, False, False)
    for hidden in (theirs, approved):
        assert send(world, "GET", f"/me/reduction-reviews/{hidden['RDCT_BFHD_SRNG_SN']}").status_code == 404
    as_member(world, other)
    mine = send(world, "GET", f"/me/reduction-reviews/{approved['RDCT_BFHD_SRNG_SN']}").json()
    assert (mine["status"], mine["validUntil"], mine["rejectReason"]) == ("APPROVED", "2026-11-29", None)
    assert (
        "내부 메모" not in str(mine)
        and "심사자" not in str(mine)
        and "reviewNote" not in mine
        and "reviewedBy" not in mine
    )
    assert send(world, "GET", "/me/reduction-reviews/999999999").status_code == 404


def test_철회는_접수_상태만_되고_증빙은_남으며_다시_신청할_수_있다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    up(world, sn)
    r = send(world, "POST", f"/me/reduction-reviews/{sn}/withdraw")
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["status"], out["canWithdraw"], out["canAddEvidence"], out["evidenceCount"]) == (
        "REVOKED",
        False,
        False,
        1,
    )
    [row] = rows(world, "SELECT SRNG_STTS_CD s, RCRD_VER v, SRNG_MNGR_SN g FROM TB_RDCT_BFHD_SRNG")
    assert (row["s"], row["v"], row["g"]) == ("DS.REVOKED", 2, None)
    [job] = rows(world, "SELECT MBR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_WITHDRAW'")
    assert job["m"] == me["MBR_SN"]
    again = send(world, "POST", f"/me/reduction-reviews/{sn}/withdraw")
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"
    assert apply(world, cyc).status_code == 201


def test_결정된_신청과_남의_신청은_철회할_수_없다(world: World) -> None:
    cyc = make_cycle(world)
    me, other = resident(world), resident(world, "박다라")
    approved = seed(world, me, cyc, "DS.APPROVED", VLD_END_DT=START + 9 * DAY)
    rejected = seed(world, me, cyc, "DS.REJECTED", RJCT_RSN="x")
    theirs = seed(world, other, cyc)
    as_member(world, me)
    for done in (approved, rejected):
        r = send(world, "POST", f"/me/reduction-reviews/{done['RDCT_BFHD_SRNG_SN']}/withdraw")
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert (
        send(world, "POST", f"/me/reduction-reviews/{theirs['RDCT_BFHD_SRNG_SN']}/withdraw").status_code
        == 404
    )
    assert (
        rows(
            world,
            "SELECT SRNG_STTS_CD s FROM TB_RDCT_BFHD_SRNG WHERE RDCT_BFHD_SRNG_SN=:s",
            s=theirs["RDCT_BFHD_SRNG_SN"],
        )[0]["s"]
        == "DS.RECEIVED"
    )


# --- 증빙 ---------------------------------------------------------------------------------------


def test_접수_상태의_내_심사에_증빙을_올리면_검사_대기로_저장한다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    r = up(world, sn, "수급증명.pdf")
    assert r.status_code == 201, r.text
    assert (r.json()["fileName"], r.json()["status"], r.json()["blockReason"]) == (
        "수급증명.pdf",
        "PENDING",
        None,
    )
    [row] = files_of(world)
    assert (str(row["RDCT_BFHD_SRNG_SN"]), row["FILE_USE_CD"], row["FILE_STTS_CD"], row["PST_SN"]) == (
        sn,
        "FP.PROOF",
        "FS.PENDING",
        None,
    )
    assert (root / row["STRG_KEY"]).read_bytes() == PDF
    [job] = rows(world, "SELECT ACTR_TYPE_CD a, MBR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='FILE_UPLOAD'")
    assert (job["a"], job["m"]) == ("AK.MEMBER", me["MBR_SN"])
    listed = send(world, "GET", f"/me/reduction-reviews/{sn}/files").json()
    assert (listed["canEdit"], listed["maxFiles"], len(listed["items"])) == (True, 5, 1)
    assert send(world, "GET", f"/me/reduction-reviews/{sn}").json()["evidenceCount"] == 1


def test_증빙은_다섯_개까지이고_형식이_틀리면_거절한다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    as_member(world, resident(world))
    sn = apply(world, cyc).json()["reviewId"]
    assert up(world, sn, "가짜.pdf", b"not a pdf").status_code == 422
    for n in range(5):
        assert up(world, sn, f"f{n}.pdf").status_code == 201
    assert up(world, sn, "f5.pdf").status_code == 422
    assert len(files_of(world)) == 5


def test_같은_키로_다시_올리면_같은_파일이다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    as_member(world, resident(world))
    sn = apply(world, cyc).json()["reviewId"]
    first = up(world, sn, idem="rfile-same-0001")
    again = up(world, sn, idem="rfile-same-0001")
    assert (
        again.status_code == 201
        and again.json()["fileId"] == first.json()["fileId"]
        and len(files_of(world)) == 1
    )


def test_남의_심사와_없는_심사에는_올릴_수_없다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me, other = resident(world), resident(world, "박다라")
    theirs = seed(world, other, cyc)
    as_member(world, me)
    for sn in (theirs["RDCT_BFHD_SRNG_SN"], 999999999):
        assert send(world, "GET", f"/me/reduction-reviews/{sn}/files").status_code == 404
        assert up(world, sn).status_code == 404
    assert files_of(world) == []


def test_결정되거나_철회된_심사의_증빙은_잠긴다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    file_id = up(world, sn).json()["fileId"]
    for status in ("DS.APPROVED", "DS.REJECTED", "DS.REVOKED"):
        world.db.execute(
            text("UPDATE TB_RDCT_BFHD_SRNG SET SRNG_STTS_CD=:s WHERE RDCT_BFHD_SRNG_SN=:r"),
            {"s": status, "r": sn},
        )
        world.db.commit()
        locked = up(world, sn)
        assert locked.status_code == 409 and locked.json()["code"] == "CONFLICT_STATE", status
        assert send(world, "DELETE", f"/me/files/{file_id}").status_code == 409, status
        assert send(world, "GET", f"/me/reduction-reviews/{sn}/files").json()["canEdit"] is False
    assert len(files_of(world)) == 1 and files_of(world)[0]["FILE_STTS_CD"] == "FS.PENDING"


def test_접수_상태에서는_내_증빙을_지울_수_있고_남의_증빙은_404다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me, other = resident(world), resident(world, "박다라")
    as_member(world, other)
    theirs = apply(world, cyc).json()["reviewId"]
    their_file = up(world, theirs).json()["fileId"]
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    mine = up(world, sn).json()["fileId"]
    assert send(world, "DELETE", f"/me/files/{their_file}").status_code == 404
    assert send(world, "DELETE", f"/me/files/{mine}").status_code == 204
    assert send(world, "GET", f"/me/reduction-reviews/{sn}").json()["evidenceCount"] == 0
    assert send(world, "DELETE", f"/me/files/{mine}").status_code == 404
    [job] = rows(world, "SELECT MBR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='FILE_DELETE'")
    assert job["m"] == me["MBR_SN"]


def test_검사를_통과한_내_증빙만_내려받고_남의_것은_404다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me, other = resident(world), resident(world, "박다라")
    as_member(world, other)
    their_file = int(up(world, apply(world, cyc).json()["reviewId"]).json()["fileId"])
    as_member(world, me)
    mine = int(up(world, apply(world, cyc).json()["reviewId"]).json()["fileId"])
    assert send(world, "GET", f"/me/files/{mine}").status_code == 404  # 검사 전
    put(world, mine)
    put(world, their_file)
    r = send(world, "GET", f"/me/files/{mine}")
    assert r.status_code == 200 and r.content == PDF and r.headers["cache-control"] == "private, no-store"
    assert send(world, "GET", f"/me/files/{their_file}").status_code == 404
    deny = [
        j
        for j in rows(world, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD='FILE_DOWNLOAD'")
        if j["JOB_RSLT_CD"] == "JR.DENY"
    ]
    assert any(j["TRGT_KEY_VL"] == str(their_file) for j in deny)


# --- 관리자와 이어지는 흐름 ---------------------------------------------------------------------


def test_관리자가_증빙을_내려받으면_열람_기록이_남고_심사_상세에_보인다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    me = resident(world)
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    file_id = int(up(world, sn, "수급증명.pdf").json()["fileId"])
    put(world, file_id)
    boss = staff(world, "viewer", "AU.APLY_R", "AU.APLY_W")
    use(world, boss)
    r = call(world, "GET", f"/files/{file_id}/download")
    assert r.status_code == 200 and r.content == PDF
    detail = call(world, "GET", f"/reductions/{sn}").json()
    assert [(e["fileName"], e["status"]) for e in detail["evidence"]] == [("수급증명.pdf", "SAFE")]
    [view] = detail["evidenceViews"]
    assert view["fileName"] == "수급증명.pdf" and view["by"] == "김관리"
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_EVIDENCE_VIEW'"
    )
    assert (job["m"], job["k"], job["c"]) == (boss.sn, sn, str(file_id))
    assert detail["evidenceCount"] == 1


def test_심사_권한이_없거나_범위_밖인_관리자는_증빙을_받을_수_없다(world: World, root: Path) -> None:
    cyc = make_cycle(world)
    a, b = dong(world, "가동"), dong(world, "나동")
    me = resident(world, DONG_SN=a["DONG_SN"])
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    file_id = int(up(world, sn).json()["fileId"])
    put(world, file_id)
    world.db.commit()
    for who in (
        staff(world, "readonly", "AU.APLY_R"),
        staff(world, "wrongdong", "AU.APLY_R", "AU.APLY_W", kind="SK.DONG", dong_sn=b["DONG_SN"]),
    ):
        use(world, who)
        assert call(world, "GET", f"/files/{file_id}/download").status_code == 404
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_EVIDENCE_VIEW'")[0]["n"] == 0
    use(world, staff(world, "rightdong", "AU.APLY_R", "AU.APLY_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert call(world, "GET", f"/files/{file_id}/download").status_code == 200


def test_주민_신청이_관리자_목록에_접수로_보이고_승인하면_결과가_주민에게_보인다(world: World) -> None:
    cyc = make_cycle(world)
    me = resident(world, "홍길동")
    as_member(world, me)
    sn = apply(world, cyc).json()["reviewId"]
    world.db.commit()
    use(world, staff(world, "boss", "AU.APLY_R", "AU.APLY_W"))
    items = call(world, "GET", "/reductions?status=RECEIVED").json()["items"]
    assert [i["reviewId"] for i in items] == [sn] and items[0]["memberName"] == "홍*동"
    r = call(
        world,
        "POST",
        f"/reductions/{sn}/decision",
        {"decision": "APPROVE", "validUntil": "2026-12-31", "reviewNote": "내부", "version": 1},
    )
    assert r.status_code == 200
    as_member(world, me)
    mine = send(world, "GET", f"/me/reduction-reviews/{sn}").json()
    assert (mine["status"], mine["validUntil"], mine["canWithdraw"], mine["canAddEvidence"]) == (
        "APPROVED",
        "2026-12-31",
        False,
        False,
    )
    assert "내부" not in str(mine)
