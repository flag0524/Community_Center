# 관리자 약관·동의문 버전(AU.SITE_W, 검토→확정→게시, 해시 고정, 이전 게시 버전 종료, 공개 화면 반영)을 실제 앱과 MariaDB로 확인하는 시험
import hashlib
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_access import dong
from tests.test_admin_applications import member
from tests.test_admin_refunds import call, staff, use
from tests.world import MEMBER, START, World

pytestmark = pytest.mark.db

_keys = itertools.count(1)
TERMS = "TERMS_OF_USE"


def draft(
    w: World,
    kind: str = TERMS,
    name: str = "v1",
    effective: str = "2026-11-01",
    body: str | None = "<p>약관 본문</p>",
    **values: Any,
) -> Any:
    payload = {"versionName": name, "effectiveOn": effective, "essential": True, "body": body, **values}
    return call(
        w, "POST", f"/terms/{kind}/versions", payload, **{"Idempotency-Key": f"term-key-{next(_keys):06d}"}
    )


def act(w: World, sn: Any, step: str, version: int) -> Any:
    return call(w, "POST", f"/terms/versions/{sn}/{step}", {"version": version})


def posted(
    w: World, kind: str = TERMS, name: str = "v1", effective: str = "2026-11-01", **values: Any
) -> dict[str, Any]:
    """검토→확정→게시까지 마친 버전."""
    made = draft(w, kind, name, effective, **values).json()
    fixed = act(w, made["versionId"], "fix", made["version"]).json()
    return dict(act(w, fixed["versionId"], "publish", fixed["version"]).json())


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def public(w: World, kind: str = TERMS) -> Any:
    return w.client.get(f"{MEMBER}/terms/{kind}")


# --- 권한 ---------------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_권한이_없거나_동_범위뿐이면_403이다(world: World) -> None:
    assert world.client.get("/api/admin/v1/terms").status_code == 401
    mine = dong(world, "가동")
    calls = (
        ("GET", "/terms", None),
        ("GET", "/terms/versions/1", None),
        (
            "POST",
            f"/terms/{TERMS}/versions",
            {"versionName": "v1", "effectiveOn": "2026-11-01", "essential": True, "body": "x"},
        ),
        (
            "PUT",
            "/terms/versions/1",
            {"versionName": "v1", "effectiveOn": "2026-11-01", "essential": True, "body": "x", "version": 1},
        ),
        ("POST", "/terms/versions/1/fix", {"version": 1}),
        ("POST", "/terms/versions/1/publish", {"version": 1}),
    )
    for who in (
        staff(world, "x", "AU.POST_W"),
        staff(world, "d", "AU.SITE_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]),
    ):
        use(world, who)
        for method, path, payload in calls:
            assert (
                call(world, method, path, payload, **{"Idempotency-Key": "term-key-000001"}).status_code
                == 403
            ), path


# --- 새 버전 ------------------------------------------------------------------------------------


def test_새_버전은_검토_상태로_만들고_본문을_정리하며_공통_문안으로_남긴다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    r = draft(
        world, TERMS, " v1 ", "2026-12-01", '<p onclick="x()">약관</p><script>x</script>', essential=False
    )
    assert r.status_code == 201
    out = r.json()
    assert (out["termType"], out["versionName"], out["effectiveOn"], out["essential"], out["status"]) == (
        TERMS,
        "v1",
        "2026-12-01",
        False,
        "REVIEW",
    )
    assert (out["body"], out["contentHash"], out["version"], out["postedOn"], out["agreedCount"]) == (
        "<p>약관</p>",
        None,
        1,
        None,
        0,
    )
    assert (out["canEdit"], out["canFix"], out["canPublish"]) == (True, True, False)
    [row] = rows(world, "SELECT * FROM TB_SITE_CONTS")
    assert (
        row["CONTS_TYPE_CD"],
        row["CONTS_ID"],
        row["DONG_SN"],
        row["PSTG_YN"],
        row["CONTS_HASH_VL"],
        row["CONTS_TTL"],
    ) == (
        "CT.TERMS",
        TERMS,
        None,
        "N",
        None,
        "이용약관",
    )
    assert row["PSTG_BGNG_DT"].isoformat() == "2026-11-30T15:00:00"  # 한국 시각 12월 1일 0시
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_CREATE'")
    assert job["m"] == boss.sn and job["c"].startswith(f"{TERMS} v1 [idem ")


@pytest.mark.parametrize(
    ("kind", "code"), [("MARKETING_CONSENT", "CT.MARKET"), ("PRIVACY_CONSENT", "CT.PRIVACY")]
)
def test_세_종류_모두_저장할_수_있다(world: World, kind: str, code: str) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    assert draft(world, kind).status_code == 201
    assert rows(world, "SELECT CONTS_TYPE_CD c, CONTS_ID i FROM TB_SITE_CONTS")[0] == {"c": code, "i": kind}


@pytest.mark.parametrize("kind", ["PRIVACY_POLICY", "EMAIL_REFUSAL"])
def test_저장_코드가_없는_종류는_거절하고_목록은_비어_있다(world: World, kind: str) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    r = draft(world, kind)
    assert r.status_code == 422 and "termType" in r.json()["fields"] and "R16" in r.json()["message"]
    assert call(world, "GET", f"/terms?type={kind}").json()["items"] == []
    assert rows(world, "SELECT COUNT(*) n FROM TB_SITE_CONTS")[0]["n"] == 0
    assert draft(world, "NOPE").status_code in (400, 422)


def test_이전_버전을_복제해_시작하고_본문이_없고_원본도_없으면_거절한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    base = draft(world, TERMS, "v1", body="<p>원본</p>").json()
    cloned = draft(world, TERMS, "v2", "2026-12-01", None, baseVersionId=base["versionId"])
    assert cloned.status_code == 201 and cloned.json()["body"] == "<p>원본</p>"
    blank = draft(world, TERMS, "v3", body="   ", baseVersionId=base["versionId"])
    assert blank.status_code == 201 and blank.json()["body"] == "<p>원본</p>"
    own = draft(world, TERMS, "v4", body="<p>새 본문</p>", baseVersionId=base["versionId"])
    assert own.json()["body"] == "<p>새 본문</p>"  # 본문을 주면 복제하지 않는다
    none = draft(world, TERMS, "v5", body=None)
    assert none.status_code == 422 and "body" in none.json()["fields"]
    wrong = draft(
        world, "MARKETING_CONSENT", "m1", body=None, baseVersionId=base["versionId"]
    )  # 다른 종류는 원본이 아니다
    assert wrong.status_code == 422 and "baseVersionId" in wrong.json()["fields"]
    missing = draft(world, TERMS, "v6", body=None, baseVersionId="999999999")
    assert missing.status_code == 422


def test_문안에_읽을_글자가_없거나_버전_이름이_비면_거절한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    assert "body" in draft(world, TERMS, "v1", body="<script>x</script>").json()["fields"]
    assert "versionName" in draft(world, TERMS, "   ").json()["fields"]
    assert draft(world, TERMS, "").status_code in (400, 422)
    assert draft(world, TERMS, "v" * 41).status_code in (400, 422)
    assert rows(world, "SELECT COUNT(*) n FROM TB_SITE_CONTS")[0]["n"] == 0


def test_버전_이름은_종류_안에서만_겹치지_않는다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    assert draft(world, TERMS, "v1").status_code == 201
    dup = draft(world, TERMS, "v1")
    assert dup.status_code == 422 and "versionName" in dup.json()["fields"]
    assert draft(world, "MARKETING_CONSENT", "v1").status_code == 201


def test_같은_키로_다시_보내면_같은_버전이고_내용이_다르면_409다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    payload = {"versionName": "v1", "effectiveOn": "2026-11-01", "essential": True, "body": "<p>본문</p>"}

    def send(b: dict[str, Any], k: str) -> Any:
        return call(world, "POST", f"/terms/{TERMS}/versions", b, **{"Idempotency-Key": k})

    first = send(payload, "same-key-0001").json()
    again = send(payload, "same-key-0001")
    assert again.status_code == 201 and again.json()["versionId"] == first["versionId"]
    assert rows(world, "SELECT COUNT(*) n FROM TB_SITE_CONTS")[0]["n"] == 1
    assert send({**payload, "body": "<p>다른</p>"}, "same-key-0001").status_code == 409
    other_type = call(
        world, "POST", "/terms/MARKETING_CONSENT/versions", payload, **{"Idempotency-Key": "same-key-0001"}
    )
    assert other_type.status_code == 409  # 같은 키로 종류가 다르면 다른 요청이다


# --- 상태·목록 ----------------------------------------------------------------------------------


def test_목록은_시행일이_늦은_것이_먼저이고_상태와_게시일과_동의_수를_준다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    first = posted(world, TERMS, "v1", "2026-10-01")
    second = posted(world, TERMS, "v2", "2026-11-05")  # 이미 시행일이 지나 v1은 바로 물러난다
    review = draft(world, TERMS, "v3", "2026-12-01").json()
    fixed = draft(world, TERMS, "v4", "2026-11-20").json()
    act(world, fixed["versionId"], "fix", 1)
    people = [member(world, f"가{n}") for n in range(3)]
    for p in people[:2]:
        world.factory.make(
            "TB_MBR_AGRE_HSTRY",
            MBR_SN=p["MBR_SN"],
            SITE_CONTS_SN=int(second["versionId"]),
            AGRE_ACT_CD="AA.AGREE",
            CONTS_HASH_VL="a" * 64,
        )
    world.factory.make(
        "TB_MBR_AGRE_HSTRY",
        MBR_SN=people[0]["MBR_SN"],
        SITE_CONTS_SN=int(second["versionId"]),
        AGRE_ACT_CD="AA.AGREE",
        CONTS_HASH_VL="a" * 64,
    )  # 같은 회원의 중복은 한 명이다
    world.factory.make(
        "TB_MBR_AGRE_HSTRY",
        MBR_SN=people[2]["MBR_SN"],
        SITE_CONTS_SN=int(second["versionId"]),
        AGRE_ACT_CD="AA.REVOKE",
        CONTS_HASH_VL="a" * 64,
    )  # 철회만 한 회원은 세지 않는다
    body = call(world, "GET", "/terms").json()
    assert [(i["versionName"], i["status"]) for i in body["items"]] == [
        ("v3", "REVIEW"),
        ("v4", "FIXED"),
        ("v2", "PUBLISHED"),
        ("v1", "ENDED"),
    ]
    by = {i["versionName"]: i for i in body["items"]}
    assert by["v2"]["agreedCount"] == 2 and by["v1"]["agreedCount"] == 0 and by["v3"]["agreedCount"] == 0
    assert (
        by["v2"]["postedOn"] == "2026-11-09"
        and by["v1"]["postedOn"] == "2026-11-09"
        and by["v3"]["postedOn"] is None
    )
    assert first["versionId"] and review["versionId"]
    assert [
        i["versionName"] for i in call(world, "GET", f"/terms?type={TERMS}&size=2&page=2").json()["items"]
    ] == ["v2", "v1"]
    assert call(world, "GET", "/terms?type=MARKETING_CONSENT").json()["items"] == []


def test_상세는_본문과_해시와_할_수_있는_일을_상태에_맞게_준다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    made = draft(world, TERMS, "v1", body="<p>약관</p>").json()
    sn = made["versionId"]
    assert call(world, "GET", f"/terms/versions/{sn}").json()["canFix"] is True
    fixed = act(world, sn, "fix", 1).json()
    assert (fixed["status"], fixed["canEdit"], fixed["canFix"], fixed["canPublish"], fixed["version"]) == (
        "FIXED",
        False,
        False,
        True,
        2,
    )
    assert fixed["contentHash"] == hashlib.sha256("<p>약관</p>".encode()).hexdigest()
    done = act(world, sn, "publish", 2).json()
    assert (done["status"], done["canEdit"], done["canFix"], done["canPublish"]) == (
        "PUBLISHED",
        False,
        False,
        False,
    )
    assert call(world, "GET", "/terms/versions/999999999").status_code == 404
    assert call(world, "GET", "/terms/versions/abc").status_code in (400, 422)


def test_약관이_아닌_콘텐츠와_다른_묶음의_행은_404다(world: World) -> None:
    from tests.test_site_public import publish  # noqa: PLC0415

    banner = publish(world, "CT.BANNER", "banner-1", "배너")
    foreign = int(world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"])
    other = world.factory.make(
        "TB_SITE_CONTS",
        OPER_BNDL_SN=foreign,
        CONTS_TYPE_CD="CT.TERMS",
        CONTS_ID=TERMS,
        CONTS_TTL="타",
        CONTS_CN="x",
        VER_NM="v1",
        PSTG_YN="Y",
    )
    use(world, staff(world, "boss", "AU.SITE_W"))
    for sn in (banner["SITE_CONTS_SN"], other["SITE_CONTS_SN"]):
        assert call(world, "GET", f"/terms/versions/{sn}").status_code == 404
        assert act(world, sn, "fix", 1).status_code == 404
    assert call(world, "GET", "/terms").json()["total"] == 0


# --- 수정 ---------------------------------------------------------------------------------------


def edit(w: World, sn: Any, version: int, **values: Any) -> Any:
    payload = {
        "versionName": "v1",
        "effectiveOn": "2026-11-01",
        "essential": True,
        "body": "<p>고침</p>",
        "version": version,
        **values,
    }
    return call(w, "PUT", f"/terms/versions/{sn}", payload)


def test_검토_상태는_고칠_수_있고_버전이_오르며_본문을_다시_정리한다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    made = draft(world, TERMS, "v1").json()
    r = edit(
        world,
        made["versionId"],
        1,
        versionName="v1-고침",
        effectiveOn="2026-12-05",
        essential=False,
        body="<b>고침</b><script>x</script>",
    )
    assert r.status_code == 200
    out = r.json()
    assert (
        out["versionName"],
        out["effectiveOn"],
        out["essential"],
        out["body"],
        out["version"],
        out["status"],
    ) == (
        "v1-고침",
        "2026-12-05",
        False,
        "<b>고침</b>",
        2,
        "REVIEW",
    )
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_UPDATE'")
    assert (job["m"], job["c"]) == (boss.sn, f"{TERMS} v1-고침 수정")


def test_읽은_버전이_다르면_409이고_이름은_자기를_뺀_나머지와_겹치지_않는다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    a = draft(world, TERMS, "v1").json()
    b = draft(world, TERMS, "v2").json()
    assert edit(world, a["versionId"], 1).status_code == 200  # 자기 이름은 그대로 써도 된다
    stale = edit(world, a["versionId"], 1)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    dup = edit(world, b["versionId"], 1, versionName="v1")
    assert dup.status_code == 422 and "versionName" in dup.json()["fields"]
    assert (
        "body" in edit(world, b["versionId"], 1, versionName="v2", body="<script>x</script>").json()["fields"]
    )


def test_확정하거나_게시한_버전은_고칠_수_없다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    made = draft(world, TERMS, "v1").json()
    sn = made["versionId"]
    act(world, sn, "fix", 1)
    for version in (1, 2):
        r = edit(world, sn, version)
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    act(world, sn, "publish", 2)
    assert edit(world, sn, 3).status_code == 409
    assert rows(world, "SELECT CONTS_CN c FROM TB_SITE_CONTS")[0]["c"] == "<p>약관 본문</p>"


# --- 확정·게시 ----------------------------------------------------------------------------------


def test_확정하면_해시가_고정되고_다시_확정할_수_없다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    made = draft(world, TERMS, "v1", body="<p>약관</p>").json()
    stale = act(world, made["versionId"], "fix", 5)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert rows(world, "SELECT CONTS_HASH_VL h FROM TB_SITE_CONTS")[0]["h"] is None
    assert act(world, made["versionId"], "fix", 1).status_code == 200
    digest = hashlib.sha256("<p>약관</p>".encode()).hexdigest()
    assert rows(world, "SELECT CONTS_HASH_VL h FROM TB_SITE_CONTS")[0]["h"] == digest
    again = act(world, made["versionId"], "fix", 2)
    assert again.status_code == 409 and again.json()["code"] == "CONFLICT_STATE"
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_FIX'")
    assert (job["m"], job["c"]) == (boss.sn, f"{TERMS} v1 확정 {digest[:8]}")


def test_확정하지_않은_버전은_게시할_수_없다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    made = draft(world, TERMS, "v1").json()
    r = act(world, made["versionId"], "publish", 1)
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert public(world).status_code == 404


def test_게시하면_공개_화면에_나오고_읽은_버전이_다르면_409다(world: World) -> None:
    boss = staff(world, "boss", "AU.SITE_W")
    use(world, boss)
    made = draft(world, TERMS, "v1", "2026-11-01", "<p>공개 약관</p>").json()
    fixed = act(world, made["versionId"], "fix", 1).json()
    assert public(world).status_code == 404  # 확정만으로는 보이지 않는다
    stale = act(world, made["versionId"], "publish", 1)
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    done = act(world, made["versionId"], "publish", fixed["version"])
    assert (
        done.status_code == 200
        and done.json()["status"] == "PUBLISHED"
        and done.json()["postedOn"] == "2026-11-09"
    )
    pub = public(world).json()
    assert (pub["version"], pub["title"], pub["body"], pub["effectiveOn"]) == (
        "v1",
        "이용약관",
        "<p>공개 약관</p>",
        "2026-11-01",
    )
    [job] = rows(
        world, "SELECT MNGR_SN m, TRGT_KEY_VL k, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_PUBLISH'"
    )
    assert (job["m"], job["k"], job["c"]) == (boss.sn, made["versionId"], f"{TERMS} v1 게시(종료 없음)")
    assert (
        act(world, made["versionId"], "publish", done.json()["version"]).status_code == 409
    )  # 다시 게시할 수 없다


def test_새_버전을_게시하면_이전_게시_버전은_종료되고_공개_화면은_새_버전이다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    old = posted(world, TERMS, "v1", "2026-10-01")
    new = posted(world, TERMS, "v2", "2026-11-05", body="<p>새 약관</p>")
    assert (old["status"], new["status"]) == ("PUBLISHED", "PUBLISHED")
    assert call(world, "GET", f"/terms/versions/{old['versionId']}").json()["status"] == "ENDED"
    assert public(world).json()["version"] == "v2"
    ended = rows(
        world,
        "SELECT PSTG_END_DT e, PSTG_BGNG_DT b, RCRD_VER v FROM TB_SITE_CONTS WHERE SITE_CONTS_SN=:s",
        s=old["versionId"],
    )[0]
    new_begin = rows(
        world, "SELECT PSTG_BGNG_DT b FROM TB_SITE_CONTS WHERE SITE_CONTS_SN=:s", s=new["versionId"]
    )[0]["b"]
    assert ended["e"] == new_begin and int(ended["v"]) == 4
    [job] = rows(
        world,
        "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_PUBLISH' AND TRGT_KEY_VL=:k",
        k=new["versionId"],
    )
    assert job["c"] == f"{TERMS} v2 게시(종료 {old['versionId']})"


def test_시행일이_미래인_새_버전을_게시해도_그날까지는_이전_버전이_보인다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    old = posted(world, TERMS, "v1", "2026-10-01")
    new = posted(world, TERMS, "v2", "2026-12-01", body="<p>12월 약관</p>")
    assert (
        call(world, "GET", f"/terms/versions/{old['versionId']}").json()["status"] == "PUBLISHED"
    )  # 아직 시행 전이다
    assert public(world).json()["version"] == "v1"
    assert new["status"] == "PUBLISHED"


def test_시행일이_지금_게시_중인_버전보다_앞서거나_같으면_게시를_거절한다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    old = posted(world, TERMS, "v1", "2026-11-05")
    for n, effective in enumerate(["2026-11-05", "2026-11-01"]):
        made = draft(world, TERMS, f"w{n}", effective).json()
        fixed = act(world, made["versionId"], "fix", 1).json()
        r = act(world, made["versionId"], "publish", fixed["version"])
        assert r.status_code == 422 and "effectiveOn" in r.json()["fields"], effective
        assert call(world, "GET", f"/terms/versions/{made['versionId']}").json()["status"] == "FIXED"
    assert call(world, "GET", f"/terms/versions/{old['versionId']}").json()["status"] == "PUBLISHED"
    assert public(world).json()["version"] == "v1"


def test_종류가_다르면_서로_영향을_주지_않는다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    terms = posted(world, TERMS, "v1", "2026-11-05")
    posted(world, "MARKETING_CONSENT", "v1", "2026-10-01")
    assert call(world, "GET", f"/terms/versions/{terms['versionId']}").json()["status"] == "PUBLISHED"
    assert public(world).status_code == 200 and public(world, "MARKETING_CONSENT").status_code == 200


def test_종료_시각이_지금과_같으면_이미_종료로_본다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    row = world.factory.make(
        "TB_SITE_CONTS",
        OPER_BNDL_SN=world.bundle,
        CONTS_TYPE_CD="CT.TERMS",
        CONTS_ID=TERMS,
        CONTS_TTL="이용약관",
        CONTS_CN="x",
        VER_NM="v0",
        CONTS_HASH_VL="a" * 64,
        PSTG_YN="Y",
        PSTG_BGNG_DT=START - timedelta(days=30),
        PSTG_END_DT=START,
    )
    assert call(world, "GET", f"/terms/versions/{row['SITE_CONTS_SN']}").json()["status"] == "ENDED"


def test_이미_종료된_버전은_다음_게시에서_다시_건드리지_않는다(world: World) -> None:
    use(world, staff(world, "boss", "AU.SITE_W"))
    first = posted(world, TERMS, "v1", "2026-10-01")
    second = posted(world, TERMS, "v2", "2026-11-05")
    third = posted(world, TERMS, "v3", "2026-11-08")
    sql = "SELECT PSTG_END_DT e, RCRD_VER v FROM TB_SITE_CONTS WHERE SITE_CONTS_SN=:s"
    ended = rows(world, sql, s=first["versionId"])[0]
    begin2 = rows(
        world, "SELECT PSTG_BGNG_DT b FROM TB_SITE_CONTS WHERE SITE_CONTS_SN=:s", s=second["versionId"]
    )[0]["b"]
    assert ended["e"] == begin2 and int(ended["v"]) == 4  # 첫 종료 때 그대로다
    sql = "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='TERM_PUBLISH' AND TRGT_KEY_VL=:k"
    [job] = rows(world, sql, k=third["versionId"])
    assert job["c"] == f"{TERMS} v3 게시(종료 {second['versionId']})"
