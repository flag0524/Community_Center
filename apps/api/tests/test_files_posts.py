# 관리자 게시물 첨부(올리기·목록·삭제·내려받기, 게시판 첨부 정책, 동 범위, 회원이 쓴 글·삭제한 글)를 실제 앱과 MariaDB로 확인하는 시험
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.admin import file_service
from tests.arena import Arena, Staff, parallel
from tests.factory import RowFactory
from tests.test_admin_access import dong
from tests.test_admin_refunds import call
from tests.test_board_public import board, post
from tests.test_files_admin import PDF, files_of, put, rows, upload, writer
from tests.test_files_admin import root as root  # 저장소를 임시 폴더로 바꾸는 픽스처
from tests.world import World, make_member

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"image"


def path(sn: Any) -> str:
    return f"/posts/{sn}/files"


def test_게시물에_파일을_올리면_첨부_용도로_검사_대기_저장하고_목록에_정책을_준다(
    world: World, root: Path
) -> None:
    target = post(world, board(world, "resources"), "자료")
    who = writer(world, "AU.POST_W")
    r = upload(world, path(target["PST_SN"]), "서식.pdf")
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    [row] = files_of(world)
    assert (row["PST_SN"], row["FILE_USE_CD"], row["FILE_STTS_CD"]) == (
        target["PST_SN"],
        "FP.ATTACH",
        "FS.PENDING",
    )
    assert (root / row["STRG_KEY"]).read_bytes() == PDF
    listed = call(world, "GET", path(target["PST_SN"])).json()
    assert (listed["canEdit"], listed["maxFiles"]) == (True, 5) and len(listed["items"]) == 1
    assert rows(world, "SELECT MNGR_SN m FROM TB_JOB_HSTRY WHERE JOB_CD='FILE_UPLOAD'")[0]["m"] == who.sn


def test_첨부는_다섯_개까지이고_갤러리는_이미지_열_장까지다(world: World, root: Path) -> None:
    notice = post(world, board(world, "resources"), "자료")
    gallery = post(world, board(world, "gallery"), "사진")
    writer(world, "AU.POST_W")
    for n in range(5):
        assert upload(world, path(notice["PST_SN"]), f"f{n}.pdf").status_code == 201
    over = upload(world, path(notice["PST_SN"]), "f5.pdf")
    assert over.status_code == 422 and "5개" in over.json()["message"]
    for n in range(10):
        assert upload(world, path(gallery["PST_SN"]), f"p{n}.png", PNG).status_code == 201
    assert upload(world, path(gallery["PST_SN"]), "p10.png", PNG).status_code == 422
    assert call(world, "GET", path(gallery["PST_SN"])).json()["maxFiles"] == 10
    assert {r["FILE_USE_CD"] for r in files_of(world) if r["PST_SN"] == gallery["PST_SN"]} == {"FP.IMAGE"}


def test_갤러리에는_이미지만_올릴_수_있다(world: World, root: Path) -> None:
    gallery = post(world, board(world, "gallery"), "사진")
    writer(world, "AU.POST_W")
    r = upload(world, path(gallery["PST_SN"]), "문서.pdf")
    assert r.status_code == 422 and "file" in r.json()["fields"] and files_of(world) == []


def test_첨부를_끈_게시판과_회원이_쓴_글에는_올리고_지울_수_없다(world: World, root: Path) -> None:
    off = post(world, board(world, "resources", ATCH_USE_YN="N"), "첨부 끔")
    qna = board(world, "qna", MBR_WRT_YN="Y")
    theirs = post(world, qna, "후기", WRT_MBR_SN=make_member(world, "w1")["MBR_SN"], WRT_MNGR_SN=None)
    writer(world, "AU.POST_W")
    for target in (off, theirs):
        assert call(world, "GET", path(target["PST_SN"])).json()["canEdit"] is False
        r = upload(world, path(target["PST_SN"]))
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert files_of(world) == []


def test_첨부를_끄면_이미_올린_파일도_지울_수_없다(world: World, root: Path) -> None:
    bbs = board(world, "resources")
    target = post(world, bbs, "자료")
    writer(world, "AU.POST_W")
    sn = int(upload(world, path(target["PST_SN"])).json()["fileId"])
    world.db.execute(text("UPDATE TB_BBS SET ATCH_USE_YN='N' WHERE BBS_SN=:b"), {"b": bbs["BBS_SN"]})
    assert call(world, "DELETE", f"/files/{sn}").status_code == 409


def test_권한이_없으면_게시물_첨부를_볼_수_없고_동_범위를_따른다(world: World, root: Path) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    bbs = board(world, "resources")
    mine = post(world, bbs, "내 글", DONG_SN=a["DONG_SN"])
    other = post(world, bbs, "남의 글", DONG_SN=b["DONG_SN"])
    common = post(world, bbs, "공통 글")
    writer(world, "AU.CORS_W")  # 강좌 권한만 있다
    assert call(world, "GET", path(mine["PST_SN"])).status_code == 404
    assert upload(world, path(mine["PST_SN"])).status_code == 404
    writer(world, "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert upload(world, path(mine["PST_SN"])).status_code == 201
    for hidden in (other, common):
        assert call(world, "GET", path(hidden["PST_SN"])).status_code == 404
        assert upload(world, path(hidden["PST_SN"])).status_code == 404


def test_지운_글과_답변과_없는_글은_404이고_지운_글의_파일은_목록에서_사라진다(
    world: World, root: Path
) -> None:
    qna = board(world, "qna", MBR_WRT_YN="Y")
    asked = post(world, qna, "질문", WRT_MBR_SN=make_member(world, "w1")["MBR_SN"], WRT_MNGR_SN=None)
    reply = post(world, qna, "답변", UP_PST_SN=asked["PST_SN"], PST_TYPE_CD="PT.REPLY")
    bbs = board(world, "resources")
    target = post(world, bbs, "자료")
    writer(world, "AU.POST_W")
    sn = int(upload(world, path(target["PST_SN"])).json()["fileId"])
    assert [i["fileId"] for i in call(world, "GET", "/files").json()["items"]] == [str(sn)]
    assert call(world, "DELETE", f"/posts/{target['PST_SN']}").status_code == 204
    assert call(world, "GET", path(target["PST_SN"])).status_code == 404
    assert upload(world, path(target["PST_SN"])).status_code == 404
    assert call(world, "GET", f"/files/{sn}").status_code == 404
    assert call(world, "GET", "/files").json()["items"] == []
    assert call(world, "GET", path(reply["PST_SN"])).status_code == 404
    assert call(world, "GET", path(999999999)).status_code == 404


def test_전체_목록은_게시물_종류와_게시물_제목을_보이고_범위_밖_파일은_빼며_내려받기도_된다(
    world: World, root: Path
) -> None:
    a, b = dong(world, "가동"), dong(world, "나동")
    bbs = board(world, "resources")
    mine = post(world, bbs, "내 자료", DONG_SN=a["DONG_SN"])
    other = post(world, bbs, "남의 자료", DONG_SN=b["DONG_SN"])
    writer(world, "AU.POST_W")
    mine_file = int(upload(world, path(mine["PST_SN"])).json()["fileId"])
    other_file = int(upload(world, path(other["PST_SN"])).json()["fileId"])
    put(world, mine_file)
    writer(world, "AU.POST_W", kind="SK.DONG", dong_sn=a["DONG_SN"])
    items = call(world, "GET", "/files?ownerKind=POST").json()["items"]
    assert [(i["fileId"], i["ownerKind"], i["ownerLabel"]) for i in items] == [
        (str(mine_file), "POST", "내 자료")
    ]
    assert call(world, "GET", "/files?ownerKind=COURSE").json()["items"] == []
    assert call(world, "GET", f"/files/{other_file}").status_code == 404
    assert call(world, "GET", f"/files/{mine_file}/download").status_code == 200
    assert call(world, "GET", f"/files/{other_file}/download").status_code == 404


def test_게시물_첨부를_지우면_논리삭제이고_다시_지우면_404다(world: World, root: Path) -> None:
    target = post(world, board(world, "resources"), "자료")
    writer(world, "AU.POST_W")
    sn = int(upload(world, path(target["PST_SN"])).json()["fileId"])
    assert call(world, "DELETE", f"/files/{sn}").status_code == 204
    assert files_of(world)[0]["FILE_STTS_CD"] == "FS.DELETE"
    assert call(world, "DELETE", f"/files/{sn}").status_code == 404
    assert call(world, "GET", path(target["PST_SN"])).json()["items"] == []


def test_같은_키로_다시_올리면_같은_파일이고_다른_파일이면_409다(world: World, root: Path) -> None:
    target = post(world, board(world, "resources"), "자료")
    writer(world, "AU.POST_W")
    first = upload(world, path(target["PST_SN"]), idem="same-key-0001")
    again = upload(world, path(target["PST_SN"]), idem="same-key-0001")
    assert (
        again.status_code == 201
        and again.json()["fileId"] == first.json()["fileId"]
        and len(files_of(world)) == 1
    )
    other = upload(world, path(target["PST_SN"]), "다른.pdf", PDF + b"x", idem="same-key-0001")
    assert other.status_code == 409


def test_동시에_여러_파일을_올려도_개수_한도를_넘지_않는다(
    arena: Arena, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arena.settings = replace(arena.settings, file_root=str(tmp_path))

    def build(f: RowFactory) -> tuple[int, int]:
        bundle = f.bundle()
        bbs = f.make(
            "TB_BBS",
            OPER_BNDL_SN=bundle,
            BBS_ID="resources",
            BBS_NM="자료",
            BBS_TYPE_CD="BT.DATA",
            ATCH_USE_YN="Y",
        )
        return bundle, int(bbs["BBS_SN"])

    bundle, bbs = arena.build(build)
    arena.serve(bundle)
    who = arena.staff(bundle, "s1", "AU.POST_W")
    with arena.migrated.begin() as connection:
        post_sn = int(
            RowFactory(connection, arena.schema).make(
                "TB_PST",
                OPER_BNDL_SN=bundle,
                BBS_SN=bbs,
                PST_TTL="자료",
                PST_CN="본문",
                WRT_MNGR_SN=who.admin_sn,
            )["PST_SN"]
        )
    real = file_service.write_blob  # type: ignore[attr-defined]

    def slow(*args: Any) -> None:
        time.sleep(0.2)  # 개수를 센 뒤 저장하기 전의 틈을 넓혀 잠금이 없으면 겹치게 한다
        real(*args)

    monkeypatch.setattr(file_service, "write_blob", slow)

    def sender(n: int, s: Staff) -> Callable[[], Any]:
        return lambda: s.client.post(
            f"/api/admin/v1/posts/{post_sn}/files",
            files={"file": (f"f{n}.pdf", PDF, "application/octet-stream")},
            headers={"X-CSRF-Token": s.csrf, "Idempotency-Key": f"conc-key-{n:04d}"},
        )

    # 세션이 다르면 요청이 서로 기다리지 않는다
    others = [arena.staff(bundle, f"t{n}", "AU.POST_W") for n in range(8)]
    codes = sorted(r.status_code for r in parallel([sender(n, s) for n, s in enumerate(others)]))
    assert codes == [201] * 5 + [422] * 3, codes
    assert (
        len(arena.query("SELECT 1 FROM TB_FILE WHERE PST_SN=:p AND FILE_STTS_CD<>'FS.DELETE'", p=post_sn))
        == 5
    )
