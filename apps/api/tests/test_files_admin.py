# 관리자 첨부파일(강좌 계획서·환불 증빙 올리기, 목록·상세·삭제·내려받기, 범위·상태·감사 기록)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.tables import TB_FILE
from app.domain.file.upload import MAX_BYTES
from tests.test_admin_access import dong
from tests.test_admin_refunds import Actor, call, refund, staff, use
from tests.test_applications_read import open_course as _open_course
from tests.world import ADMIN, START, World

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n" + "계획서".encode()
_keys = itertools.count(1)


def key() -> str:
    return f"file-{next(_keys):08d}"


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    """저장소 위치를 시험용 임시 폴더로 바꾼다."""
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def upload(w: World, path: str, name: str = "계획서.pdf", data: bytes = PDF, idem: str | None = None) -> Any:
    who: Actor = w.current  # type: ignore[attr-defined]
    return w.client.post(
        f"{ADMIN}{path}",
        files={"file": (name, data, "application/octet-stream")},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": idem or key()},
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings().all())


def files_of(w: World) -> list[Any]:
    return rows(w, "SELECT * FROM TB_FILE ORDER BY FILE_SN")


def jobs(w: World, code: str) -> list[Any]:
    return rows(w, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD=:c ORDER BY JOB_HSTRY_SN", c=code)


def put(w: World, sn: int, status: str = "FS.SAFE") -> None:
    w.db.execute(text("UPDATE TB_FILE SET FILE_STTS_CD=:s WHERE FILE_SN=:f"), {"s": status, "f": sn})


def writer(w: World, *codes: str, **kw: Any) -> Actor:
    who = staff(w, f"f{next(_keys)}", *(codes or ("AU.CORS_W",)), **kw)
    use(w, who)
    return who


# --- 강좌 계획서 올리기 --------------------------------------------------------------------------


def test_강좌에_계획서를_올리면_검사_대기로_저장하고_원본_이름은_DB에만_둔다(
    world: World, root: Path
) -> None:
    target = course(world)
    who = writer(world)
    r = upload(world, f"/courses/{target['CORS_SN']}/files", "한글 계획서.pdf")
    assert r.status_code == 201
    body = r.json()
    assert (body["fileName"], body["status"], body["sizeBytes"], body["blockReason"]) == (
        "한글 계획서.pdf",
        "PENDING",
        len(PDF),
        None,
    )
    [row] = files_of(world)
    assert (row["FILE_STTS_CD"], row["FILE_USE_CD"], row["CORS_SN"], row["MIME_TYPE_NM"]) == (
        "FS.PENDING",
        "FP.PLAN",
        target["CORS_SN"],
        "application/pdf",
    )
    assert (
        row["STRG_KEY"].startswith(f"b{world.bundle}/")
        and "계획서" not in row["STRG_KEY"]
        and ".pdf" not in row["STRG_KEY"]
    )
    assert (root / row["STRG_KEY"]).read_bytes() == PDF and len(row["FILE_HASH_VL"]) == 64
    job = jobs(world, "FILE_UPLOAD")[0]
    assert (job["ACTR_TYPE_CD"], job["MNGR_SN"], job["TRGT_KEY_VL"]) == (
        "AK.ADMIN",
        who.sn,
        str(row["FILE_SN"]),
    )


def test_권한이_없으면_올릴_수_없다_조회만_되면_403이고_아예_없으면_404다(world: World, root: Path) -> None:
    target = course(world)
    path = f"/courses/{target['CORS_SN']}/files"
    assert world.client.get(f"{ADMIN}{path}").status_code == 401
    use(world, staff(world, "reader", "AU.CORS_R"))
    assert call(world, "GET", path).status_code == 404  # 계획서 첨부는 고칠 수 있는 담당자만 본다
    assert upload(world, path).status_code == 404
    use(world, staff(world, "other", "AU.APLY_R"))
    assert upload(world, path).status_code == 404
    assert files_of(world) == [] and not list(root.rglob("*"))


def test_CSRF_토큰이_없으면_올릴_수_없다(world: World, root: Path) -> None:
    target = course(world)
    writer(world)
    r = world.client.post(
        f"{ADMIN}/courses/{target['CORS_SN']}/files",
        files={"file": ("a.pdf", PDF, "application/pdf")},
        headers={"Idempotency-Key": key()},
    )
    assert r.status_code == 403 and files_of(world) == []


def test_동_담당자는_자기_동_강좌에만_올린다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    ok = course(world, DONG_SN=mine["DONG_SN"])
    no = course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"])
    common = course(world, CORS_NM="공통")
    use(world, staff(world, "d", "AU.CORS_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert upload(world, f"/courses/{ok['CORS_SN']}/files").status_code == 201
    for target in (no, common):
        assert upload(world, f"/courses/{target['CORS_SN']}/files").status_code == 404
        assert call(world, "GET", f"/courses/{target['CORS_SN']}/files").status_code == 404
    assert len(files_of(world)) == 1


@pytest.mark.parametrize("state", ["CS.CANCEL", "CS.END"])
def test_폐강하거나_종료한_강좌는_잠겨_올릴_수_없다(world: World, root: Path, state: str) -> None:
    target = course(world, CORS_STTS_CD=state)
    writer(world)
    shown = call(world, "GET", f"/courses/{target['CORS_SN']}/files").json()
    assert shown["canEdit"] is False
    r = upload(world, f"/courses/{target['CORS_SN']}/files")
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE" and files_of(world) == []


def test_강의계획서는_한_개이고_제거한_뒤에는_다시_올릴_수_있다(world: World, root: Path) -> None:
    target = course(world)
    writer(world)
    path = f"/courses/{target['CORS_SN']}/files"
    first = upload(world, path).json()
    second = upload(world, path, "둘째.pdf")
    assert second.status_code == 422 and "먼저 기존 파일을 제거" in second.json()["message"]
    assert call(world, "DELETE", f"/files/{first['fileId']}").status_code == 204
    assert upload(world, path, "둘째.pdf").status_code == 201
    listed = call(world, "GET", path).json()
    assert [f["fileName"] for f in listed["items"]] == ["둘째.pdf"]  # 삭제한 파일은 소유 업무 목록에 없다
    assert (listed["maxFiles"], listed["maxBytes"], listed["canEdit"]) == (1, MAX_BYTES, True)
    assert "pdf" in listed["allowedExtensions"] and "exe" not in listed["allowedExtensions"]


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.exe", PDF),
        ("a.pdf", b""),
        ("a.pdf", b"<html>x"),
        ("a.png", PDF),
        ("a.pdf", PDF + b"x" * MAX_BYTES),
    ],
    ids=["확장자", "빈파일", "내용형식", "확장자와내용", "20MB초과"],
)
def test_틀린_파일은_422이고_저장소와_DB에_아무것도_남기지_않는다(
    world: World, root: Path, name: str, data: bytes
) -> None:
    target = course(world)
    writer(world)
    r = upload(world, f"/courses/{target['CORS_SN']}/files", name, data)
    assert r.status_code == 422 and r.json()["code"] == "RULE_REJECTED" and "file" in r.json()["fields"]
    assert files_of(world) == [] and not list(root.rglob("*")) and jobs(world, "FILE_UPLOAD") == []


def test_같은_키로_같은_파일을_다시_올리면_이전_결과이고_다른_파일이면_충돌이다(
    world: World, root: Path
) -> None:
    target = course(world)
    writer(world)
    path, idem = f"/courses/{target['CORS_SN']}/files", key()
    a, b = upload(world, path, idem=idem), upload(world, path, idem=idem)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["fileId"] == b.json()["fileId"]
    assert len(files_of(world)) == 1 and len([p for p in root.rglob("*") if p.is_file()]) == 1
    clash = upload(world, path, "다른.pdf", PDF + b"x", idem=idem)
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"


# --- 환불 증빙 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        ("RS.REQUEST", True),
        ("RS.HOLD", True),
        ("RS.APPROVE", False),
        ("RS.DONE", False),
        ("RS.REJECT", False),
    ],
)
def test_환불_증빙은_접수와_보류_상태에서만_올린다(
    world: World, root: Path, status: str, allowed: bool
) -> None:
    extra: dict[str, Any] = {"RFND_DT": START} if status == "RS.DONE" else {}
    target = refund(world, status=status, **extra)
    writer(world, "AU.RFND_A")
    r = upload(world, f"/refunds/{target['RFND_SN']}/files", "증빙.png", b"\x89PNG\r\n\x1a\n....")
    assert (r.status_code == 201) is allowed
    if allowed:
        assert (
            files_of(world)[0]["FILE_USE_CD"] == "FP.PROOF"
            and files_of(world)[0]["RFND_SN"] == target["RFND_SN"]
        )
    else:
        assert r.status_code == 409 and files_of(world) == []


def test_환불_증빙은_다섯_장까지이고_집행_권한만으로는_올릴_수_없다(world: World, root: Path) -> None:
    target = refund(world)
    path = f"/refunds/{target['RFND_SN']}/files"
    use(world, staff(world, "x", "AU.RFND_X"))
    assert call(world, "GET", path).status_code == 200  # 집행 담당자는 볼 수 있다
    denied = upload(world, path)
    assert denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"
    writer(world, "AU.RFND_A")
    for n in range(5):
        assert upload(world, path, f"증빙{n}.pdf", PDF + bytes([n])).status_code == 201
    sixth = upload(world, path, "증빙5.pdf", PDF + b"5")
    assert sixth.status_code == 422 and "5개까지" in sixth.json()["message"]
    assert [f["fileName"] for f in call(world, "GET", path).json()["items"]] == [
        f"증빙{n}.pdf" for n in range(5)
    ]


def test_동_담당자는_범위_밖_환불의_증빙을_볼_수도_올릴_수도_없다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    own = refund(world, row=course(world, DONG_SN=mine["DONG_SN"]))
    foreign = refund(world, row=course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))
    use(world, staff(world, "d", "AU.RFND_A", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert upload(world, f"/refunds/{own['RFND_SN']}/files").status_code == 201
    assert upload(world, f"/refunds/{foreign['RFND_SN']}/files").status_code == 404
    assert call(world, "GET", f"/refunds/{foreign['RFND_SN']}/files").status_code == 404


# --- 전체 목록·상세 -----------------------------------------------------------------------------


def seed(w: World) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    """강좌 계획서 한 개와 환불 증빙 한 개를 올린 상태."""
    c, r = course(w), refund(w)
    writer(w, "AU.CORS_W", "AU.RFND_A")
    plan = upload(w, f"/courses/{c['CORS_SN']}/files", "계획서.pdf").json()
    proof = upload(w, f"/refunds/{r['RFND_SN']}/files", "증빙.pdf").json()
    return c, r, int(plan["fileId"]), int(proof["fileId"])


def test_전체_목록은_소유_업무를_보여_주고_권한이_있는_종류만_나온다(world: World, root: Path) -> None:
    c, r, plan, proof = seed(world)
    items = call(world, "GET", "/files").json()["items"]
    assert [(i["ownerKind"], i["ownerLabel"], i["fileName"], i["status"]) for i in items] == [
        ("REFUND", f"환불 {r['RFND_SN']}", "증빙.pdf", "PENDING"),
        ("COURSE", "요가", "계획서.pdf", "PENDING"),
    ]
    use(world, staff(world, "course-only", "AU.CORS_W"))
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [str(plan)]
    use(world, staff(world, "refund-x", "AU.RFND_X"))
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [str(proof)]
    use(world, staff(world, "nothing", "AU.APLY_R"))
    assert call(world, "GET", "/files").status_code == 403
    assert c and r


def test_전체_목록은_동_범위를_따르고_조건으로_거른다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    own, foreign = (
        course(world, DONG_SN=mine["DONG_SN"]),
        course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]),
    )
    writer(world, "AU.CORS_W")
    ids = {}
    for label, target in (("own", own), ("foreign", foreign)):
        ids[label] = int(
            upload(world, f"/courses/{target['CORS_SN']}/files", f"{label}%.pdf").json()["fileId"]
        )
    use(world, staff(world, "d", "AU.CORS_W", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [str(ids["own"])]
    use(world, staff(world, "all", "AU.CORS_W"))
    assert call(world, "GET", "/files").json()["total"] == 2
    assert [i["fileId"] for i in call(world, "GET", "/files?q=foreign").json()["items"]] == [
        str(ids["foreign"])
    ]
    assert call(world, "GET", "/files?q=_").json()["items"] == []  # 와일드카드(_)는 글자로만 찾는다
    assert len(call(world, "GET", "/files?q=%25").json()["items"]) == 2  # 이름에 있는 %는 글자로 찾는다
    assert call(world, "GET", "/files?ownerKind=REFUND").json()["items"] == []
    assert call(world, "GET", "/files?ownerKind=POST").json()["items"] == []  # 아직 구현되지 않은 소유 업무
    put(world, ids["own"], "FS.SAFE")
    assert [i["fileId"] for i in call(world, "GET", "/files?status=SAFE").json()["items"]] == [
        str(ids["own"])
    ]
    assert call(world, "GET", "/files?size=1&page=2").json()["items"][0]["fileId"] == str(ids["own"])


def test_환불_증빙도_전체_목록에서_동_범위를_따른다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    own = refund(world, row=course(world, DONG_SN=mine["DONG_SN"]))
    foreign = refund(world, row=course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))
    writer(world, "AU.RFND_A")
    ids = {
        name: int(upload(world, f"/refunds/{r['RFND_SN']}/files", f"{name}.pdf").json()["fileId"])
        for name, r in (("own", own), ("foreign", foreign))
    }
    use(world, staff(world, "d", "AU.RFND_A", kind="SK.DONG", dong_sn=mine["DONG_SN"]))
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [str(ids["own"])]
    assert call(world, "GET", f"/files/{ids['foreign']}").status_code == 404


def test_DB에_기록하지_못하면_저장한_파일을_치우고_500이다(
    world: World, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = course(world)
    writer(world)

    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError("DB 오류")

    monkeypatch.setattr(TB_FILE, "insert", broken)
    world.db.commit()
    r = upload(world, f"/courses/{target['CORS_SN']}/files")
    assert r.status_code == 500
    assert [p for p in root.rglob("*") if p.is_file()] == []  # 고아 파일을 남기지 않는다


def test_삭제한_파일은_상태로_고를_때만_목록에_나온다(world: World, root: Path) -> None:
    _, _, plan, proof = seed(world)
    assert call(world, "DELETE", f"/files/{plan}").status_code == 204
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [
        str(proof)
    ]  # 삭제한 파일은 빠진다
    assert [i["fileId"] for i in call(world, "GET", "/files?status=DELETE").json()["items"]] == [str(plan)]
    assert call(world, "GET", f"/files/{plan}").status_code == 404


def test_상세는_용도와_해시_앞부분과_내려받기_기록을_준다(world: World, root: Path) -> None:
    _, _, plan, _ = seed(world)
    put(world, plan)
    assert call(world, "GET", f"/files/{plan}/download").status_code == 200
    body = call(world, "GET", f"/files/{plan}").json()
    row = rows(world, "SELECT FILE_HASH_VL h FROM TB_FILE WHERE FILE_SN=:f", f=plan)[0]
    assert (body["purpose"], body["mimeType"], body["hashPrefix"], body["blockReason"]) == (
        "PLAN",
        "application/pdf",
        row["h"][:8],
        None,
    )
    assert [(d["by"], d["byAdmin"]) for d in body["downloads"]] == [("김관리", True)]
    assert body["ownerKind"] == "COURSE" and body["registeredOn"] == "2026-11-09"


def test_볼_수_없는_파일은_404이고_시도가_기록된다(world: World, root: Path) -> None:
    _, _, plan, proof = seed(world)
    use(world, staff(world, "intruder", "AU.RFND_X"))
    r = call(world, "GET", f"/files/{plan}")  # 강좌 계획서는 환불 집행 담당자의 범위 밖이다
    assert r.status_code == 404 and call(world, "GET", "/files/99999999").status_code == 404
    denied = jobs(world, "FILE_DOWNLOAD")
    assert [(d["JOB_RSLT_CD"], d["TRGT_KEY_VL"]) for d in denied] == [
        ("JR.DENY", str(plan))
    ]  # 없는 파일은 기록하지 않는다
    assert proof


# --- 삭제 ---------------------------------------------------------------------------------------


def test_삭제는_논리삭제이고_저장소_파일은_남기며_이력을_남긴다(world: World, root: Path) -> None:
    _, _, plan, _ = seed(world)
    key_ = rows(world, "SELECT STRG_KEY k FROM TB_FILE WHERE FILE_SN=:f", f=plan)[0]["k"]
    assert call(world, "DELETE", f"/files/{plan}").status_code == 204
    row = rows(world, "SELECT FILE_STTS_CD s, MDFCN_DT m FROM TB_FILE WHERE FILE_SN=:f", f=plan)[0]
    assert (row["s"], row["m"]) == ("FS.DELETE", START)
    assert (root / key_).exists()  # 물리 삭제는 보존기간 뒤에 한다
    assert jobs(world, "FILE_DELETE")[0]["TRGT_KEY_VL"] == str(plan)
    assert call(world, "DELETE", f"/files/{plan}").status_code == 404  # 이미 삭제했다


def test_소유_업무가_잠겼거나_권한이_없으면_삭제할_수_없다(world: World, root: Path) -> None:
    c, r, plan, proof = seed(world)
    world.db.execute(
        text("UPDATE TB_CORS SET CORS_STTS_CD='CS.CANCEL' WHERE CORS_SN=:c"), {"c": c["CORS_SN"]}
    )
    locked = call(world, "DELETE", f"/files/{plan}")
    assert locked.status_code == 409 and locked.json()["code"] == "CONFLICT_STATE"
    use(world, staff(world, "x", "AU.RFND_X"))
    forbidden = call(world, "DELETE", f"/files/{proof}")
    assert forbidden.status_code == 403
    assert [f["FILE_STTS_CD"] for f in files_of(world)] == ["FS.PENDING", "FS.PENDING"]


# --- 내려받기 -----------------------------------------------------------------------------------


def test_검사를_통과한_파일만_내려주고_안전한_헤더와_감사를_남긴다(world: World, root: Path) -> None:
    _, _, plan, _ = seed(world)
    pending = call(world, "GET", f"/files/{plan}/download")
    assert pending.status_code == 404  # 검사 대기는 내려주지 않는다
    put(world, plan)
    r = call(world, "GET", f"/files/{plan}/download")
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;") and "%EA%B3%84%ED%9A%8D%EC%84%9C.pdf" in disposition
    assert (
        r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "private, no-store"
    )
    logged = [(d["JOB_RSLT_CD"], d["CHG_CN"]) for d in jobs(world, "FILE_DOWNLOAD")]
    assert logged == [
        ("JR.DENY", "권한 없는 파일 접근"),
        ("JR.SUCCESS", "관리자 내려받기"),
    ]  # 거절 시도와 허용 모두


@pytest.mark.parametrize("status", ["FS.PENDING", "FS.BLOCK", "FS.DELETE"])
def test_검사_대기_차단_삭제_파일은_내려주지_않는다(world: World, root: Path, status: str) -> None:
    _, _, plan, _ = seed(world)
    put(world, plan, status)
    assert call(world, "GET", f"/files/{plan}/download").status_code == 404


def test_권한이_없으면_내려받을_수_없다(world: World, root: Path) -> None:
    _, _, plan, _ = seed(world)
    put(world, plan)
    use(world, staff(world, "x", "AU.RFND_X"))
    r = call(world, "GET", f"/files/{plan}/download")
    assert r.status_code == 404 and b"%PDF" not in r.content
    assert [d["JOB_RSLT_CD"] for d in jobs(world, "FILE_DOWNLOAD")] == ["JR.DENY"]


def test_저장소에서_사라진_파일과_밖을_가리키는_키는_500이고_경로를_알리지_않는다(
    world: World, root: Path
) -> None:
    _, _, plan, proof = seed(world)
    put(world, plan)
    put(world, proof)
    for sn in (plan, proof):
        stored = rows(world, "SELECT STRG_KEY k FROM TB_FILE WHERE FILE_SN=:f", f=sn)[0]["k"]
        (root / stored).unlink()
    world.db.execute(text("UPDATE TB_FILE SET STRG_KEY='../../outside' WHERE FILE_SN=:f"), {"f": proof})
    world.db.commit()  # 첫 500 응답의 롤백이 위 준비 변경까지 되돌리지 않게 고정한다
    for sn in (plan, proof):
        r = call(world, "GET", f"/files/{sn}/download")
        assert r.status_code == 500 and str(root) not in r.text and "outside" not in r.text
