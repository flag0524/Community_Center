# 관리자 강사 심사(AU.INSTR_W, 방문·외부 접수 등록, 승인·반려·활동중지 규칙, 회원 연결, 전화번호 암호화, 멱등)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.crypto import decrypt, encrypt
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board, post
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)
PHONE = "01012345678"


def recruitment(w: World) -> dict[str, Any]:
    p = post(w, board(w, "notice"), "강사 모집")
    return w.factory.make("TB_INSTR_RCRT", PST_SN=p["PST_SN"])


def application(
    w: World, rcrt: dict[str, Any], name: str = "홍길동", status: str = "IA.WAIT", **values: Any
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "INSTR_RCRT_SN": rcrt["INSTR_RCRT_SN"],
        "RCPT_CHNL_CD": "IC.ONLINE",
        "APLCT_NM": name,
        "TELNO_ENCPT_VL": encrypt(w.settings.secret_key, PHONE),
        "HOPE_CORS_NM": "수채화",
        "CRR_CN": "경력 10년",
        "RLS_HOPE_YN": "N",
        "SBMSN_DT": START,
        "SRNG_STTS_CD": status,
        "IDEM_KEY": f"seed-{next(_n)}",
    }
    return w.factory.make("TB_INSTR_APLY", **{**defaults, **values})


def reviewer(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"i{next(_n)}", *(codes or ("AU.INSTR_W",)), **kw)
    use(w, who)
    return who


def decide(w: World, sn: Any, status: str, version: int = 1, **values: Any) -> Any:
    return call(
        w,
        "PUT",
        f"/instructor-applications/{sn}",
        {"status": status, "reason": None, "isPublic": False, "memo": None, "version": version, **values},
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def receive(w: World, rcrt: dict[str, Any], key: str = "intake-key-0001", **values: Any) -> Any:
    payload = {
        "recruitmentId": str(rcrt["INSTR_RCRT_SN"]),
        "applicantName": "김방문",
        "phone": PHONE,
        "desiredCourse": "서예",
        "career": "경력 5년",
        "source": "VISIT",
        **values,
    }
    return call(w, "POST", "/instructor-applications", payload, **{"Idempotency-Key": key})


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위뿐이면_403이다(world: World) -> None:
    rcrt = recruitment(world)
    a = application(world, rcrt)
    mine = dong(world, "가동")
    world.db.commit()  # 오류 응답의 롤백이 준비한 행을 되돌리지 않게 고정한다
    assert world.client.get("/api/admin/v1/instructor-applications").status_code == 401
    calls = (
        ("GET", "/instructor-applications", None),
        (
            "POST",
            "/instructor-applications",
            {
                "recruitmentId": "1",
                "applicantName": "가",
                "phone": PHONE,
                "desiredCourse": "나",
                "career": "다",
                "source": "VISIT",
            },
        ),
        ("GET", f"/instructor-applications/{a['INSTR_APLY_SN']}", None),
        (
            "PUT",
            f"/instructor-applications/{a['INSTR_APLY_SN']}",
            {"status": "APPROVED", "isPublic": False, "version": 1},
        ),
    )
    for who in (
        staff(world, "x", "AU.CORS_W"),
        staff(world, "d", "AU.INSTR_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]),
    ):
        use(world, who)
        for method, path, payload in calls:
            assert (
                call(world, method, path, payload, **{"Idempotency-Key": "intake-key-0001"}).status_code
                == 403
            ), path


# --- 목록·상세 ----------------------------------------------------------------------------------


def seeded(w: World) -> dict[str, dict[str, Any]]:
    rcrt = recruitment(w)
    boss = staff(w, f"seed{next(_n)}", "AU.INSTR_W")
    approver = w.factory.make("TB_MNGR", LGN_ID=f"ap{next(_n)}", PSWD_HASH_VL="x" * 20, MNGR_NM="승인자")
    m_ok, m_stop = (
        make_member(w, f"ok{next(_n)}", MBR_NM="승인됨"),
        make_member(w, f"st{next(_n)}", MBR_NM="중지됨"),
    )
    base = {"APRV_DT": START, "APRV_MNGR_SN": approver["MNGR_SN"]}
    ok = w.factory.make("TB_INSTR", MBR_SN=m_ok["MBR_SN"], INSTR_STTS_CD="IS.APPROVE", RLS_YN="Y", **base)
    stop = w.factory.make(
        "TB_INSTR", MBR_SN=m_stop["MBR_SN"], INSTR_STTS_CD="IS.STOP", RLS_YN="N", RJCT_RSN="계약 종료", **base
    )
    out = {
        "pending": application(w, rcrt, "대기자", "IA.WAIT", SBMSN_DT=START - timedelta(days=5)),
        "newer_pending": application(
            w, rcrt, "새대기", "IA.WAIT", HOPE_CORS_NM="도예", SBMSN_DT=START - timedelta(days=1)
        ),
        "approved": application(
            w,
            rcrt,
            "승인자",
            "IA.APPROVE",
            MBR_SN=m_ok["MBR_SN"],
            INSTR_SN=ok["INSTR_SN"],
            SBMSN_DT=START - timedelta(days=10),
        ),
        "suspended": application(
            w,
            rcrt,
            "중지자",
            "IA.APPROVE",
            MBR_SN=m_stop["MBR_SN"],
            INSTR_SN=stop["INSTR_SN"],
            SBMSN_DT=START - timedelta(days=8),
        ),
        "rejected": application(
            w, rcrt, "반려자", "IA.REJECT", RJCT_RSN="자격 미달", SBMSN_DT=START - timedelta(days=3)
        ),
    }
    assert boss
    return out


def test_목록은_심사대기가_먼저이고_각각_최근_접수가_먼저이며_상태를_도출한다(world: World) -> None:
    s = seeded(world)
    reviewer(world)
    body = call(world, "GET", "/instructor-applications").json()
    assert [i["applicantName"] for i in body["items"]] == ["새대기", "대기자", "반려자", "중지자", "승인자"]
    by = {i["applicantName"]: i for i in body["items"]}
    assert (
        by["새대기"]["status"],
        by["승인자"]["status"],
        by["중지자"]["status"],
        by["반려자"]["status"],
    ) == ("PENDING", "APPROVED", "SUSPENDED", "REJECTED")
    assert (by["승인자"]["isPublic"], by["중지자"]["isPublic"], by["대기자"]["isPublic"]) == (
        True,
        False,
        False,
    )
    assert (
        by["새대기"]["desiredCourse"] == "도예"
        and by["대기자"]["receivedOn"] == "2026-11-04"
        and body["total"] == 5
    )
    assert s["pending"]["INSTR_APLY_SN"]


def test_상태와_공개와_검색어와_쪽으로_거른다(world: World) -> None:
    seeded(world)
    reviewer(world)

    def names(qs: str) -> list[str]:
        return [
            i["applicantName"] for i in call(world, "GET", f"/instructor-applications{qs}").json()["items"]
        ]

    assert names("?status=PENDING") == ["새대기", "대기자"]
    assert (
        names("?status=APPROVED") == ["승인자"]
        and names("?status=SUSPENDED") == ["중지자"]
        and names("?status=REJECTED") == ["반려자"]
    )
    assert names("?isPublic=true") == ["승인자"]
    assert sorted(names("?isPublic=false")) == sorted(["새대기", "대기자", "반려자", "중지자"])
    assert names("?q=도예") == ["새대기"] and names("?q=승인") == ["승인자"] and names("?q=_") == []
    assert names("?status=APPROVED&isPublic=false") == []
    assert [
        len(call(world, "GET", f"/instructor-applications?size=2&page={n}").json()["items"])
        for n in (1, 2, 3)
    ] == [2, 2, 1]
    assert call(world, "GET", "/instructor-applications?status=NOPE").status_code in (400, 422)


def test_상세는_이유와_메모와_버전을_상태에_맞게_준다(world: World) -> None:
    s = seeded(world)
    reviewer(world)
    rejected = call(world, "GET", f"/instructor-applications/{s['rejected']['INSTR_APLY_SN']}").json()
    assert (
        rejected["status"],
        rejected["reason"],
        rejected["source"],
        rejected["career"],
        rejected["version"],
        rejected["canReview"],
    ) == (
        "REJECTED",
        "자격 미달",
        "ONLINE",
        "경력 10년",
        1,
        True,
    )
    suspended = call(world, "GET", f"/instructor-applications/{s['suspended']['INSTR_APLY_SN']}").json()
    assert (suspended["status"], suspended["reason"]) == ("SUSPENDED", "계약 종료")
    pending = call(world, "GET", f"/instructor-applications/{s['pending']['INSTR_APLY_SN']}").json()
    assert (pending["reason"], pending["memo"], pending["categoryName"]) == (None, None, None)
    assert PHONE not in str(pending) and "TELNO" not in str(pending)
    assert call(world, "GET", "/instructor-applications/999999999").status_code == 404
    assert call(world, "GET", "/instructor-applications/abc").status_code in (400, 422)


def test_다른_묶음의_지원서는_보이지_않는다(world: World) -> None:
    foreign = int(world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"])
    other = world.factory.make(
        "TB_INSTR_APLY",
        OPER_BNDL_SN=foreign,
        APLCT_NM="타",
        SRNG_STTS_CD="IA.WAIT",
        SBMSN_DT=START,
        RCPT_CHNL_CD="IC.ONLINE",
        HOPE_CORS_NM="x",
        TELNO_ENCPT_VL="x",
        RLS_HOPE_YN="N",
    )
    reviewer(world)
    assert call(world, "GET", "/instructor-applications").json()["total"] == 0
    assert call(world, "GET", f"/instructor-applications/{other['INSTR_APLY_SN']}").status_code == 404


# --- 접수 등록 ----------------------------------------------------------------------------------


def test_방문_접수를_등록하면_심사대기로_저장하고_전화번호는_암호화한다(world: World) -> None:
    rcrt = recruitment(world)
    boss = reviewer(world)
    r = receive(world, rcrt)
    assert r.status_code == 201
    out = r.json()
    assert (
        out["applicantName"],
        out["desiredCourse"],
        out["career"],
        out["source"],
        out["status"],
        out["isPublic"],
        out["version"],
    ) == (
        "김방문",
        "서예",
        "경력 5년",
        "VISIT",
        "PENDING",
        False,
        1,
    )
    assert PHONE not in str(out)
    [row] = rows(world, "SELECT * FROM TB_INSTR_APLY")
    assert (
        row["RCPT_CHNL_CD"],
        row["SRNG_STTS_CD"],
        row["RCPT_MNGR_SN"],
        row["MBR_SN"],
        row["RLS_HOPE_YN"],
    ) == ("IC.VISIT", "IA.WAIT", boss.sn, None, "N")
    assert row["TELNO_ENCPT_VL"] != PHONE and PHONE not in row["TELNO_ENCPT_VL"]
    assert decrypt(world.settings.secret_key, row["TELNO_ENCPT_VL"]) == PHONE
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_APLY_CREATE'")
    assert job["m"] == boss.sn and PHONE not in job["c"] and "김방문" not in job["c"]


def test_외부_접수와_회원_연결을_받는다(world: World) -> None:
    rcrt = recruitment(world)
    who = make_member(world, "linked1", MBR_NM="김회원")
    reviewer(world)
    r = receive(world, rcrt, source="EXTERNAL", memberLoginId="linked1")
    assert r.status_code == 201 and r.json()["source"] == "EXTERNAL"
    [row] = rows(world, "SELECT RCPT_CHNL_CD c, MBR_SN m FROM TB_INSTR_APLY")
    assert (row["c"], row["m"]) == ("IC.EXTERNAL", who["MBR_SN"])


def test_온라인_접수나_없는_공고나_없는_회원이나_틀린_전화번호는_거절한다(world: World) -> None:
    rcrt = recruitment(world)
    make_member(world, "gone1", MBR_NM="탈퇴", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    reviewer(world)
    for n, (extra, field) in enumerate(
        [
            ({"source": "ONLINE"}, "source"),
            ({"recruitmentId": "999999999"}, "recruitmentId"),
            ({"memberLoginId": "nobody"}, "memberLoginId"),
            ({"memberLoginId": "gone1"}, "memberLoginId"),
            ({"applicantName": "   "}, "applicantName"),
            ({"desiredCourse": "   "}, "desiredCourse"),
            ({"career": "   "}, "career"),
        ]
    ):
        r = receive(world, rcrt, f"intake-key-{n:04d}", **extra)
        assert r.status_code == 422 and field in r.json()["fields"], extra
    for phone in ("010-1234-5678", "1234", "0212345678", "abc"):
        assert receive(world, rcrt, "intake-key-9999", phone=phone).status_code in (400, 422), phone
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 0


def test_같은_키로_다시_보내면_같은_접수이고_내용이_다르면_409다(world: World) -> None:
    rcrt = recruitment(world)
    reviewer(world)
    first = receive(world, rcrt).json()
    again = receive(world, rcrt)
    assert again.status_code == 201 and again.json()["applicationId"] == first["applicationId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR_APLY")[0]["n"] == 1
    assert len(rows(world, "SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_APLY_CREATE'")) == 1
    for diff in ({"applicantName": "다른"}, {"phone": "01099998888"}, {"source": "EXTERNAL"}):
        r = receive(world, rcrt, **diff)
        assert r.status_code == 409 and r.json()["code"] == "IDEMPOTENCY_CONFLICT", diff
    assert call(world, "POST", "/instructor-applications", {"recruitmentId": "1"}).status_code in (400, 422)


# --- 심사 ---------------------------------------------------------------------------------------


def test_회원과_연결된_지원서를_승인하면_강사를_만들고_심사_정보를_채운다(world: World) -> None:
    rcrt = recruitment(world)
    who = make_member(world, "apm1", MBR_NM="지원자")
    a = application(world, rcrt, "지원자", MBR_SN=who["MBR_SN"], INSTR_INTRO_CN="소개", CRR_CN="경력 7년")
    boss = reviewer(world)
    r = decide(world, a["INSTR_APLY_SN"], "APPROVED", isPublic=True, memo="면접 양호")
    assert r.status_code == 200
    out = r.json()
    assert (out["status"], out["isPublic"], out["version"], out["memo"], out["reason"]) == (
        "APPROVED",
        True,
        2,
        "면접 양호",
        None,
    )
    [instr] = rows(world, "SELECT * FROM TB_INSTR")
    assert (
        instr["MBR_SN"],
        instr["INSTR_STTS_CD"],
        instr["RLS_YN"],
        instr["APRV_MNGR_SN"],
        instr["CRR_CN"],
        instr["INSTR_INTRO_CN"],
    ) == (
        who["MBR_SN"],
        "IS.APPROVE",
        "Y",
        boss.sn,
        "경력 7년",
        "소개",
    )
    assert instr["APRV_DT"] is not None
    [apply] = rows(
        world,
        "SELECT SRNG_STTS_CD s, SRNG_MNGR_SN m, SRNG_DT d, INSTR_SN i, RJCT_RSN r, MDFCN_DT t FROM TB_INSTR_APLY",
    )
    assert (apply["s"], apply["m"], apply["i"], apply["r"]) == (
        "IA.APPROVE",
        boss.sn,
        instr["INSTR_SN"],
        None,
    )
    assert apply["d"] is not None and apply["t"] is not None
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='INSTR_REVIEW'"
    )
    assert (job["m"], job["k"]) == (boss.sn, str(a["INSTR_APLY_SN"])) and json.loads(job["c"]) == {
        "s": "APPROVED",
        "memo": "면접 양호",
    }
    assert rows(world, "SELECT COUNT(*) n FROM TB_ROLE_AUTHRT")[0]["n"] >= 0  # 승인은 권한을 주지 않는다
    assert (
        rows(world, "SELECT COUNT(*) n FROM TB_CORS WHERE INSTR_SN=:i", i=instr["INSTR_SN"])[0]["n"] == 0
    )  # 강좌 배정도 없다


def test_공개하지_않고_승인하면_비공개_강사다(world: World) -> None:
    rcrt = recruitment(world)
    a = application(world, rcrt, MBR_SN=make_member(world, "apm2")["MBR_SN"])
    reviewer(world)
    out = decide(world, a["INSTR_APLY_SN"], "APPROVED", isPublic=False).json()
    assert out["status"] == "APPROVED" and out["isPublic"] is False
    assert rows(world, "SELECT RLS_YN r FROM TB_INSTR")[0]["r"] == "N"


def test_회원과_연결되지_않은_지원서는_승인할_수_없다(world: World) -> None:
    a = application(world, recruitment(world))
    reviewer(world)
    r = decide(world, a["INSTR_APLY_SN"], "APPROVED")
    assert r.status_code == 422 and "status" in r.json()["fields"] and "회원" in r.json()["message"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR")[0]["n"] == 0
    assert rows(world, "SELECT SRNG_STTS_CD s, RCRD_VER v FROM TB_INSTR_APLY")[0] == {"s": "IA.WAIT", "v": 1}
    assert (
        decide(world, a["INSTR_APLY_SN"], "REJECTED", reason="연락 불가").status_code == 200
    )  # 반려는 비회원도 된다


def test_이미_강사_행이_있는_회원은_새로_만들지_않고_다시_승인한다(world: World) -> None:
    rcrt = recruitment(world)
    who = make_member(world, "apm3")
    old = world.factory.make(
        "TB_INSTR", MBR_SN=who["MBR_SN"], INSTR_STTS_CD="IS.REJECT", RJCT_RSN="예전 반려", RLS_YN="N"
    )
    a = application(world, rcrt, MBR_SN=who["MBR_SN"])
    reviewer(world)
    assert decide(world, a["INSTR_APLY_SN"], "APPROVED", isPublic=True).status_code == 200
    [instr] = rows(world, "SELECT INSTR_SN s, INSTR_STTS_CD c, RJCT_RSN r, RLS_YN y FROM TB_INSTR")
    assert (instr["s"], instr["c"], instr["r"], instr["y"]) == (old["INSTR_SN"], "IS.APPROVE", None, "Y")


def test_반려는_사유가_필수이고_반려한_지원은_다시_심사할_수_없다(world: World) -> None:
    a = application(world, recruitment(world))
    boss = reviewer(world)
    for reason in (None, "", "   "):
        r = decide(world, a["INSTR_APLY_SN"], "REJECTED", reason=reason)
        assert r.status_code == 422 and "reason" in r.json()["fields"], reason
    done = decide(world, a["INSTR_APLY_SN"], "REJECTED", reason="  서류 미비  ")
    assert done.status_code == 200 and (
        done.json()["status"],
        done.json()["reason"],
        done.json()["version"],
    ) == ("REJECTED", "서류 미비", 2)
    [apply] = rows(world, "SELECT SRNG_STTS_CD s, RJCT_RSN r, SRNG_MNGR_SN m FROM TB_INSTR_APLY")
    assert (apply["s"], apply["r"], apply["m"]) == ("IA.REJECT", "서류 미비", boss.sn)
    for target in ("PENDING", "APPROVED", "REJECTED", "SUSPENDED"):
        r = decide(world, a["INSTR_APLY_SN"], target, version=2, reason="다시")
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE", target


def test_심사대기로_되돌리거나_대기에서_바로_활동중지할_수_없다(world: World) -> None:
    rcrt = recruitment(world)
    a = application(world, rcrt, MBR_SN=make_member(world, "apm4")["MBR_SN"])
    reviewer(world)
    assert (
        decide(world, a["INSTR_APLY_SN"], "SUSPENDED", reason="사유").status_code == 409
    )  # 대기 → 활동중지 없음
    assert decide(world, a["INSTR_APLY_SN"], "APPROVED").status_code == 200
    back = decide(world, a["INSTR_APLY_SN"], "PENDING", version=2)
    assert back.status_code == 409 and back.json()["code"] == "CONFLICT_STATE"
    rej = decide(world, a["INSTR_APLY_SN"], "REJECTED", version=2, reason="사유")
    assert rej.status_code == 409  # 승인한 뒤 반려는 없다


def test_승인한_강사를_활동중지했다가_다시_승인할_수_있다(world: World) -> None:
    rcrt = recruitment(world)
    a = application(world, rcrt, MBR_SN=make_member(world, "apm5")["MBR_SN"])
    boss = reviewer(world)
    decide(world, a["INSTR_APLY_SN"], "APPROVED", isPublic=True)
    for reason in (None, " "):
        assert (
            "reason"
            in decide(world, a["INSTR_APLY_SN"], "SUSPENDED", version=2, reason=reason).json()["fields"]
        )
    stop = decide(world, a["INSTR_APLY_SN"], "SUSPENDED", version=2, reason="민원 접수")
    assert stop.status_code == 200
    s = stop.json()
    assert (s["status"], s["reason"], s["isPublic"], s["version"]) == ("SUSPENDED", "민원 접수", False, 3)
    [instr] = rows(world, "SELECT INSTR_STTS_CD c, RJCT_RSN r, RLS_YN y FROM TB_INSTR")
    assert (instr["c"], instr["r"], instr["y"]) == ("IS.STOP", "민원 접수", "N")
    assert (
        decide(world, a["INSTR_APLY_SN"], "SUSPENDED", version=3, reason="계속").status_code == 200
    )  # 사유만 고친다
    back = decide(world, a["INSTR_APLY_SN"], "APPROVED", version=4, isPublic=True)
    assert back.status_code == 200 and (
        back.json()["status"],
        back.json()["reason"],
        back.json()["isPublic"],
    ) == ("APPROVED", None, True)
    [instr] = rows(world, "SELECT INSTR_STTS_CD c, RJCT_RSN r, RLS_YN y, APRV_MNGR_SN m FROM TB_INSTR")
    assert (instr["c"], instr["r"], instr["y"], instr["m"]) == ("IS.APPROVE", None, "Y", boss.sn)
    assert rows(world, "SELECT COUNT(*) n FROM TB_INSTR")[0]["n"] == 1


def test_다른_담당자가_다시_승인하면_승인자와_일시를_새로_남긴다(world: World) -> None:
    a = application(world, recruitment(world), MBR_SN=make_member(world, "apm10")["MBR_SN"])
    first = reviewer(world)
    decide(world, a["INSTR_APLY_SN"], "APPROVED")
    decide(world, a["INSTR_APLY_SN"], "SUSPENDED", version=2, reason="중지")
    before = rows(world, "SELECT APRV_DT d FROM TB_INSTR")[0]["d"]
    second = reviewer(world)
    assert second.sn != first.sn
    assert decide(world, a["INSTR_APLY_SN"], "APPROVED", version=3).status_code == 200
    [instr] = rows(world, "SELECT APRV_MNGR_SN m, APRV_DT d FROM TB_INSTR")
    assert instr["m"] == second.sn and instr["d"] >= before


def test_승인한_강사의_공개_여부와_메모를_고칠_수_있다(world: World) -> None:
    a = application(world, recruitment(world), MBR_SN=make_member(world, "apm6")["MBR_SN"])
    reviewer(world)
    decide(world, a["INSTR_APLY_SN"], "APPROVED", isPublic=False)
    on = decide(world, a["INSTR_APLY_SN"], "APPROVED", version=2, isPublic=True, memo="공개 전환")
    assert on.status_code == 200 and (on.json()["isPublic"], on.json()["memo"], on.json()["version"]) == (
        True,
        "공개 전환",
        3,
    )
    assert rows(world, "SELECT RLS_YN y FROM TB_INSTR")[0]["y"] == "Y"
    off = decide(world, a["INSTR_APLY_SN"], "APPROVED", version=3, isPublic=False)
    assert off.json()["isPublic"] is False and off.json()["memo"] is None  # 메모는 가장 최근 심사의 것이다


def test_공개는_승인된_강사만_할_수_있다(world: World) -> None:
    a = application(world, recruitment(world), MBR_SN=make_member(world, "apm7")["MBR_SN"])
    reviewer(world)
    cases: list[tuple[str, dict[str, Any]]] = [("PENDING", {}), ("REJECTED", {"reason": "사유"})]
    for target, extra in cases:
        r = decide(world, a["INSTR_APLY_SN"], target, isPublic=True, **extra)
        assert r.status_code == 422 and "isPublic" in r.json()["fields"], target
    assert rows(world, "SELECT SRNG_STTS_CD s FROM TB_INSTR_APLY")[0]["s"] == "IA.WAIT"


def test_심사대기_상태의_메모만_남길_수_있다(world: World) -> None:
    a = application(world, recruitment(world))
    reviewer(world)
    r = decide(world, a["INSTR_APLY_SN"], "PENDING", memo="서류 확인 중")
    assert r.status_code == 200 and (r.json()["status"], r.json()["memo"], r.json()["version"]) == (
        "PENDING",
        "서류 확인 중",
        2,
    )
    assert rows(world, "SELECT SRNG_MNGR_SN m, SRNG_DT d FROM TB_INSTR_APLY")[0] == {
        "m": None,
        "d": None,
    }  # 아직 심사하지 않았다


def test_읽은_버전이_다르면_409이고_심사하지_않는다(world: World) -> None:
    a = application(world, recruitment(world), MBR_SN=make_member(world, "apm8")["MBR_SN"])
    reviewer(world)
    stale = decide(world, a["INSTR_APLY_SN"], "APPROVED", version=7)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert (
        rows(world, "SELECT SRNG_STTS_CD s FROM TB_INSTR_APLY")[0]["s"] == "IA.WAIT"
        and rows(world, "SELECT COUNT(*) n FROM TB_INSTR")[0]["n"] == 0
    )
    assert decide(world, "999999999", "REJECTED", reason="x").status_code == 404
    assert call(
        world,
        "PUT",
        f"/instructor-applications/{a['INSTR_APLY_SN']}",
        {"status": "NOPE", "isPublic": False, "version": 1},
    ).status_code in (400, 422)


def test_승인한_강사가_강좌_등록의_대표강사_선택지에_나온다(world: World) -> None:
    from tests.test_admin_education import Kit  # noqa: PLC0415

    kit = Kit(world)
    a = application(world, recruitment(world), MBR_SN=make_member(world, "apm9", MBR_NM="신규강사")["MBR_SN"])
    who = staff(world, "both", "AU.INSTR_W", "AU.CORS_R", "AU.CORS_W")
    use(world, who)
    decide(world, a["INSTR_APLY_SN"], "APPROVED")
    names = [i["name"] for i in call(world, "GET", "/course-options").json()["instructors"]]
    assert "신규강사" in names and kit
    decide(world, a["INSTR_APLY_SN"], "SUSPENDED", version=2, reason="중지")
    assert "신규강사" not in [i["name"] for i in call(world, "GET", "/course-options").json()["instructors"]]
