# 강사 모집공고 조회와 회원의 강사 지원(작성·수정·증빙)과 관리자 심사 흐름을 실제 앱과 DB로 확인하는 시험
import itertools
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.crypto import decrypt
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board, post
from tests.test_files_admin import PDF, files_of, put, upload
from tests.test_files_admin import root as root  # 저장소를 임시 폴더로 바꾸는 픽스처
from tests.test_member_inquiries import as_member, csrf, person
from tests.world import MEMBER, START, World

pytestmark = pytest.mark.db

_n = itertools.count(1)
DAY = timedelta(days=1)
PHONE = "01055556666"


def new_board(w: World, **values: Any) -> dict[str, Any]:
    return board(w, "notice", **{"BBS_ID": f"recruit{next(_n)}", **values})


def recruit(
    w: World, title: str = "요가 강사 모집", begin: int = -3, end: int = 10, **values: Any
) -> dict[str, Any]:
    """공고글과 모집 정보. 기간은 오늘(시험 시계 2026-11-09)에서 며칠 앞뒤인지로 준다."""
    bbs = values.pop("bbs", None) or new_board(w)
    pst = post(
        w,
        bbs,
        title,
        PST_CN="<p>자격: <b>경력 3년</b></p><ul><li>이력서 제출</li></ul>",
        **{"REG_DT": START - 5 * DAY, **values.pop("post", {})},
    )
    defaults: dict[str, Any] = {
        "PST_SN": pst["PST_SN"],
        "RCRT_BGNG_DT": START + begin * DAY,
        "RCRT_END_DT": START + end * DAY,
        "RCRT_NOPE": 2,
    }
    return w.factory.make("TB_INSTR_RCRT", **{**defaults, **values})


def category(w: World, name: str = "생활체육", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "CORS_CLSF_NM": name,
        "CLSF_NM_KEY": name.lower(),
        "SORT_SEQ": next(_n),
        "USE_YN": "Y",
        "DEL_YN": "N",
    }
    return w.factory.make("TB_CORS_CLSF", **{**defaults, **values})


def applicant(w: World, name: str = "홍길동", **values: Any) -> dict[str, Any]:
    return person(w, name, **{"MBL_TELNO": PHONE, **values})


def body(rcrt: dict[str, Any], **values: Any) -> dict[str, Any]:
    return {
        "recruitmentId": str(rcrt["INSTR_RCRT_SN"]),
        "desiredCourse": "요가 기초반",
        "categoryName": "생활체육",
        "career": "요가 지도 10년",
        **values,
    }


def send(
    w: World, method: str, path: str, payload: dict[str, Any] | None = None, key: str | None = None
) -> Any:
    headers = {**csrf(w), **({"Idempotency-Key": key} if key else {})}
    return w.client.request(method, f"{MEMBER}{path}", json=payload, headers=headers)


def apply(w: World, payload: dict[str, Any], key: str | None = None) -> Any:
    return send(w, "POST", "/me/instructor-applications", payload, key or f"inst-key-{next(_n):06d}")


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def get(w: World, path: str) -> Any:
    return w.client.get(f"{MEMBER}{path}")


def up(w: World, sn: Any, name: str = "자격증.pdf", data: bytes = PDF, idem: str | None = None) -> Any:
    headers = {**csrf(w), "Idempotency-Key": idem or f"ifile-{next(_n):08d}"}
    return w.client.post(
        f"{MEMBER}/me/instructor-applications/{sn}/files",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )


# --- 인증 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_내_지원_관련은_모두_401이다(world: World) -> None:
    for method, path in (
        ("GET", "/me/instructor-applications"),
        ("POST", "/me/instructor-applications"),
        ("GET", "/me/instructor-applications/1"),
        ("PUT", "/me/instructor-applications/1"),
        ("GET", "/me/instructor-applications/1/files"),
        ("POST", "/me/instructor-applications/1/files"),
    ):
        assert world.client.request(method, f"{MEMBER}{path}").status_code == 401, path


# --- 모집공고 -----------------------------------------------------------------------------------


def test_공고_목록은_누구나_보고_게시일_최근_순이며_상태를_서버가_정한다(world: World) -> None:
    bbs = new_board(world)
    older = recruit(world, "지난 모집", -20, -10, bbs=bbs, post={"REG_DT": START - 30 * DAY})
    now_open = recruit(world, "모집중", -3, 10, bbs=bbs, post={"REG_DT": START - 3 * DAY})
    soon = recruit(world, "예정", 5, 15, bbs=bbs, post={"REG_DT": START - 1 * DAY}, RCRT_NOPE=None)
    res = world.client.get("/api/v1/instructor-recruitments")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["recruitmentId"] for i in items] == [
        str(soon["INSTR_RCRT_SN"]),
        str(now_open["INSTR_RCRT_SN"]),
        str(older["INSTR_RCRT_SN"]),
    ]
    assert [(i["title"], i["status"], i["headcount"]) for i in items] == [
        ("예정", "UPCOMING", None),
        ("모집중", "OPEN", 2),
        ("지난 모집", "CLOSED", 2),
    ]
    assert (items[1]["periodStart"], items[1]["periodEnd"]) == ("2026-11-06", "2026-11-19")
    assert res.json()["total"] == 3


def test_숨겨야_할_공고는_목록과_상세에_나오지_않는다(world: World) -> None:
    bbs = new_board(world)
    shown = recruit(world, "보이는 공고", bbs=bbs)
    hidden = {
        "삭제": recruit(world, "삭제", bbs=bbs, post={"DEL_YN": "Y"}),
        "비공개": recruit(world, "비공개", bbs=bbs, post={"PRVT_YN": "Y"}),
        "게시 전": recruit(world, "게시 전", bbs=bbs, post={"PSTG_BGNG_DT": START + DAY}),
        "게시 종료": recruit(world, "게시 종료", bbs=bbs, post={"PSTG_END_DT": START - DAY}),
        "기간 없음": recruit(world, "기간 없음", bbs=bbs, RCRT_BGNG_DT=None, RCRT_END_DT=None),
        "게시판 끔": recruit(world, "게시판 끔", bbs=new_board(world, USE_YN="N")),
    }
    items = world.client.get("/api/v1/instructor-recruitments").json()["items"]
    assert [i["recruitmentId"] for i in items] == [str(shown["INSTR_RCRT_SN"])]
    for name, row in hidden.items():
        assert (
            world.client.get(f"/api/v1/instructor-recruitments/{row['INSTR_RCRT_SN']}").status_code == 404
        ), name
    assert world.client.get("/api/v1/instructor-recruitments/999999999").status_code == 404
    assert [
        len(world.client.get(f"/api/v1/instructor-recruitments?size=1&page={n}").json()["items"])
        for n in (1, 2)
    ] == [1, 0]


def test_공고_상세는_본문_글자만_안내로_주고_로그인하지_않아도_지원할_수_있다고_알린다(world: World) -> None:
    rcrt = recruit(world)
    out = world.client.get(f"/api/v1/instructor-recruitments/{rcrt['INSTR_RCRT_SN']}").json()
    assert (
        out["title"],
        out["status"],
        out["canApply"],
        out["field"],
        out["announcedOn"],
        out["headcount"],
    ) == ("요가 강사 모집", "OPEN", True, None, "2026-11-04", 2)
    assert "<" not in out["guide"] and "경력 3년" in out["guide"] and "이력서 제출" in out["guide"]
    closed = recruit(world, "마감", -20, -10)
    upcoming = recruit(world, "예정", 5, 15)
    for row, status in ((closed, "CLOSED"), (upcoming, "UPCOMING")):
        res = world.client.get(f"/api/v1/instructor-recruitments/{row['INSTR_RCRT_SN']}").json()
        assert (res["status"], res["canApply"]) == (status, False)


def test_이미_지원한_회원에게는_지원할_수_없다고_알린다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    other = recruit(world, "다른 공고")
    me = applicant(world)
    as_member(world, me)
    assert apply(world, body(rcrt)).status_code == 201
    path = "/api/v1/instructor-recruitments/{}"
    assert world.client.get(path.format(rcrt["INSTR_RCRT_SN"])).json()["canApply"] is False
    assert world.client.get(path.format(other["INSTR_RCRT_SN"])).json()["canApply"] is True
    world.client.cookies.clear()
    assert (
        world.client.get(path.format(rcrt["INSTR_RCRT_SN"])).json()["canApply"] is True
    )  # 로그인하지 않으면 모른다


# --- 지원 ---------------------------------------------------------------------------------------


def test_지원하면_서류_검토중으로_접수하고_이름과_휴대전화는_회원정보를_쓴다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    me = applicant(world, "김지원")
    as_member(world, me)
    r = apply(world, body(rcrt, desiredCourse="  요가 기초반  ", career="  요가 지도 10년  "))
    assert r.status_code == 201, r.text
    out = r.json()
    assert (
        out["recruitmentId"],
        out["recruitmentTitle"],
        out["desiredCourse"],
        out["categoryName"],
        out["career"],
        out["status"],
        out["canEdit"],
    ) == (
        str(rcrt["INSTR_RCRT_SN"]),
        "요가 강사 모집",
        "요가 기초반",
        "생활체육",
        "요가 지도 10년",
        "REVIEWING",
        True,
    )
    assert out["appliedAt"].startswith("2026-11-09")
    [row] = rows(world, "SELECT * FROM TB_INSTR_APLY")
    assert (
        row["RCPT_CHNL_CD"],
        row["MBR_SN"],
        row["APLCT_NM"],
        row["HOPE_FLD_NM"],
        row["RLS_HOPE_YN"],
        row["SRNG_STTS_CD"],
        row["RCRD_VER"],
        row["RCPT_MNGR_SN"],
    ) == (
        "IC.ONLINE",
        me["MBR_SN"],
        "김지원",
        "생활체육",
        "N",
        "IA.WAIT",
        1,
        None,
    )
    assert (
        decrypt(world.settings.secret_key, row["TELNO_ENCPT_VL"]) == PHONE
        and PHONE not in row["TELNO_ENCPT_VL"]
    )
    assert PHONE not in str(out)
    [job] = rows(
        world, "SELECT ACTR_TYPE_CD a, MBR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_APLY_CREATE'"
    )
    assert (job["a"], job["m"]) == ("AK.MEMBER", me["MBR_SN"]) and PHONE not in job["c"]


def test_지원_규칙_위반은_422이고_아무것도_만들지_않는다(world: World) -> None:
    category(world)
    category(world, "쓰지 않음", USE_YN="N")
    category(world, "지움", DEL_YN="Y")
    open_ = recruit(world)
    closed = recruit(world, "마감", -20, -10)
    upcoming = recruit(world, "예정", 5, 15)
    hidden = recruit(world, "삭제", post={"DEL_YN": "Y"})
    as_member(world, applicant(world))
    for rcrt in (closed, upcoming, hidden, {"INSTR_RCRT_SN": 999999999}):
        r = apply(world, body(rcrt))
        assert r.status_code == 422 and "recruitmentId" in r.json()["fields"], rcrt["INSTR_RCRT_SN"]
    for name in ("없는 분야", "쓰지 않음", "지움"):
        r = apply(world, body(open_, categoryName=name))
        assert r.status_code == 422 and "categoryName" in r.json()["fields"], name
    for field, value in (("desiredCourse", "   "), ("career", "   ")):
        r = apply(world, body(open_, **{field: value}))
        assert r.status_code == 422 and field in r.json()["fields"], field
    assert apply(world, {**body(open_), "categoryName": ""}).status_code in (400, 422)
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 0


def test_같은_공고에는_결과와_상관없이_한_번만_지원한다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    as_member(world, applicant(world))
    first = apply(world, body(rcrt))
    assert first.status_code == 201
    again = apply(world, body(rcrt))
    assert again.status_code == 422 and "이미" in again.json()["fields"]["recruitmentId"]
    world.db.execute(text("UPDATE TB_INSTR_APLY SET SRNG_STTS_CD='IA.REJECT', RJCT_RSN='x'"))
    world.db.commit()
    assert apply(world, body(rcrt)).status_code == 422  # 미선정이어도 다시 지원할 수 없다
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 1


def test_휴대전화가_없는_회원은_지원할_수_없다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    as_member(world, applicant(world, MBL_TELNO=None))
    r = apply(world, body(rcrt))
    assert r.status_code == 422 and "휴대전화" in r.json()["message"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 0


def test_같은_키로_다시_보내면_같은_지원이고_내용이_다르면_409다(world: World) -> None:
    category(world)
    category(world, "문화예술")
    rcrt = recruit(world)
    as_member(world, applicant(world))
    first = apply(world, body(rcrt), "inst-key-same01").json()
    again = apply(world, body(rcrt, categoryName="생활체육"), "inst-key-same01")
    assert again.status_code == 201 and again.json()["applicationId"] == first["applicationId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 1
    for diff in ({"categoryName": "문화예술"}, {"career": "다른 경력"}, {"desiredCourse": "다른 강좌"}):
        r = apply(world, body(rcrt, **diff), "inst-key-same01")
        assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT", diff
    assert send(world, "POST", "/me/instructor-applications", body(rcrt)).status_code in (400, 422)  # 키 필수
    no_csrf = world.client.post(
        f"{MEMBER}/me/instructor-applications",
        json=body(rcrt),
        headers={"Idempotency-Key": "inst-key-nocsrf"},
    )
    assert no_csrf.status_code == 403


# --- 조회·수정 ----------------------------------------------------------------------------------


def test_내_지원내역은_내_것만_최근_순이고_남의_상세는_404다(world: World) -> None:
    category(world)
    r1, r2 = recruit(world, "첫 공고"), recruit(world, "둘째 공고")
    me, other = applicant(world), applicant(world, "박다라")
    as_member(world, other)
    theirs = apply(world, body(r1)).json()
    as_member(world, me)
    first = apply(world, body(r1)).json()
    world.db.execute(
        text("UPDATE TB_INSTR_APLY SET SBMSN_DT = SBMSN_DT - INTERVAL 1 DAY WHERE INSTR_APLY_SN=:s"),
        {"s": first["applicationId"]},
    )
    second = apply(world, body(r2)).json()
    listed = get(world, "/me/instructor-applications").json()
    assert [i["applicationId"] for i in listed["items"]] == [
        second["applicationId"],
        first["applicationId"],
    ] and listed["total"] == 2
    assert [
        len(get(world, f"/me/instructor-applications?size=1&page={n}").json()["items"]) for n in (1, 2, 3)
    ] == [1, 1, 0]
    assert (
        get(world, f"/me/instructor-applications/{first['applicationId']}").json()["recruitmentTitle"]
        == "첫 공고"
    )
    assert get(world, f"/me/instructor-applications/{theirs['applicationId']}").status_code == 404
    assert get(world, "/me/instructor-applications/999999999").status_code == 404


def test_서류_검토중인_지원서는_고칠_수_있고_공고는_바꿀_수_없다(world: World) -> None:
    category(world)
    category(world, "문화예술")
    rcrt, other = recruit(world), recruit(world, "다른 공고")
    as_member(world, applicant(world))
    sn = apply(world, body(rcrt)).json()["applicationId"]
    r = send(
        world,
        "PUT",
        f"/me/instructor-applications/{sn}",
        body(rcrt, desiredCourse="  요가 심화반 ", categoryName="문화예술", career="경력 15년"),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["desiredCourse"], out["categoryName"], out["career"], out["status"], out["canEdit"]) == (
        "요가 심화반",
        "문화예술",
        "경력 15년",
        "REVIEWING",
        True,
    )
    [row] = rows(world, "SELECT RCRD_VER v, MDFCN_DT d, HOPE_FLD_NM c FROM TB_INSTR_APLY")
    assert (row["v"], row["c"]) == (2, "문화예술") and row["d"] is not None
    assert rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_APLY_UPDATE'")[0]["n"] == 1
    moved = send(world, "PUT", f"/me/instructor-applications/{sn}", body(other))
    assert moved.status_code == 422 and "recruitmentId" in moved.json()["fields"]
    for bad in ({"categoryName": "없는 분야"}, {"career": "  "}, {"desiredCourse": "  "}):
        r = send(world, "PUT", f"/me/instructor-applications/{sn}", body(rcrt, **bad))
        assert r.status_code == 422, bad
    assert get(world, f"/me/instructor-applications/{sn}").json()["career"] == "경력 15년"


def test_심사가_끝난_지원서와_남의_지원서는_고칠_수_없다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    me, other = applicant(world), applicant(world, "박다라")
    as_member(world, other)
    theirs = apply(world, body(rcrt)).json()["applicationId"]
    as_member(world, me)
    sn = apply(world, body(rcrt)).json()["applicationId"]
    assert (
        send(world, "PUT", f"/me/instructor-applications/{theirs}", body(rcrt, career="가로채기")).status_code
        == 404
    )
    for status in ("IA.APPROVE", "IA.REJECT"):
        world.db.execute(
            text("UPDATE TB_INSTR_APLY SET SRNG_STTS_CD=:s, RJCT_RSN=NULL WHERE INSTR_APLY_SN=:i"),
            {"s": status, "i": sn},
        )
        world.db.commit()
        r = send(world, "PUT", f"/me/instructor-applications/{sn}", body(rcrt, career="수정 시도"))
        assert r.status_code == 422 and "status" in r.json()["fields"], status
        view = get(world, f"/me/instructor-applications/{sn}").json()
        assert (view["canEdit"], view["status"]) == (
            False,
            "SELECTED" if status == "IA.APPROVE" else "REJECTED",
        )
    assert (
        rows(world, "SELECT CRR_CN c FROM TB_INSTR_APLY WHERE INSTR_APLY_SN=:i", i=sn)[0]["c"]
        == "요가 지도 10년"
    )


# --- 증빙 ---------------------------------------------------------------------------------------


def test_서류_검토중인_내_지원서에_증빙을_올리고_지우고_내려받는다(world: World, root: Path) -> None:
    category(world)
    rcrt = recruit(world)
    me = applicant(world)
    as_member(world, me)
    sn = apply(world, body(rcrt)).json()["applicationId"]
    r = up(world, sn, "자격증.pdf")
    assert r.status_code == 201, r.text
    assert (r.json()["fileName"], r.json()["status"]) == ("자격증.pdf", "PENDING")
    [row] = files_of(world)
    assert (str(row["INSTR_APLY_SN"]), row["FILE_USE_CD"], row["FILE_STTS_CD"], row["PST_SN"]) == (
        sn,
        "FP.PROOF",
        "FS.PENDING",
        None,
    )
    listed = get(world, f"/me/instructor-applications/{sn}/files").json()
    assert (listed["canEdit"], listed["maxFiles"], len(listed["items"])) == (True, 5, 1)
    fid = int(r.json()["fileId"])
    assert get(world, f"/me/files/{fid}").status_code == 404  # 검사 전
    put(world, fid)
    dl = get(world, f"/me/files/{fid}")
    assert dl.status_code == 200 and dl.content == PDF
    assert send(world, "DELETE", f"/me/files/{fid}").status_code == 204
    assert get(world, f"/me/instructor-applications/{sn}/files").json()["items"] == []


def test_증빙은_다섯_개까지이고_형식이_틀리면_거절한다(world: World, root: Path) -> None:
    category(world)
    rcrt = recruit(world)
    as_member(world, applicant(world))
    sn = apply(world, body(rcrt)).json()["applicationId"]
    assert up(world, sn, "가짜.pdf", b"not a pdf").status_code == 422
    for n in range(5):
        assert up(world, sn, f"f{n}.pdf").status_code == 201
    assert up(world, sn, "f5.pdf").status_code == 422


def test_심사가_끝난_지원서의_증빙은_잠기고_남의_지원서에는_올릴_수_없다(world: World, root: Path) -> None:
    category(world)
    rcrt = recruit(world)
    me, other = applicant(world), applicant(world, "박다라")
    as_member(world, other)
    theirs = apply(world, body(rcrt)).json()["applicationId"]
    as_member(world, me)
    sn = apply(world, body(rcrt)).json()["applicationId"]
    fid = up(world, sn).json()["fileId"]
    assert get(world, f"/me/instructor-applications/{theirs}/files").status_code == 404
    assert up(world, theirs).status_code == 404
    world.db.execute(
        text("UPDATE TB_INSTR_APLY SET SRNG_STTS_CD='IA.APPROVE' WHERE INSTR_APLY_SN=:i"), {"i": sn}
    )
    world.db.commit()
    locked = up(world, sn)
    assert locked.status_code == 409 and locked.json()["code"] == "CONFLICT_STATE"
    assert send(world, "DELETE", f"/me/files/{fid}").status_code == 409
    assert get(world, f"/me/instructor-applications/{sn}/files").json()["canEdit"] is False


# --- 관리자와 이어지는 흐름 ---------------------------------------------------------------------


def test_주민_지원이_관리자_심사_목록에_접수로_보이고_승인하면_결과가_보인다(world: World) -> None:
    category(world)
    rcrt = recruit(world)
    me = applicant(world, "김지원")
    as_member(world, me)
    sn = apply(world, body(rcrt)).json()["applicationId"]
    world.db.commit()
    use(world, staff(world, "boss", "AU.INSTR_W"))
    items = call(world, "GET", "/instructor-applications?status=PENDING").json()["items"]
    assert [(i["applicationId"], i["applicantName"], i["desiredCourse"]) for i in items] == [
        (sn, "김지원", "요가 기초반")
    ]
    detail = call(world, "GET", f"/instructor-applications/{sn}").json()
    assert (detail["source"], detail["categoryName"], detail["career"]) == (
        "ONLINE",
        "생활체육",
        "요가 지도 10년",
    )
    approved = call(
        world,
        "PUT",
        f"/instructor-applications/{sn}",
        {"status": "APPROVED", "isPublic": False, "version": 1},
    )
    assert approved.status_code == 200, approved.text  # 회원과 연결된 온라인 지원이라 승인할 수 있다
    as_member(world, me)
    view = get(world, f"/me/instructor-applications/{sn}").json()
    assert (view["status"], view["canEdit"]) == ("SELECTED", False)


def test_관리자는_묶음_전체_권한일_때만_지원_증빙을_보고_올리고_내려받는다(world: World, root: Path) -> None:
    category(world)
    rcrt = recruit(world)
    a = dong(world, "가동")
    as_member(world, applicant(world))
    sn = apply(world, body(rcrt)).json()["applicationId"]
    fid = int(up(world, sn).json()["fileId"])
    put(world, fid)
    world.db.commit()
    for who in (
        staff(world, "other", "AU.CORS_W"),
        staff(world, "dongstaff", "AU.INSTR_W", kind="SK.DONG", dong_sn=a["DONG_SN"]),
    ):
        use(world, who)
        assert call(world, "GET", f"/instructor-applications/{sn}/files").status_code in (403, 404)
        assert call(world, "GET", f"/files/{fid}/download").status_code == 404
    boss = staff(world, "boss", "AU.INSTR_W")
    use(world, boss)
    listed = call(world, "GET", f"/instructor-applications/{sn}/files").json()
    assert (listed["canEdit"], [i["fileName"] for i in listed["items"]]) == (True, ["자격증.pdf"])
    assert call(world, "GET", f"/files/{fid}/download").content == PDF
    added = upload(world, f"/instructor-applications/{sn}/files", "면접메모.pdf")
    assert added.status_code == 201, added.text
    world.db.execute(
        text("UPDATE TB_INSTR_APLY SET SRNG_STTS_CD='IA.REJECT', RJCT_RSN='x' WHERE INSTR_APLY_SN=:i"),
        {"i": sn},
    )
    world.db.commit()
    assert upload(world, f"/instructor-applications/{sn}/files", "추가.pdf").status_code == 409
    assert call(world, "GET", f"/instructor-applications/{sn}/files").json()["canEdit"] is False
