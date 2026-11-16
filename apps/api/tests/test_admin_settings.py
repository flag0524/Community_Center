# 관리자 운영 설정(읽기 전용)과 공통 코드(표시명·순서·사용 여부, 한 번에 저장, 코드값 불변)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import application, open_course
from tests.test_board_public import board
from tests.test_member_inquiries import asked, category
from tests.world import World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)


def reader(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"st{next(_n)}", *codes, **kw)
    use(w, who)
    return who


def rule(
    w: World,
    cid: str,
    title: str,
    version: str = "v1",
    body: str = "기준 내용",
    status: str = "OR.REVIEW",
    **values: Any,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "CONTS_TYPE_CD": "CT.OPER_RULE",
        "CONTS_ID": cid,
        "CONTS_TTL": title,
        "CONTS_CN": body,
        "VER_NM": version,
        "RVW_STTS_CD": status,
        "SORT_SEQ": next(_n),
    }
    return w.factory.make("TB_SITE_CONTS", **{**defaults, **values})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 운영 설정 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위뿐이면_403이다(world: World) -> None:
    a = dong(world, "가동")
    first = rule(world, "r1", "항목")
    world.db.commit()
    assert world.client.get("/api/admin/v1/settings").status_code == 401
    for who in (
        staff(world, "x", "AU.CORS_W"),
        staff(world, "d", "AU.SITE_W", kind="SK.DONG", dong_sn=a["DONG_SN"]),
    ):
        use(world, who)
        assert call(world, "GET", "/settings").status_code == 403
        assert call(world, "GET", f"/settings/{first['SITE_CONTS_SN']}").status_code == 403


def test_설정_목록은_항목마다_최근_버전만_보이고_다른_콘텐츠는_없다(world: World) -> None:
    rule(world, "age", "정원 기준", "v1", "옛 기준")
    new = rule(world, "age", "정원 기준", "v2", "새 기준")
    other = rule(world, "cancel", "취소 기준", "v1")
    world.factory.make(
        "TB_SITE_CONTS",
        CONTS_TYPE_CD="CT.BANNER",
        CONTS_ID="banner",
        CONTS_TTL="배너",
        CONTS_CN="x",
        VER_NM="v1",
        SORT_SEQ=99,
    )
    reader(world, "AU.SITE_W")
    body = call(world, "GET", "/settings").json()
    assert [i["settingId"] for i in body["items"]] == [
        str(new["SITE_CONTS_SN"]),
        str(other["SITE_CONTS_SN"]),
    ] and body["total"] == 2
    first = body["items"][0]
    assert (first["name"], first["value"], first["status"]) == ("정원 기준", "새 기준", "REVIEW")
    assert first["updatedOn"] == "2026-11-09" or len(first["updatedOn"]) == 10


def test_설정_목록은_상태와_항목명으로_거르고_쪽을_나눈다(world: World) -> None:
    a = rule(world, "a", "정원 기준", status="OR.REVIEW")
    b = rule(world, "b", "취소 기준", status="OR.DECIDED")
    c = rule(world, "c", "환불 기준", status="OR.HOLD")
    reader(world, "AU.SITE_W")

    def ids(qs: str) -> list[str]:
        return [i["settingId"] for i in call(world, "GET", f"/settings{qs}").json()["items"]]

    assert ids("?status=REVIEW") == [str(a["SITE_CONTS_SN"])]
    assert ids("?status=DECIDED") == [str(b["SITE_CONTS_SN"])]
    assert ids("?status=HOLD") == [str(c["SITE_CONTS_SN"])]
    assert ids("?q=환불") == [str(c["SITE_CONTS_SN"])] and ids("?q=_") == [] and ids("?q=%25") == []
    assert [len(call(world, "GET", f"/settings?size=2&page={p}").json()["items"]) for p in (1, 2)] == [2, 1]
    assert call(world, "GET", "/settings?status=NOPE").status_code in (400, 422)


def test_요약은_첫_줄만_여든_자까지이고_본문은_전체를_준다(world: World) -> None:
    long_text = "가" * 100 + "\n둘째 줄"
    item = rule(world, "long", "긴 기준", body=long_text)
    empty = rule(world, "none", "빈 기준", body="")
    reader(world, "AU.SITE_W")
    by = {i["name"]: i for i in call(world, "GET", "/settings").json()["items"]}
    assert by["긴 기준"]["value"] == "가" * 80 + "…" and by["빈 기준"]["value"] == ""
    detail = call(world, "GET", f"/settings/{item['SITE_CONTS_SN']}").json()
    assert detail["body"] == long_text
    assert call(world, "GET", f"/settings/{empty['SITE_CONTS_SN']}").json()["body"] == ""


def test_상세의_버전은_같은_항목의_몇_번째_기준인지이다(world: World) -> None:
    old = rule(world, "age", "정원 기준", "v1")
    new = rule(world, "age", "정원 기준", "v2")
    banner = world.factory.make(
        "TB_SITE_CONTS",
        CONTS_TYPE_CD="CT.BANNER",
        CONTS_ID="banner",
        CONTS_TTL="배너",
        CONTS_CN="x",
        VER_NM="v1",
        SORT_SEQ=99,
    )
    reader(world, "AU.SITE_W")
    assert call(world, "GET", f"/settings/{old['SITE_CONTS_SN']}").json()["version"] == 1
    assert call(world, "GET", f"/settings/{new['SITE_CONTS_SN']}").json()["version"] == 2
    assert call(world, "GET", f"/settings/{banner['SITE_CONTS_SN']}").status_code == 404  # 운영 기준이 아니다
    assert call(world, "GET", "/settings/999999999").status_code == 404 and call(
        world, "GET", "/settings/abc"
    ).status_code in (400, 422)


# --- 공통 코드: 조회 ----------------------------------------------------------------------------


def test_코드_그룹_조회는_배정_권한이_있는_담당자만_한다(world: World) -> None:
    a = dong(world, "가동")
    world.db.commit()
    use(world, staff(world, "x", "AU.SITE_W"))
    for method, path, payload in (
        ("GET", "/code-groups", None),
        ("GET", "/codes?group=ES", None),
        (
            "PUT",
            "/codes",
            {"groupId": "ES", "items": [{"code": "ES.WAIT", "name": "대기", "sortSeq": 1, "use": True}]},
        ),
    ):
        assert call(world, method, path, payload).status_code == 403, path
    use(world, staff(world, "d", "AU.GRANT_W", kind="SK.DONG", dong_sn=a["DONG_SN"]))
    assert (
        call(world, "GET", "/code-groups").status_code == 403
    )  # 코드는 사이트 전체라 묶음 전체 범위가 필요하다


def test_그룹_목록은_코드가_있는_그룹을_이름과_함께_준다(world: World) -> None:
    category(world)
    reader(world, "AU.GRANT_W")
    items = {g["id"]: g["name"] for g in call(world, "GET", "/code-groups").json()["items"]}
    assert items["ES"] == "수강신청 상태" and items["IQ"] == "문의 분류" and items["PS"] == "결제 상태"
    assert list(items) == sorted(items)


def test_코드_목록은_순서대로_주고_업무_건수를_센다(world: World) -> None:
    c = open_course(world)
    for state in ("ES.CONFIRM", "ES.CONFIRM", "ES.WAIT"):
        application(
            world,
            make_member(world, f"cd{next(_n)}"),
            c,
            state,
            **({"WTNG_SEQ": 1} if state == "ES.WAIT" else {}),
        )
    reader(world, "AU.GRANT_W")
    out = call(world, "GET", "/codes?group=ES").json()
    assert out["group"] == {"id": "ES", "name": "수강신청 상태"}
    by = {r["code"]: r for r in out["items"]}
    assert (
        by["ES.CONFIRM"]["refCount"] == 2
        and by["ES.WAIT"]["refCount"] == 1
        and by["ES.CANCEL"]["refCount"] == 0
    )
    assert [r["sortSeq"] for r in out["items"]] == sorted(r["sortSeq"] for r in out["items"])
    assert all(set(r) == {"code", "name", "sortSeq", "use", "refCount"} for r in out["items"])
    unknown = call(world, "GET", "/codes?group=DW").json()["items"]  # 건수를 셀 수 없는 그룹은 null이다
    assert unknown and all(r["refCount"] is None for r in unknown)


def test_문의_분류는_글_수를_세고_이름과_사용_여부로_찾는다(world: World) -> None:
    category(world, "IQ.COURSE", "수강신청", 1)
    category(world, "IQ.ETC", "기타 문의", 2)
    world.db.execute(text("UPDATE TB_COM_CD SET USE_YN='N' WHERE COM_CD='IQ.ETC'"))
    qna = board(world, "qna", MBR_WRT_YN="Y")
    asker = make_member(world, "asker")
    asked(world, qna, asker, "문의 1", INQRY_CLSF_CD="IQ.COURSE")
    asked(world, qna, asker, "문의 2", INQRY_CLSF_CD="IQ.COURSE")
    reader(world, "AU.GRANT_W")
    by = {r["code"]: r for r in call(world, "GET", "/codes?group=IQ").json()["items"]}
    assert (by["IQ.COURSE"]["refCount"], by["IQ.ETC"]["refCount"], by["IQ.ETC"]["use"]) == (2, 0, False)

    def names(qs: str) -> list[str]:
        return [r["code"] for r in call(world, "GET", f"/codes?group=IQ{qs}").json()["items"]]

    assert names("&q=수강") == ["IQ.COURSE"] and names("&q=ETC") == ["IQ.ETC"] and names("&q=_") == []
    assert names("&use=false") == ["IQ.ETC"] and names("&use=true") == ["IQ.COURSE"]
    assert call(world, "GET", "/codes?group=ZZ").status_code == 404
    assert call(world, "GET", "/codes").status_code in (400, 422)


# --- 공통 코드: 저장 ----------------------------------------------------------------------------


def item(code: str, name: str, seq: int, use_: bool = True) -> dict[str, Any]:
    return {"code": code, "name": name, "sortSeq": seq, "use": use_}


def test_표시명과_순서를_고치면_저장하고_바뀐_것만_작업이력에_남긴다(world: World) -> None:
    me = reader(world, "AU.GRANT_W")
    before = {r["COM_CD"].strip(): r for r in rows(world, "SELECT * FROM TB_COM_CD WHERE CD_GROUP_ID='ES'")}
    keep = before["ES.WAIT"]
    res = call(
        world,
        "PUT",
        "/codes",
        {
            "groupId": "ES",
            "items": [
                item("ES.CONFIRM", "  등록 완료  ", 9),
                item("ES.WAIT", keep["CD_NM"], int(keep["SORT_SEQ"])),
            ],
        },
    )
    assert res.status_code == 200, res.text
    out = {r["code"]: r for r in res.json()["items"]}
    assert (out["ES.CONFIRM"]["name"], out["ES.CONFIRM"]["sortSeq"]) == ("등록 완료", 9)
    stored = rows(
        world, "SELECT CD_NM n, SORT_SEQ s, USE_YN u, MDFCN_DT d FROM TB_COM_CD WHERE COM_CD='ES.CONFIRM'"
    )[0]
    assert (stored["n"], stored["s"], stored["u"]) == ("등록 완료", 9, "Y") and stored["d"] is not None
    assert (
        rows(world, "SELECT MDFCN_DT d FROM TB_COM_CD WHERE COM_CD='ES.WAIT'")[0]["d"] == keep["MDFCN_DT"]
    )  # 바뀌지 않은 코드는 건드리지 않는다
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='CODE_UPDATE'"
    )
    assert (job["m"], job["k"]) == (me.sn, "ES") and "ES.CONFIRM" in job["c"] and "ES.WAIT" not in job["c"]
    again = call(world, "PUT", "/codes", {"groupId": "ES", "items": [item("ES.CONFIRM", "등록 완료", 9)]})
    assert again.status_code == 200
    assert (
        rows(world, "SELECT COUNT(*) n FROM TB_JOB_HSTRY WHERE JOB_CD='CODE_UPDATE'")[0]["n"] == 1
    )  # 바뀐 것이 없으면 기록하지 않는다


def test_업무_규칙이_쓰는_그룹은_사용_여부를_바꿀_수_없다(world: World) -> None:
    reader(world, "AU.GRANT_W")
    world.db.commit()
    res = call(
        world,
        "PUT",
        "/codes",
        {"groupId": "ES", "items": [item("ES.CONFIRM", "바뀐 이름", 1), item("ES.WAIT", "대기", 2, False)]},
    )
    assert res.status_code == 422 and "items" in res.json()["fields"]
    assert "수강신청 상태" in res.json()["message"] and "사용 여부" in res.json()["message"]
    assert (
        rows(world, "SELECT CD_NM n FROM TB_COM_CD WHERE COM_CD='ES.CONFIRM'")[0]["n"] != "바뀐 이름"
    )  # 함께 보낸 다른 변경도 저장하지 않는다
    assert rows(world, "SELECT USE_YN u FROM TB_COM_CD WHERE COM_CD='ES.WAIT'")[0]["u"] == "Y"


def test_기관이_정하는_목록은_사용_여부도_바꿀_수_있다(world: World) -> None:
    category(world, "IQ.COURSE", "수강신청", 1)
    category(world, "IQ.ETC", "기타", 2)
    reader(world, "AU.GRANT_W")
    res = call(
        world,
        "PUT",
        "/codes",
        {"groupId": "IQ", "items": [item("IQ.COURSE", "수강신청", 1, False), item("IQ.ETC", "기타 문의", 5)]},
    )
    assert res.status_code == 200
    by = {r["code"]: r for r in res.json()["items"]}
    assert (by["IQ.COURSE"]["use"], by["IQ.ETC"]["name"], by["IQ.ETC"]["sortSeq"]) == (False, "기타 문의", 5)
    stored = {
        r["COM_CD"].strip(): r["USE_YN"]
        for r in rows(world, "SELECT COM_CD, USE_YN FROM TB_COM_CD WHERE CD_GROUP_ID='IQ'")
    }
    assert stored == {"IQ.COURSE": "N", "IQ.ETC": "Y"}  # 끈 분류는 문의 분류 목록(USE_YN=Y)에서 빠진다


def test_없는_코드나_다른_그룹의_코드가_섞이면_404이고_아무것도_저장하지_않는다(world: World) -> None:
    reader(world, "AU.GRANT_W")
    world.db.commit()
    for items in (
        [item("ES.CONFIRM", "바뀜", 1), item("ES.NOPE", "없음", 2)],
        [item("ES.CONFIRM", "바뀜", 1), item("PS.PAID", "다른 그룹", 2)],
    ):
        assert call(world, "PUT", "/codes", {"groupId": "ES", "items": items}).status_code == 404
    assert call(world, "PUT", "/codes", {"groupId": "ZZ", "items": [item("ZZ.A", "x", 1)]}).status_code == 404
    assert rows(world, "SELECT CD_NM n FROM TB_COM_CD WHERE COM_CD='ES.CONFIRM'")[0]["n"] != "바뀜"


def test_빈_표시명과_중복_코드와_빈_목록은_거절한다(world: World) -> None:
    reader(world, "AU.GRANT_W")
    world.db.commit()
    blank = call(world, "PUT", "/codes", {"groupId": "ES", "items": [item("ES.CONFIRM", "   ", 1)]})
    assert blank.status_code == 422 and "items" in blank.json()["fields"]
    dup = call(
        world,
        "PUT",
        "/codes",
        {"groupId": "ES", "items": [item("ES.CONFIRM", "가", 1), item("ES.CONFIRM", "나", 2)]},
    )
    assert dup.status_code == 422 and "items" in dup.json()["fields"]
    assert call(world, "PUT", "/codes", {"groupId": "ES", "items": []}).status_code in (400, 422)
    assert call(
        world, "PUT", "/codes", {"groupId": "ES", "items": [item("ES.CONFIRM", "가", -1)]}
    ).status_code in (400, 422)
    assert call(
        world, "PUT", "/codes", {"groupId": "ES", "items": [item("ES.CONFIRM", "가" * 101, 1)]}
    ).status_code in (400, 422)
