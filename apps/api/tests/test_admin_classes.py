# 관리자 강좌분류(이름 정규화·삭제 이름 재사용 금지, 연결 강좌가 있으면 중지·삭제 거절, 변경 이력, 읽은 버전)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import open_course
from tests.world import World

pytestmark = pytest.mark.db

_keys = itertools.count(1)


def create(w: World, name: str = "생활체육", sort_seq: int = 1, key: str | None = None) -> Any:
    return call(
        w,
        "POST",
        "/course-classes",
        {"name": name, "sortSeq": sort_seq},
        **{"Idempotency-Key": key or f"clsf-key-{next(_keys):06d}"},
    )


def made(w: World, name: str = "생활체육", sort_seq: int = 1) -> dict[str, Any]:
    r = create(w, name, sort_seq)
    assert r.status_code == 201, r.text
    return dict(r.json())


def edit(w: World, sn: Any, version: int, name: str = "생활체육", sort_seq: int = 1) -> Any:
    return call(w, "PUT", f"/course-classes/{sn}", {"name": name, "sortSeq": sort_seq, "version": version})


def act(w: World, sn: Any, step: str, version: int) -> Any:
    return call(w, "POST", f"/course-classes/{sn}/{step}", {"version": version})


def linked(w: World, class_sn: Any) -> dict[str, Any]:
    return open_course(w, CORS_CLSF_SN=class_sn)


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def writer(w: World) -> Any:
    who = staff(w, "boss", "AU.CORS_R", "AU.CORS_W")
    use(w, who)
    return who


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위_쓰기는_403이다(world: World) -> None:
    from tests.test_admin_access import dong  # noqa: PLC0415

    assert world.client.get("/api/admin/v1/course-classes").status_code == 401
    use(world, staff(world, "x", "AU.POST_W"))
    assert call(world, "GET", "/course-classes").status_code == 403
    assert call(world, "GET", "/course-classes/1/history").status_code == 403
    mine = dong(world, "가동")
    writes = (
        ("POST", "/course-classes", {"name": "가", "sortSeq": 1}),
        ("PUT", "/course-classes/1", {"name": "가", "sortSeq": 1, "version": 1}),
        ("POST", "/course-classes/1/deactivate", {"version": 1}),
        ("POST", "/course-classes/1/activate", {"version": 1}),
        ("DELETE", "/course-classes/1?version=1", None),
    )
    for who in (
        staff(world, "r", "AU.CORS_R"),  # 읽기만 있다
        staff(
            world, "d", "AU.CORS_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]
        ),  # 동 범위 쓰기는 묶음 설정이 아니다
    ):
        use(world, who)
        for method, path, payload in writes:
            assert (
                call(world, method, path, payload, **{"Idempotency-Key": "clsf-key-000001"}).status_code
                == 403
            ), path


def test_읽기_권한만_있으면_목록과_이력을_보지만_고칠_수_없다고_알린다(world: World) -> None:
    row = world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="체육", CLSF_NM_KEY="체육", USE_YN="Y", DEL_YN="N")
    use(world, staff(world, "r", "AU.CORS_R"))
    body = call(world, "GET", "/course-classes").json()
    assert body["canEdit"] is False and [i["name"] for i in body["items"]] == ["체육"]
    assert call(world, "GET", f"/course-classes/{row['CORS_CLSF_SN']}/history").status_code == 200


# --- 등록 ---------------------------------------------------------------------------------------


def test_등록하면_공백을_정리한_이름과_정규화키로_저장하고_이력을_남긴다(world: World) -> None:
    boss = writer(world)
    r = create(world, "  생활   체육  ", 3)
    assert r.status_code == 201
    out = r.json()
    assert (out["name"], out["sortSeq"], out["active"], out["courseCount"], out["version"]) == (
        "생활 체육",
        3,
        True,
        0,
        1,
    )
    assert (out["canDeactivate"], out["canDelete"]) == (True, True)
    [row] = rows(world, "SELECT * FROM TB_CORS_CLSF")
    assert (row["CORS_CLSF_NM"], row["CLSF_NM_KEY"], row["USE_YN"], row["DEL_YN"], row["REG_MNGR_SN"]) == (
        "생활 체육",
        "생활 체육",
        "Y",
        "N",
        boss.sn,
    )
    hist = call(world, "GET", f"/course-classes/{out['classId']}/history").json()["items"]
    assert [(h["action"], h["before"], h["after"], h["by"]) for h in hist] == [
        ("CREATE", None, "생활 체육", "김관리")
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("요가", " 요가 "),
        ("Yoga", "yoga"),
        ("Yoga", "ＹＯＧＡ"),
        ("생활 체육", "생활  체육"),
        ("ＡＢＣ ｄｅｆ", "abc DEF"),
    ],
)
def test_정규화키가_같으면_이름이_조금_달라도_중복이다(world: World, first: str, second: str) -> None:
    writer(world)
    made(world, first)
    r = create(world, second)
    assert r.status_code == 422 and "name" in r.json()["fields"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_CLSF")[0]["n"] == 1


def test_정규화키는_NFKC_공백_정리_소문자로_서버가_만든다(world: World) -> None:
    writer(world)
    made(world, "ＹＯＧＡ  Ｓｔｕｄｙ", 1)  # 전각 글자와 겹친 공백. DB 대조 규칙이 아니라 서버가 키를 만든다
    row = rows(world, "SELECT CORS_CLSF_NM n, CLSF_NM_KEY k FROM TB_CORS_CLSF")[0]
    assert (row["n"], row["k"]) == ("ＹＯＧＡ Ｓｔｕｄｙ", "yoga study")


def test_이름이_비거나_길면_절단하지_않고_거절한다(world: World) -> None:
    writer(world)
    assert "name" in create(world, "   ").json()["fields"]
    assert create(world, "").status_code in (400, 422)
    too_long = create(world, "가" * 101)
    assert too_long.status_code == 422 and "name" in too_long.json()["fields"]
    assert create(world, "가" * 100).status_code == 201  # 정확히 한도는 받는다
    assert rows(world, "SELECT CHAR_LENGTH(CORS_CLSF_NM) n FROM TB_CORS_CLSF")[0]["n"] == 100


def test_같은_키로_다시_보내면_같은_분류이고_내용이_다르면_409다(world: World) -> None:
    writer(world)
    first = create(world, "체육", 1, "same-key-0001").json()
    again = create(world, "체육", 1, "same-key-0001")
    assert again.status_code == 201 and again.json()["classId"] == first["classId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_CLSF")[0]["n"] == 1
    diff = create(world, "다른", 1, "same-key-0001")
    assert diff.status_code == 409 and diff.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/course-classes", {"name": "x", "sortSeq": 1}).status_code in (400, 422)


# --- 목록 ---------------------------------------------------------------------------------------


def test_목록은_순서대로_주고_연결_강좌_수와_할_수_있는_일과_미분류_수를_알린다(world: World) -> None:
    writer(world)
    b = made(world, "B 분류", 2)
    a = made(world, "A 분류", 1)
    linked(world, b["classId"])
    linked(world, b["classId"])
    open_course(world, CORS_NM="미분류 강좌", CORS_CLSF_SN=None)
    body = call(world, "GET", "/course-classes").json()
    assert [(i["name"], i["courseCount"], i["canDeactivate"], i["canDelete"]) for i in body["items"]] == [
        ("A 분류", 0, True, True),
        ("B 분류", 2, False, False),
    ]
    assert body["canEdit"] is True and body["uncategorizedCount"] == 1 and a["classId"]
    act(world, a["classId"], "deactivate", 1)
    inactive = call(world, "GET", "/course-classes").json()["items"][0]
    assert (inactive["active"], inactive["canDeactivate"], inactive["canDelete"]) == (False, False, True)


# --- 수정 ---------------------------------------------------------------------------------------


def test_이름과_순서를_고치면_버전이_오르고_바뀐_항목마다_이력을_남긴다(world: World) -> None:
    writer(world)
    c = made(world, "체육", 1)
    r = edit(world, c["classId"], 1, "스포츠", 5)
    assert r.status_code == 200
    out = r.json()
    assert (out["name"], out["sortSeq"], out["version"]) == ("스포츠", 5, 2)
    hist = call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"]
    assert [(h["action"], h["before"], h["after"]) for h in hist] == [
        ("REORDER", "1", "5"),
        ("RENAME", "체육", "스포츠"),
        ("CREATE", None, "체육"),
    ]
    only = edit(world, c["classId"], 2, "스포츠", 9).json()
    assert only["version"] == 3
    assert [
        h["action"] for h in call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"]
    ][0] == "REORDER"
    assert rows(world, "SELECT MDFCN_DT d FROM TB_CORS_CLSF")[0]["d"] is not None


def test_바뀐_것이_없으면_버전을_올리지_않고_이력도_남기지_않는다(world: World) -> None:
    writer(world)
    c = made(world, "체육", 1)
    r = edit(world, c["classId"], 1, "체육", 1)
    assert r.status_code == 200 and r.json()["version"] == 1
    assert len(call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"]) == 1


def test_표기만_바꾸는_수정은_이름을_바꾸고_이력을_남긴다(world: World) -> None:
    writer(world)
    c = made(world, "yoga", 1)
    r = edit(world, c["classId"], 1, "Yoga", 1)  # 정규화키는 같고 표시 이름만 다르다
    assert r.status_code == 200 and r.json()["name"] == "Yoga" and r.json()["version"] == 2
    assert (
        call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"][0]["action"] == "RENAME"
    )


def test_읽은_버전이_다르면_409이고_다른_분류의_이름과는_겹치지_않아야_한다(world: World) -> None:
    writer(world)
    a, b = made(world, "A", 1), made(world, "B", 2)
    assert edit(world, a["classId"], 1, "A2", 1).status_code == 200
    stale = edit(world, a["classId"], 1, "A3", 1)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    dup = edit(world, b["classId"], 1, " a2 ", 2)
    assert dup.status_code == 422 and "name" in dup.json()["fields"]
    assert edit(world, a["classId"], 2, "A2", 1).status_code == 200  # 자기 이름은 그대로 써도 된다


# --- 비활성·재활성 ------------------------------------------------------------------------------


def test_연결_강좌가_없으면_비활성하고_재활성할_수_있으며_이력을_남긴다(world: World) -> None:
    writer(world)
    c = made(world)
    off = act(world, c["classId"], "deactivate", 1)
    assert off.status_code == 200 and off.json()["active"] is False and off.json()["version"] == 2
    again = act(world, c["classId"], "deactivate", 2)
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"
    on = act(world, c["classId"], "activate", 2)
    assert on.status_code == 200 and on.json()["active"] is True and on.json()["version"] == 3
    assert act(world, c["classId"], "activate", 3).status_code == 409
    hist = call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"]
    assert [(h["action"], h["before"], h["after"]) for h in hist[:2]] == [
        ("ACTIVATE", "비활성", "활성"),
        ("DEACTIVATE", "활성", "비활성"),
    ]


def test_연결_강좌가_있으면_비활성을_거절하고_기존_연결은_그대로_둔다(world: World) -> None:
    writer(world)
    c = made(world)
    course = linked(world, c["classId"])
    world.db.commit()  # 오류 응답의 롤백이 준비한 행을 되돌리지 않게 고정한다
    r = act(world, c["classId"], "deactivate", 1)
    assert r.status_code == 422 and "classId" in r.json()["fields"] and "1건" in r.json()["message"]
    assert rows(world, "SELECT USE_YN u, RCRD_VER v FROM TB_CORS_CLSF")[0] == {"u": "Y", "v": 1}
    assert rows(world, "SELECT CORS_CLSF_SN s FROM TB_CORS WHERE CORS_SN=:c", c=course["CORS_SN"])[0][
        "s"
    ] == int(c["classId"])


def test_폐강한_강좌도_연결로_센다(world: World) -> None:
    writer(world)
    c = made(world)
    linked(world, c["classId"])
    world.db.execute(text("UPDATE TB_CORS SET CORS_STTS_CD='CS.CANCEL'"))
    assert act(world, c["classId"], "deactivate", 1).status_code == 422


def test_상태_작업의_버전과_없는_분류를_검사한다(world: World) -> None:
    writer(world)
    c = made(world)
    stale = act(world, c["classId"], "deactivate", 7)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    for step in ("deactivate", "activate"):
        assert act(world, "999999999", step, 1).status_code == 404
    assert call(world, "POST", f"/course-classes/{c['classId']}/deactivate", {}).status_code in (400, 422)


# --- 삭제 ---------------------------------------------------------------------------------------


def test_삭제는_논리삭제이고_이력이_남으며_삭제한_이름은_다시_쓸_수_없다(world: World) -> None:
    writer(world)
    c = made(world, "체육")
    r = call(world, "DELETE", f"/course-classes/{c['classId']}?version=1")
    assert r.status_code == 204 and r.content == b""
    row = rows(world, "SELECT DEL_YN d, DEL_DT t, CORS_CLSF_NM n, CLSF_NM_KEY k FROM TB_CORS_CLSF")[0]
    assert (row["d"], row["n"], row["k"]) == ("Y", "체육", "체육") and row[
        "t"
    ] is not None  # 행과 정규화키는 남는다
    assert call(world, "GET", "/course-classes").json()["items"] == []
    reuse = create(world, " 체육 ")
    assert reuse.status_code == 422 and "name" in reuse.json()["fields"]
    hist = call(world, "GET", f"/course-classes/{c['classId']}/history").json()[
        "items"
    ]  # 삭제한 뒤에도 이력은 본다
    assert [(h["action"], h["before"], h["after"]) for h in hist[:2]] == [
        ("DELETE", "체육", None),
        ("CREATE", None, "체육"),
    ]
    for gone in (
        call(world, "DELETE", f"/course-classes/{c['classId']}?version=2"),
        edit(world, c["classId"], 2, "다시", 1),
        act(world, c["classId"], "activate", 2),
        act(world, c["classId"], "deactivate", 2),
    ):
        assert gone.status_code == 404


def test_연결_강좌가_있거나_버전이_다르면_삭제를_거절한다(world: World) -> None:
    writer(world)
    c = made(world)
    linked(world, c["classId"])
    r = call(world, "DELETE", f"/course-classes/{c['classId']}?version=1")
    assert r.status_code == 422 and "classId" in r.json()["fields"]
    free = made(world, "빈 분류", 2)
    stale = call(world, "DELETE", f"/course-classes/{free['classId']}?version=9")
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert call(world, "DELETE", f"/course-classes/{free['classId']}").status_code in (400, 422)  # 버전 없음
    assert rows(world, "SELECT COUNT(*) n FROM TB_CORS_CLSF WHERE DEL_YN='N'")[0]["n"] == 2


# --- 이력 ---------------------------------------------------------------------------------------


def test_이력은_최근_것이_먼저이고_처리자와_시각을_담으며_없는_분류는_404다(world: World) -> None:
    writer(world)
    c = made(world, "체육")
    edit(world, c["classId"], 1, "체육2", 1)
    act(world, c["classId"], "deactivate", 2)
    hist = call(world, "GET", f"/course-classes/{c['classId']}/history").json()["items"]
    assert [h["action"] for h in hist] == ["DEACTIVATE", "RENAME", "CREATE"]
    assert all(h["by"] == "김관리" and h["at"] for h in hist)
    assert call(world, "GET", "/course-classes/999999999/history").status_code == 404
    jobs = rows(world, "SELECT DMND_ID d, TRGT_TBL_NM t FROM TB_JOB_HSTRY WHERE JOB_CD LIKE 'CLSF_%'")
    assert len(jobs) == 3 and all(
        j["t"] == "TB_CORS_CLSF" and j["d"] for j in jobs
    )  # 요청 번호가 함께 남는다


def test_이력은_그_분류의_것만_준다(world: World) -> None:
    writer(world)
    a, b = made(world, "A 분류", 1), made(world, "B 분류", 2)
    edit(world, a["classId"], 1, "A 바뀜", 1)
    hist_b = call(world, "GET", f"/course-classes/{b['classId']}/history").json()["items"]
    assert [(h["action"], h["after"]) for h in hist_b] == [("CREATE", "B 분류")]
