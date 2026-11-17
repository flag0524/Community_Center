# 검사 워커가 clamd 어댑터로 파일을 통과·차단·보류하는 흐름을 가짜 clamd와 실제 MariaDB로 확인하는 시험
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.adapters.scan.clamd import ClamdScanner
from app.worker import jobs
from tests.test_files_scan import state, stored
from tests.test_scan_clamd import FakeClamd
from tests.world import World

pytestmark = pytest.mark.db


def run_scan(w: World, fake: FakeClamd, root: Path) -> int:
    w.db.commit()
    scanner = ClamdScanner("127.0.0.1", fake.port, timeout_seconds=1)
    return jobs.scan_files(w.db, replace(w.settings, file_root=str(root)), scanner, w.bundle, w.clock)


def test_통과하면_안전_탐지하면_차단이고_저장소의_내용을_그대로_보낸다(world: World, tmp_path: Path) -> None:
    good = FakeClamd()
    clean = stored(world, tmp_path, b"%PDF-1.7 clean")
    assert run_scan(world, good, tmp_path) == 1
    assert state(world, clean) == "FS.SAFE" and good.received == b"%PDF-1.7 clean"
    good.close()
    bad = FakeClamd(reply=b"stream: Some.Virus FOUND\0")
    infected = stored(world, tmp_path, b"%PDF-1.7 infected")
    run_scan(world, bad, tmp_path)
    assert state(world, infected) == "FS.BLOCK"
    bad.close()


def test_검사기가_오류를_내면_통과시키지_않고_검사_대기로_둔다(world: World, tmp_path: Path) -> None:
    fake: Any = FakeClamd(reply=b"INSTREAM size limit exceeded. ERROR\0")
    pending = stored(world, tmp_path)
    run_scan(world, fake, tmp_path)
    assert state(world, pending) == "FS.PENDING"
    fake.close()
