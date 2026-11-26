# 시설·강의실 사진(올리기 한도·형식·권한, 대표 지정, 전체 목록, 주민 시설안내 공개)을 실제 앱과 MariaDB로 확인하는 시험
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_files_admin import files_of, jobs, key, put, rows, upload
from tests.test_site_facilities import facility, listed
from tests.world import ADMIN, MEMBER, World

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"image"
JPG = b"\xff\xd8\xff\xe0" + b"jpeg-image"


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    """저장소 위치를 시험용 임시 폴더로 바꾼다."""
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


def editor(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"p{key().split('-')[1]}", *(codes or ("AU.FCLT_W",)), **kw)
    use(w, who)
    return who


def site(w: World, **values: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    center = facility(w, "행정복지센터", "FT.CENTER", **values)
    room = facility(w, "공연장", UP_FCLT_SN=center["FCLT_SN"], FCLT_EXPLN="층: 1층", **values)
    return center, room


def path(target: dict[str, Any]) -> str:
    return f"/facilities/{int(target['FCLT_SN'])}/files"


def add(w: World, target: dict[str, Any], name: str = "사진.png", data: bytes = PNG) -> int:
    res = upload(w, path(target), name, data)
    assert res.status_code == 201, res.text
    return int(res.json()["fileId"])


def names(w: World, target: dict[str, Any]) -> list[str]:
    return [item["fileName"] for item in call(w, "GET", path(target)).json()["items"]]


def main(w: World, target: dict[str, Any], file_sn: int, idem: str | None = None) -> Any:
    url = f"/facilities/{int(target['FCLT_SN'])}/files/{file_sn}/representative"
    return call(w, "POST", url, None, **{"Idempotency-Key": idem or key()})


# --- 올리기 -------------------------------------------------------------------------------------


def test_센터와_강의실에_사진을_올리면_검사_대기로_저장한다(world: World, root: Path) -> None:
    center, room = site(world)
    editor(world)
    add(world, center, "청사.jpg", JPG)
    add(world, room, "무대.png")
    saved = files_of(world)
    assert [(int(f["FCLT_SN"]), f["FILE_USE_CD"].strip(), f["FILE_STTS_CD"].strip()) for f in saved] == [
        (int(center["FCLT_SN"]), "FP.IMAGE", "FS.PENDING"),
        (int(room["FCLT_SN"]), "FP.IMAGE", "FS.PENDING"),
    ]
    listing = call(world, "GET", path(room)).json()
    assert (listing["canEdit"], listing["maxFiles"]) == (True, 5)
    assert names(world, room) == ["무대.png"] and len(jobs(world, "FILE_UPLOAD")) == 2


def test_사진은_다섯_장까지이고_제거하면_다시_올려_맨_뒤에_놓인다(world: World, root: Path) -> None:
    _, room = site(world)
    editor(world)
    ids = [add(world, room, f"{n}.png") for n in range(1, 6)]
    over = upload(world, path(room), "6.png", PNG)
    assert over.status_code == 422 and "file" in over.json()["fields"]
    for gone in ids[:3]:
        assert call(world, "DELETE", f"/files/{gone}").status_code == 204
    add(world, room, "새.png")
    assert names(world, room) == ["4.png", "5.png", "새.png"]  # 새 사진이 대표 자리를 빼앗지 않는다


def test_이미지가_아닌_파일은_422이다(world: World, root: Path) -> None:
    _, room = site(world)
    editor(world)
    res = upload(world, path(room), "안내.pdf", b"%PDF-1.7\nx")
    assert res.status_code == 422 and "이미지" in res.json()["fields"]["file"]
    assert files_of(world) == []


def test_사용_중지한_시설에도_사진을_올릴_수_있다(world: World, root: Path) -> None:
    _, room = site(world, USE_YN="N")
    editor(world)
    add(world, room)


def test_시설_권한이_없거나_범위_밖이거나_없는_시설은_404이다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    _, ours = site(world, DONG_SN=mine["DONG_SN"])
    theirs = facility(world, "남의 교실", DONG_SN=other["DONG_SN"])
    common = facility(world, "공통 교실")
    editor(world, "AU.CORS_W", "AU.SITE_W")
    assert upload(world, path(ours), "a.png", PNG).status_code == 404
    assert call(world, "GET", path(ours)).status_code == 404
    editor(world, "AU.FCLT_W", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    add(world, ours)
    for target in (theirs, common):
        assert upload(world, path(target), "a.png", PNG).status_code == 404
        assert call(world, "GET", path(target)).status_code == 404
    assert upload(world, "/facilities/999999999/files", "a.png", PNG).status_code == 404


# --- 대표 사진 -----------------------------------------------------------------------------------


def test_대표로_지정한_사진이_맨_앞에_오고_나머지_순서는_유지된다(world: World, root: Path) -> None:
    _, room = site(world)
    editor(world)
    ids = [add(world, room, f"{n}.png") for n in (1, 2, 3)]
    for sn in ids:
        put(world, sn)
    res = main(world, room, ids[2])
    assert res.status_code == 200, res.text
    assert [i["fileName"] for i in res.json()["items"]] == ["3.png", "1.png", "2.png"]
    assert names(world, room) == ["3.png", "1.png", "2.png"]
    [job] = jobs(world, "FCLT_PHOTO_MAIN")
    assert job["TRGT_TBL_NM"] == "TB_FCLT" and int(job["TRGT_KEY_VL"]) == int(room["FCLT_SN"])
    add(world, room, "4.png")
    assert names(world, room) == ["3.png", "1.png", "2.png", "4.png"]


def test_대표_지정은_같은_키면_다시_바꾸지_않고_내용이_다르면_409이다(world: World, root: Path) -> None:
    _, room = site(world)
    editor(world)
    ids = [add(world, room, f"{n}.png") for n in (1, 2, 3)]
    for sn in ids:
        put(world, sn)
    assert main(world, room, ids[1], "main-key-0001").status_code == 200
    assert main(world, room, ids[2], "main-key-0002").status_code == 200
    replay = main(world, room, ids[1], "main-key-0001")
    assert replay.status_code == 200 and names(world, room) == ["3.png", "2.png", "1.png"]
    assert main(world, room, ids[0], "main-key-0001").status_code == 409
    assert len(jobs(world, "FCLT_PHOTO_MAIN")) == 2


def test_검사를_통과하지_않았거나_다른_시설이거나_지운_사진은_대표가_될_수_없다(
    world: World,
    root: Path,
) -> None:
    center, room = site(world)
    editor(world)
    waiting, elsewhere, gone = add(world, room), add(world, center), add(world, room, "b.png")
    assert main(world, room, waiting).status_code == 422
    put(world, elsewhere)
    assert main(world, room, elsewhere).status_code == 404
    assert call(world, "DELETE", f"/files/{gone}").status_code == 204
    assert main(world, room, gone).status_code == 404
    assert jobs(world, "FCLT_PHOTO_MAIN") == []
    editor(world, "AU.SITE_W")
    assert main(world, room, waiting).status_code == 404


# --- 관리자 파일 목록·내려받기 -------------------------------------------------------------------


def test_전체_파일_목록과_상세에_시설_사진이_시설_이름으로_보인다(world: World, root: Path) -> None:
    _, room = site(world)
    editor(world, "AU.FCLT_W", "AU.SITE_W")
    sn = add(world, room, "무대.png")
    page = call(world, "GET", "/files?ownerKind=FACILITY").json()
    assert [(i["fileName"], i["ownerKind"], i["ownerLabel"]) for i in page["items"]] == [
        ("무대.png", "FACILITY", "공연장")
    ]
    assert call(world, "GET", f"/files/{sn}").json()["purpose"] == "IMAGE"
    assert call(world, "GET", f"/files/{sn}/download").status_code == 404  # 검사 대기
    put(world, sn)
    got = call(world, "GET", f"/files/{sn}/download")
    assert got.status_code == 200 and got.content == PNG
    editor(world, "AU.SITE_W")
    assert call(world, "GET", "/files").json()["items"] == []
    assert call(world, "GET", f"/files/{sn}").status_code == 404


# --- 주민 시설안내 --------------------------------------------------------------------------------


def photos(w: World) -> dict[str, list[str]]:
    return {item["name"]: item["photoUrls"] for item in listed(w)}


def test_주민은_검사를_통과한_사진만_대표부터_순서대로_보고_로그인_없이_받는다(
    world: World,
    root: Path,
) -> None:
    center, room = site(world)
    editor(world)
    first, second, blocked, waiting = (add(world, room, f"{n}.png") for n in (1, 2, 3, 4))
    for sn in (first, second):
        put(world, sn)
    put(world, blocked, "FS.BLOCK")
    assert main(world, room, second).status_code == 200
    world.db.commit()
    world.client.cookies.clear()
    assert photos(world) == {
        "행정복지센터": [],
        "공연장": [f"{MEMBER}/files/{second}", f"{MEMBER}/files/{first}"],
    }
    got = world.client.get(f"{MEMBER}/files/{second}")
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-disposition"].startswith("inline")
    for hidden in (blocked, waiting):
        assert world.client.get(f"{MEMBER}/files/{hidden}").status_code == 404
    assert rows(world, "SELECT 1 FROM TB_FILE WHERE FCLT_SN=:f", f=center["FCLT_SN"]) == []
    assert world.client.get(f"{ADMIN}{path(room)}").status_code == 401


@pytest.mark.parametrize("closed", ["ROOM", "CENTER"])
def test_사용_중지한_시설이나_센터의_사진은_주민에게_열지_않는다(
    world: World,
    root: Path,
    closed: str,
) -> None:
    center, room = site(world)
    editor(world)
    sn = add(world, room)
    put(world, sn)
    target = room if closed == "ROOM" else center
    world.db.execute(text("UPDATE TB_FCLT SET USE_YN='N' WHERE FCLT_SN=:f"), {"f": target["FCLT_SN"]})
    world.db.commit()
    assert world.client.get(f"{MEMBER}/files/{sn}").status_code == 404
    assert "공연장" not in photos(world)
