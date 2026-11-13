# 주민 쪽 문의 첨부(올리기·목록·삭제·내려받기, 답변 뒤 잠김, 본인 파일만, 관리자와 이어지는 흐름)를 실제 앱과 MariaDB로 확인하는 시험
import itertools
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.test_admin_refunds import call, staff, use
from tests.test_board_public import board
from tests.test_files_admin import PDF, files_of, put
from tests.test_files_admin import root as root  # 저장소를 임시 폴더로 바꾸는 픽스처
from tests.test_member_inquiries import answered, as_member, asked, category, csrf, person
from tests.world import MEMBER, World

pytestmark = pytest.mark.db

_keys = itertools.count(1)


@pytest.fixture
def qna(world: World) -> dict[str, Any]:
    return board(world, "qna", MBR_WRT_YN="Y", ANS_USE_YN="Y", ATCH_USE_YN="Y")


def inquiry_of(w: World, qna: dict[str, Any], who: dict[str, Any], **values: Any) -> dict[str, Any]:
    category(w) if not w.db.execute(
        text("SELECT 1 FROM TB_COM_CD WHERE COM_CD='IQ.COURSE'")
    ).first() else None
    return asked(w, qna, who, "문의", INQRY_CLSF_CD="IQ.COURSE", **values)


def up(w: World, post_sn: Any, name: str = "증빙.pdf", data: bytes = PDF, idem: str | None = None) -> Any:
    headers = {**csrf(w), "Idempotency-Key": idem or f"mfile-{next(_keys):08d}"}
    return w.client.post(
        f"{MEMBER}/me/inquiries/{post_sn}/files",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


def jobs(w: World, code: str) -> list[Any]:
    return rows(w, "SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD=:c ORDER BY JOB_HSTRY_SN", c=code)


# --- 올리기·목록 --------------------------------------------------------------------------------


def test_로그인이_없으면_모두_401이다(world: World, qna: dict[str, Any]) -> None:
    for method, path in (
        ("GET", "/me/inquiries/1/files"),
        ("POST", "/me/inquiries/1/files"),
        ("DELETE", "/me/files/1"),
        ("GET", "/me/files/1"),
    ):
        assert world.client.request(method, f"{MEMBER}{path}").status_code == 401, path


def test_내_문의에_올리면_검사_대기로_저장하고_목록에_한도를_알린다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    r = up(world, target["PST_SN"], "내 증빙.pdf")
    assert r.status_code == 201
    out = r.json()
    assert (out["fileName"], out["status"], out["sizeBytes"], out["blockReason"]) == (
        "내 증빙.pdf",
        "PENDING",
        len(PDF),
        None,
    )
    [row] = files_of(world)
    assert (row["PST_SN"], row["FILE_USE_CD"], row["FILE_STTS_CD"], row["MIME_TYPE_NM"]) == (
        target["PST_SN"],
        "FP.ATTACH",
        "FS.PENDING",
        "application/pdf",
    )
    assert (root / row["STRG_KEY"]).read_bytes() == PDF and ".pdf" not in row["STRG_KEY"]
    [job] = jobs(world, "FILE_UPLOAD")
    assert (job["ACTR_TYPE_CD"], job["MBR_SN"], job["MNGR_SN"], job["TRGT_KEY_VL"]) == (
        "AK.MEMBER",
        me["MBR_SN"],
        None,
        str(row["FILE_SN"]),
    )
    listed = world.client.get(f"{MEMBER}/me/inquiries/{target['PST_SN']}/files").json()
    assert (listed["canEdit"], listed["maxFiles"], len(listed["items"])) == (True, 5, 1)
    assert "pdf" in listed["allowedExtensions"] and listed["maxBytes"] == 20 * 1024 * 1024


def test_검증은_관리자와_같아_형식이_틀리면_거절하고_아무것도_남기지_않는다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    assert up(world, target["PST_SN"], "가짜.pdf", b"not a pdf").status_code == 422
    assert up(world, target["PST_SN"], "실행.exe", b"MZ").status_code == 422
    assert up(world, target["PST_SN"], "빈.pdf", b"").status_code == 422
    assert files_of(world) == [] and [p for p in root.rglob("*") if p.is_file()] == []


def test_첨부는_다섯_개까지다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    for n in range(5):
        assert up(world, target["PST_SN"], f"f{n}.pdf").status_code == 201
    over = up(world, target["PST_SN"], "f5.pdf")
    assert over.status_code == 422 and "5개" in over.json()["message"]


def test_같은_키로_다시_올리면_같은_파일이고_다른_파일이면_409다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    first = up(world, target["PST_SN"], idem="same-key-0001")
    again = up(world, target["PST_SN"], idem="same-key-0001")
    assert (
        again.status_code == 201
        and again.json()["fileId"] == first.json()["fileId"]
        and len(files_of(world)) == 1
    )
    other = up(world, target["PST_SN"], "다른.pdf", PDF + b"x", idem="same-key-0001")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_남의_문의와_지운_문의와_없는_문의는_404이다(world: World, qna: dict[str, Any], root: Path) -> None:
    me, other = person(world), person(world, "박다라")
    theirs = inquiry_of(world, qna, other)
    gone = inquiry_of(world, qna, me, DEL_YN="Y")
    reply = answered(world, inquiry_of(world, qna, me))
    as_member(world, me)
    for sn in (theirs["PST_SN"], gone["PST_SN"], reply["PST_SN"], 999999999):
        assert world.client.get(f"{MEMBER}/me/inquiries/{sn}/files").status_code == 404, sn
        assert up(world, sn).status_code == 404, sn
    assert files_of(world) == []


def test_멱등키와_CSRF가_없으면_거절한다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    files = {"file": ("a.pdf", PDF, "application/octet-stream")}
    no_key = world.client.post(
        f"{MEMBER}/me/inquiries/{target['PST_SN']}/files", files=files, headers=csrf(world)
    )
    assert no_key.status_code in (400, 422)
    no_csrf = world.client.post(
        f"{MEMBER}/me/inquiries/{target['PST_SN']}/files",
        files=files,
        headers={"Idempotency-Key": "mfile-00000001"},
    )
    assert no_csrf.status_code == 403
    assert files_of(world) == []


# --- 잠김 ---------------------------------------------------------------------------------------


def test_답변이_달리면_올리고_지울_수_없고_목록은_잠김을_알린다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"]).json()["fileId"])
    answered(world, target)
    listed = world.client.get(f"{MEMBER}/me/inquiries/{target['PST_SN']}/files").json()
    assert listed["canEdit"] is False and len(listed["items"]) == 1
    r = up(world, target["PST_SN"])
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    d = world.client.delete(f"{MEMBER}/me/files/{sn}", headers=csrf(world))
    assert (
        d.status_code == 409
        and len(files_of(world)) == 1
        and files_of(world)[0]["FILE_STTS_CD"] != "FS.DELETE"
    )


def test_게시판이_첨부를_쓰지_않으면_올릴_수_없다(world: World) -> None:
    off = board(world, "qna", MBR_WRT_YN="Y", ATCH_USE_YN="N")
    me = person(world)
    target = inquiry_of(world, off, me)
    as_member(world, me)
    assert world.client.get(f"{MEMBER}/me/inquiries/{target['PST_SN']}/files").json()["canEdit"] is False
    assert up(world, target["PST_SN"]).status_code == 409


# --- 삭제 ---------------------------------------------------------------------------------------


def test_내_파일은_논리삭제하고_목록에서_사라지며_다시_지우면_404다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"]).json()["fileId"])
    r = world.client.delete(f"{MEMBER}/me/files/{sn}", headers=csrf(world))
    assert r.status_code == 204 and r.content == b""
    assert files_of(world)[0]["FILE_STTS_CD"] == "FS.DELETE"
    assert world.client.get(f"{MEMBER}/me/inquiries/{target['PST_SN']}/files").json()["items"] == []
    assert world.client.delete(f"{MEMBER}/me/files/{sn}", headers=csrf(world)).status_code == 404
    [job] = jobs(world, "FILE_DELETE")
    assert (job["ACTR_TYPE_CD"], job["MBR_SN"], job["TRGT_KEY_VL"]) == ("AK.MEMBER", me["MBR_SN"], str(sn))
    assert up(world, target["PST_SN"]).status_code == 201  # 지우면 자리가 난다


def test_남의_파일과_문의가_아닌_파일은_지울_수_없고_404다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me, other = person(world), person(world, "박다라")
    theirs = inquiry_of(world, qna, other)
    as_member(world, other)
    sn = int(up(world, theirs["PST_SN"]).json()["fileId"])
    as_member(world, me)
    assert world.client.delete(f"{MEMBER}/me/files/{sn}", headers=csrf(world)).status_code == 404
    assert files_of(world)[0]["FILE_STTS_CD"] == "FS.PENDING"
    assert world.client.delete(f"{MEMBER}/me/files/999999999", headers=csrf(world)).status_code == 404
    assert world.client.delete(f"{MEMBER}/me/files/abc", headers=csrf(world)).status_code in (400, 422)


# --- 내려받기 -----------------------------------------------------------------------------------


def test_검사를_통과한_내_파일만_내려받고_기록한다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"], "내 증빙.pdf").json()["fileId"])
    pending = world.client.get(f"{MEMBER}/me/files/{sn}")
    assert pending.status_code == 404  # 검사 전
    put(world, sn)
    r = world.client.get(f"{MEMBER}/me/files/{sn}")
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    assert (
        "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
    )
    assert r.headers["cache-control"] == "private, no-store"
    [ok] = [j for j in jobs(world, "FILE_DOWNLOAD") if j["JOB_RSLT_CD"] == "JR.SUCCESS"]
    assert (ok["ACTR_TYPE_CD"], ok["MBR_SN"], ok["TRGT_KEY_VL"]) == ("AK.MEMBER", me["MBR_SN"], str(sn))
    assert (
        len([j for j in jobs(world, "FILE_DOWNLOAD") if j["JOB_RSLT_CD"] == "JR.DENY"]) == 1
    )  # 검사 전 시도


@pytest.mark.parametrize("status", ["FS.BLOCK", "FS.DELETE"])
def test_차단되거나_지운_파일은_내려받을_수_없다(
    world: World, qna: dict[str, Any], root: Path, status: str
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"]).json()["fileId"])
    put(world, sn, status)
    assert world.client.get(f"{MEMBER}/me/files/{sn}").status_code == 404


def test_남의_파일은_검사를_통과했어도_404이고_시도를_기록한다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me, other = person(world), person(world, "박다라")
    theirs = inquiry_of(world, qna, other)
    as_member(world, other)
    sn = int(up(world, theirs["PST_SN"]).json()["fileId"])
    put(world, sn)
    as_member(world, me)
    assert world.client.get(f"{MEMBER}/me/files/{sn}").status_code == 404
    [deny] = jobs(world, "FILE_DOWNLOAD")
    assert (deny["JOB_RSLT_CD"], deny["MBR_SN"], deny["TRGT_KEY_VL"]) == ("JR.DENY", me["MBR_SN"], str(sn))
    assert world.client.get(f"{MEMBER}/me/files/999999999").status_code == 404


def test_저장소에서_사라진_파일은_500이고_경로를_알리지_않는다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"]).json()["fileId"])
    put(world, sn)
    for p in root.rglob("*"):
        if p.is_file():
            p.unlink()
    r = world.client.get(f"{MEMBER}/me/files/{sn}")
    assert r.status_code == 500 and str(root) not in r.text


# --- 관리자와 이어지는 흐름 ---------------------------------------------------------------------


def test_주민이_올린_첨부를_담당자가_보고_내려받는다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"], "증빙.pdf").json()["fileId"])
    put(world, sn)
    use(world, staff(world, "boss", "AU.POST_W"))
    listed = call(world, "GET", "/files?ownerKind=POST").json()["items"]
    assert [(i["fileId"], i["fileName"]) for i in listed] == [(str(sn), "증빙.pdf")]
    r = call(world, "GET", f"/files/{sn}/download")
    assert r.status_code == 200 and r.content == PDF


def test_질문과_답변_게시판이_아닌_내_글에는_올릴_수_없다(world: World, root: Path) -> None:
    review = board(world, "review", MBR_WRT_YN="Y", ATCH_USE_YN="Y")
    me = person(world)
    mine = asked(world, review, me, "후기")
    as_member(world, me)
    assert world.client.get(f"{MEMBER}/me/inquiries/{mine['PST_SN']}/files").status_code == 404
    assert up(world, mine["PST_SN"]).status_code == 404 and files_of(world) == []


def test_지운_답변은_답변으로_치지_않아_올릴_수_있다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    answered(world, target)
    world.db.execute(text("UPDATE TB_PST SET DEL_YN='Y' WHERE UP_PST_SN=:s"), {"s": target["PST_SN"]})
    as_member(world, me)
    assert up(world, target["PST_SN"]).status_code == 201


def test_답변이_달린_문의에는_파일을_검증하기_전에_409다(
    world: World, qna: dict[str, Any], root: Path
) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    answered(world, target)
    as_member(world, me)
    assert up(world, target["PST_SN"], "가짜.pdf", b"not a pdf").status_code == 409


def test_강좌_파일_같은_다른_소유자의_파일은_404다(world: World, qna: dict[str, Any], root: Path) -> None:
    from tests.test_applications_read import open_course  # noqa: PLC0415

    plan = world.factory.make(
        "TB_FILE", CORS_SN=open_course(world)["CORS_SN"], FILE_STTS_CD="FS.SAFE", FILE_USE_CD="FP.PLAN"
    )
    as_member(world, person(world))
    assert world.client.get(f"{MEMBER}/me/files/{plan['FILE_SN']}").status_code == 404
    assert world.client.delete(f"{MEMBER}/me/files/{plan['FILE_SN']}", headers=csrf(world)).status_code == 404


def test_삭제하면_수정_일시가_남는다(world: World, qna: dict[str, Any], root: Path) -> None:
    me = person(world)
    target = inquiry_of(world, qna, me)
    as_member(world, me)
    sn = int(up(world, target["PST_SN"]).json()["fileId"])
    world.client.delete(f"{MEMBER}/me/files/{sn}", headers=csrf(world))
    assert rows(world, "SELECT MDFCN_DT d FROM TB_FILE WHERE FILE_SN=:s", s=sn)[0]["d"] is not None
