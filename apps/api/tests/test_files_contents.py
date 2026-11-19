# 홈 배너·팝업 이미지 올리기·목록·전체 목록·상세·삭제·내려받기(범위, 한 장, 유형, 형식)를 실제 앱과 MariaDB로 확인하는 시험
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.core.config import get_settings
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_files_admin import files_of, jobs, key, put, upload
from tests.test_site_public import publish
from tests.world import World

pytestmark = pytest.mark.db


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    """저장소 위치를 시험용 임시 폴더로 바꾼다."""
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


PNG = b"\x89PNG\r\n\x1a\n" + b"image"
JPG = b"\xff\xd8\xff\xe0" + b"jpeg-image"


def editor(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"c{next_id()}", *(codes or ("AU.SITE_W",)), **kw)
    use(w, who)
    return who


def next_id() -> str:
    return key().split("-")[1]


def path(content: dict[str, Any]) -> str:
    return f"/contents/{content['SITE_CONTS_SN']}/files"


def test_배너에_이미지_한_장을_올리면_검사_대기로_저장하고_목록에_보인다(world: World, root: Path) -> None:
    banner = publish(world, "CT.BANNER", "banner-1", "본문")
    editor(world)
    res = upload(world, path(banner), "배너.png", PNG)
    assert res.status_code == 201, res.text
    assert (res.json()["fileName"], res.json()["status"]) == ("배너.png", "PENDING")
    [saved] = files_of(world)
    assert saved["SITE_CONTS_SN"] == banner["SITE_CONTS_SN"] and saved["FILE_USE_CD"].strip() == "FP.IMAGE"
    listing = call(world, "GET", path(banner)).json()
    assert [i["fileName"] for i in listing["items"]] == ["배너.png"]
    assert (listing["canEdit"], listing["maxFiles"]) == (True, 1)
    assert len(jobs(world, "FILE_UPLOAD")) == 1


def test_팝업도_올릴_수_있고_이미지는_한_장뿐이며_제거하면_다시_올릴_수_있다(
    world: World, root: Path
) -> None:
    popup = publish(world, "CT.POPUP", "popup-1", "본문")
    editor(world)
    first = upload(world, path(popup), "a.jpg", JPG)
    assert first.status_code == 201
    second = upload(world, path(popup), "b.png", PNG)
    assert second.status_code == 422 and "file" in second.json()["fields"]
    assert call(world, "DELETE", f"/files/{first.json()['fileId']}").status_code == 204
    assert upload(world, path(popup), "b.png", PNG).status_code == 201
    assert len(files_of(world)) == 2


def test_홈_비주얼에도_이미지_한_장을_올릴_수_있다(world: World, root: Path) -> None:
    visual = publish(world, "CT.VISUAL", "home-visual", "본문")
    editor(world)
    first = upload(world, path(visual), "청사.png", PNG)
    assert first.status_code == 201, first.text
    assert upload(world, path(visual), "둘째.png", PNG).status_code == 422  # 한 장뿐이다
    assert call(world, "GET", path(visual)).json()["maxFiles"] == 1


def test_이미지를_쓰지_않는_유형은_올릴_수_없고_목록에서_편집_불가이다(world: World, root: Path) -> None:
    history = publish(world, "CT.HISTORY", "center-history", "연혁")
    editor(world)
    res = upload(world, path(history), "a.png", PNG)
    assert res.status_code == 422 and "file" in res.json()["fields"]
    assert call(world, "GET", path(history)).json()["canEdit"] is False
    assert files_of(world) == []


def test_이미지가_아닌_파일은_422이다(world: World, root: Path) -> None:
    banner = publish(world, "CT.BANNER", "banner-1", "본문")
    editor(world)
    res = upload(world, path(banner), "문서.pdf", b"%PDF-1.7\nx")
    assert res.status_code == 422 and "file" in res.json()["fields"]
    assert files_of(world) == []


def test_권한이_없거나_없는_콘텐츠나_다른_유형은_존재를_알리지_않고_404이다(world: World, root: Path) -> None:
    banner = publish(world, "CT.BANNER", "banner-1", "본문")
    terms = publish(world, "CT.TERMS", "terms", "약관")
    editor(world, "AU.APLY_R")
    assert upload(world, path(banner), "a.png", PNG).status_code == 404
    assert call(world, "GET", path(banner)).status_code == 404
    assert call(world, "GET", "/files").status_code == 403
    editor(world)
    assert upload(world, "/contents/999999999/files", "a.png", PNG).status_code == 404
    assert (
        upload(world, path(terms), "a.png", PNG).status_code == 404
    )  # 홈·센터 콘텐츠가 아닌 약관은 이 경로의 대상이 아니다
    assert call(world, "GET", path(terms)).status_code == 404


def test_동_담당자는_자기_동_콘텐츠만_다룬다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    ok = publish(world, "CT.BANNER", "banner-a", "내", DONG_SN=mine["DONG_SN"])
    no = publish(world, "CT.BANNER", "banner-b", "남", DONG_SN=other["DONG_SN"])
    common = publish(world, "CT.BANNER", "banner-c", "공통")
    editor(world, "AU.SITE_W", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    assert upload(world, path(ok), "a.png", PNG).status_code == 201
    for target in (no, common):
        assert upload(world, path(target), "a.png", PNG).status_code == 404
        assert call(world, "GET", path(target)).status_code == 404


def test_CSRF_토큰이_없으면_올릴_수_없다(world: World, root: Path) -> None:
    banner = publish(world, "CT.BANNER", "banner-1", "본문")
    editor(world)
    res = world.client.post(
        f"/api/admin/v1{path(banner)}",
        files={"file": ("a.png", PNG, "image/png")},
        headers={"Idempotency-Key": key()},
    )
    assert res.status_code == 403 and files_of(world) == []


def test_전체_목록과_상세와_내려받기는_콘텐츠_범위를_따른다(world: World, root: Path) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    a = publish(world, "CT.BANNER", "banner-a", "내", DONG_SN=mine["DONG_SN"], CONTS_TTL="내 배너")
    b = publish(world, "CT.POPUP", "popup-b", "남", DONG_SN=other["DONG_SN"], CONTS_TTL="남 팝업")
    editor(world)
    fa = upload(world, path(a), "a.png", PNG).json()["fileId"]
    fb = upload(world, path(b), "b.png", PNG).json()["fileId"]
    listed = call(
        world,
        "GET",
        "/files",
    ).json()["items"]
    assert sorted((i["ownerKind"], i["ownerLabel"]) for i in listed) == [
        ("CONTENT", "남 팝업"),
        ("CONTENT", "내 배너"),
    ]
    only = call(world, "GET", "/files?ownerKind=CONTENT").json()["items"]
    assert len(only) == 2
    assert call(world, "GET", "/files?ownerKind=POST").json()["items"] == []
    detail = call(world, "GET", f"/files/{fa}").json()
    assert (detail["ownerKind"], detail["purpose"]) == ("CONTENT", "IMAGE")
    put(world, int(fa))
    assert call(world, "GET", f"/files/{fa}/download").status_code == 200
    editor(world, "AU.SITE_W", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [fa]
    assert call(world, "GET", f"/files/{fb}").status_code == 404
    assert call(world, "DELETE", f"/files/{fb}").status_code == 404


def test_감면_증빙과_강사_지원서_파일도_상세와_내려받기가_된다(world: World, root: Path) -> None:
    ia = world.factory.make("TB_INSTR_APLY")
    proof = world.factory.make(
        "TB_FILE", INSTR_APLY_SN=ia["INSTR_APLY_SN"], FILE_STTS_CD="FS.SAFE", FILE_USE_CD="FP.PROOF"
    )
    editor(world, "AU.INSTR_W")
    detail = call(world, "GET", f"/files/{proof['FILE_SN']}")
    assert detail.status_code == 200, detail.text
    assert (detail.json()["ownerKind"], detail.json()["ownerLabel"]) == (
        "INSTRUCTOR_APPLICATION",
        f"강사 지원 {ia['INSTR_APLY_SN']}",
    )


def test_다른_묶음의_콘텐츠와_홈_콘텐츠가_아닌_유형에_붙은_파일은_보이지_않는다(
    world: World, root: Path
) -> None:
    other = world.factory.make("TB_OPER_BNDL")
    foreign = publish(world, "CT.BANNER", "banner-x", "남의 배너", OPER_BNDL_SN=other["OPER_BNDL_SN"])
    terms = publish(world, "CT.TERMS", "terms", "약관")
    world.factory.make(
        "TB_FILE", SITE_CONTS_SN=terms["SITE_CONTS_SN"], FILE_STTS_CD="FS.SAFE", FILE_USE_CD="FP.IMAGE"
    )
    editor(world)
    assert upload(world, path(foreign), "a.png", PNG).status_code == 404
    assert call(world, "GET", path(foreign)).status_code == 404
    assert call(world, "GET", "/files").json()["items"] == []
