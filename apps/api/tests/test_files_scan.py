# 파일 검사 워커(통과·차단·변조·검사기 장애·경합)와 올리기→검사→내려받기 전체 흐름을 실제 MariaDB로 확인하는 시험
import hashlib
import itertools
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.scan.mock import EICAR, MockScanner
from app.core.config import get_settings
from app.files.storage import new_key, write_blob
from app.worker import jobs
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import open_course as _open_course
from tests.test_files_admin import PDF, upload
from tests.world import START, World

pytestmark = pytest.mark.db

_n = itertools.count(1)


@pytest.fixture
def root(world: World, tmp_path: Path) -> Path:
    settings = replace(world.settings, file_root=str(tmp_path))
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return tmp_path


def scan(w: World, scanner: MockScanner, root: Path) -> int:
    w.db.commit()  # 작업은 처음에 트랜잭션을 닫으므로 시험이 만든 데이터를 먼저 고정한다
    return jobs.scan_files(w.db, replace(w.settings, file_root=str(root)), scanner, w.bundle, w.clock)


def stored(
    w: World,
    root: Path,
    data: bytes = PDF,
    *,
    age: timedelta = timedelta(0),
    status: str = "FS.PENDING",
    hash_of: bytes | None = None,
) -> dict[str, Any]:
    """저장소에 실제 파일을 쓰고 그 키를 가진 파일 행을 만든다."""
    key = new_key(w.bundle)
    write_blob(str(root), key, data)
    return w.factory.make(
        "TB_FILE",
        STRG_KEY=key,
        FILE_NM=f"f{next(_n)}.pdf",
        FILE_SZ=len(data),
        MIME_TYPE_NM="application/pdf",
        FILE_USE_CD="FP.PLAN",
        FILE_STTS_CD=status,
        FILE_HASH_VL=hashlib.sha256(data if hash_of is None else hash_of).hexdigest(),
        REG_DT=START - age,
    )


def state(w: World, f: dict[str, Any]) -> str:
    return str(
        w.db.execute(text("SELECT FILE_STTS_CD FROM TB_FILE WHERE FILE_SN=:f"), {"f": f["FILE_SN"]}).scalar()
    )


def audit(w: World) -> list[Any]:
    return list(
        w.db.execute(text("SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD='FILE_SCAN' ORDER BY JOB_HSTRY_SN"))
        .mappings()
        .all()
    )


def test_검사를_통과하면_통과로_바꾸고_시스템_이력을_남긴다(world: World, root: Path) -> None:
    f = stored(world, root)
    scanner = MockScanner()
    assert scan(world, scanner, root) == 1
    assert state(world, f) == "FS.SAFE" and scanner.scanned == [len(PDF)]
    [job] = audit(world)
    assert (job["ACTR_TYPE_CD"], job["MNGR_SN"], job["MBR_SN"], job["CHG_CN"], job["TRGT_KEY_VL"]) == (
        "AK.SYSTEM",
        None,
        None,
        "검사 통과",
        str(f["FILE_SN"]),
    )
    row = world.db.execute(
        text("SELECT MDFCN_DT m FROM TB_FILE WHERE FILE_SN=:f"), {"f": f["FILE_SN"]}
    ).scalar()
    assert row == START


def test_악성으로_탐지하면_차단하고_탐지_이름은_이력에_남기지_않는다(
    world: World, root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = stored(world, root, PDF + EICAR)
    with caplog.at_level(logging.DEBUG):
        assert scan(world, MockScanner(), root) == 1
    assert state(world, bad) == "FS.BLOCK"
    [job] = audit(world)
    assert job["CHG_CN"] == "차단" and "Mock" not in str(job) and "Signature" not in caplog.text


def test_올린_뒤_내용이_바뀐_파일은_검사하지_않고_차단한다(world: World, root: Path) -> None:
    tampered = stored(world, root, PDF + b"changed", hash_of=PDF)
    scanner = MockScanner()
    assert scan(world, scanner, root) == 1
    assert state(world, tampered) == "FS.BLOCK" and scanner.scanned == []


def test_검사기에_닿지_못하면_통과로_보지_않고_검사_대기로_두었다가_다음에_처리한다(
    world: World, root: Path
) -> None:
    f = stored(world, root)
    down = MockScanner(unavailable=True)
    assert scan(world, down, root) == 0 and state(world, f) == "FS.PENDING" and audit(world) == []
    assert scan(world, MockScanner(), root) == 1 and state(world, f) == "FS.SAFE"


def test_저장소에서_사라진_파일이_있어도_나머지는_계속_검사한다(world: World, root: Path) -> None:
    gone = stored(world, root, age=timedelta(hours=2))
    ok = stored(world, root, age=timedelta(hours=1))
    (
        root
        / str(
            world.db.execute(
                text("SELECT STRG_KEY FROM TB_FILE WHERE FILE_SN=:f"), {"f": gone["FILE_SN"]}
            ).scalar()
        )
    ).unlink()
    assert scan(world, MockScanner(), root) == 1
    assert (state(world, gone), state(world, ok)) == ("FS.PENDING", "FS.SAFE")  # 못 읽은 파일은 대기로 남는다


@pytest.mark.parametrize("status", ["FS.SAFE", "FS.BLOCK", "FS.DELETE"])
def test_검사_대기가_아닌_파일은_건드리지_않는다(world: World, root: Path, status: str) -> None:
    f = stored(world, root, status=status)
    scanner = MockScanner()
    assert scan(world, scanner, root) == 0 and state(world, f) == status and scanner.scanned == []


def test_오래_기다린_파일부터_한_번에_집는_수만큼_검사한다(
    world: World, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    newest = stored(world, root, age=timedelta(minutes=1))
    oldest = stored(world, root, age=timedelta(hours=3))
    middle = stored(world, root, age=timedelta(hours=1))
    monkeypatch.setattr(jobs, "BATCH", 2)
    assert scan(world, MockScanner(), root) == 2
    assert (state(world, oldest), state(world, middle), state(world, newest)) == (
        "FS.SAFE",
        "FS.SAFE",
        "FS.PENDING",
    )
    assert scan(world, MockScanner(), root) == 1


def test_검사하는_사이_삭제된_파일은_다시_통과로_바꾸지_않는다(world: World, root: Path) -> None:
    f = stored(world, root)
    world.db.commit()
    done = {"x": False}

    def clock_that_races() -> Any:
        if not done["x"]:  # 항목을 잠그기 직전에 다른 처리가 먼저 삭제한다
            done["x"] = True
            world.db.execute(
                text("UPDATE TB_FILE SET FILE_STTS_CD='FS.DELETE' WHERE FILE_SN=:f"), {"f": f["FILE_SN"]}
            )
        return world.clock()

    settings = replace(world.settings, file_root=str(root))
    assert jobs.scan_files(world.db, settings, MockScanner(), world.bundle, clock_that_races) == 0
    assert audit(world) == []


def test_올리기부터_검사와_내려받기까지_이어지고_악성_파일은_끝내_내려가지_않는다(
    world: World, root: Path
) -> None:
    target = _open_course(world, EDU_BGNG_YMD="20261201", EDU_END_YMD="20261231")
    other = _open_course(world, CORS_NM="탁구", EDU_BGNG_YMD="20261201", EDU_END_YMD="20261231")
    use(world, staff(world, "w", "AU.CORS_W"))
    good = upload(world, f"/courses/{target['CORS_SN']}/files", "정상.pdf").json()["fileId"]
    bad = upload(world, f"/courses/{other['CORS_SN']}/files", "악성.pdf", PDF + EICAR).json()["fileId"]
    assert call(world, "GET", f"/files/{good}/download").status_code == 404  # 검사 전에는 내려가지 않는다
    assert scan(world, MockScanner(), root) == 2
    assert call(world, "GET", f"/files/{good}/download").content == PDF
    assert call(world, "GET", f"/files/{bad}/download").status_code == 404
    assert call(world, "GET", f"/files/{bad}").json()["status"] == "BLOCK"
    assert call(world, "GET", f"/courses/{other['CORS_SN']}/files").json()["items"][0]["blockReason"] is None
