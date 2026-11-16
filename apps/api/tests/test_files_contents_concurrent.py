# 같은 배너에 이미지를 동시에 올려도 한 장만 남는지 서로 다른 DB 연결로 확인하는 시험
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.domain.admin import file_service
from tests.arena import Arena, Staff, parallel

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"image"
JPG = b"\xff\xd8\xff\xe0" + b"jpeg-image"


def build(f: Any) -> tuple[int, int]:
    bundle = f.bundle()
    banner = f.make(
        "TB_SITE_CONTS",
        OPER_BNDL_SN=bundle,
        CONTS_TYPE_CD="CT.BANNER",
        CONTS_ID="banner-1",
        CONTS_TTL="배너",
        CONTS_CN="본문",
        VER_NM="v1",
        PSTG_YN="Y",
    )
    return bundle, int(banner["SITE_CONTS_SN"])


def send(who: Staff, banner: int, name: str, data: bytes, key: str) -> Any:
    return who.client.post(
        f"/api/admin/v1/contents/{banner}/files",
        files={"file": (name, data, "application/octet-stream")},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key},
    )


def test_다른_키로_동시에_올려도_배너_이미지는_한_장만_남는다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle, banner = arena.build(build)
    arena.settings = replace(arena.settings, file_root=str(tmp_path))
    arena.serve(bundle)
    real = file_service.lock_owner

    def slow(*args: Any) -> Any:
        real(*args)
        time.sleep(0.5)  # 잠근 뒤에 머물러 개수 검사가 잠금 밖에서 겹치는지 드러낸다

    monkeypatch.setattr(file_service, "lock_owner", slow)
    one, two = arena.staff(bundle, "e1", "AU.SITE_W"), arena.staff(bundle, "e2", "AU.SITE_W")
    responses = parallel(
        [
            lambda: send(one, banner, "a.png", PNG, "file-conc-0001"),
            lambda: send(two, banner, "b.jpg", JPG, "file-conc-0002"),
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    live = arena.query(
        "SELECT 1 FROM TB_FILE WHERE SITE_CONTS_SN=:c AND FILE_STTS_CD <> 'FS.DELETE'", c=banner
    )
    assert len(live) == 1
