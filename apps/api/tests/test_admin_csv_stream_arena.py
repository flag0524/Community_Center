# 내보내기 감사 기록이 본문 스트리밍 시작 전에 실제로 커밋되는지 실제 MariaDB 연결로 확인하는 시험
from collections.abc import Iterator
from typing import Any

import pytest

from app.domain.admin import csv_export
from tests.arena import Arena, make_application, make_course, make_cycle, make_member
from tests.factory import RowFactory

pytestmark = pytest.mark.db


def _setup(arena: Arena) -> int:
    def make(f: RowFactory) -> int:
        bundle = f.bundle()
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌")
        make_application(f, bundle, make_member(f, bundle, "csv-stream"), course, "ES.CONFIRM")
        return bundle

    bundle = arena.build(make)
    arena.serve(bundle)
    return int(bundle)


def test_본문_전송이_중간에_실패해도_감사_기록은_이미_확정돼_있다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _setup(arena)

    def broken(*args: Any, **kwargs: Any) -> Iterator[bytes]:
        yield b"\xef\xbb\xbf"
        raise RuntimeError("전송 중 실패")

    monkeypatch.setattr(csv_export, "_stream", broken)
    who = arena.staff(bundle, "csv-boss", "AU.APLY_R")
    who.client.get("/api/admin/v1/applications/export.csv", headers={"X-CSRF-Token": who.csrf})
    # 요청 뒤의 롤백이 감사 기록을 지우지 못한다. 본문보다 먼저 커밋했기 때문이다
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'CSV_EXPORT'")) == 1


def test_한도를_넘으면_감사_기록도_남지_않는다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _setup(arena)
    monkeypatch.setattr(csv_export, "MAX_ROWS", 0)
    who = arena.staff(bundle, "csv-boss2", "AU.APLY_R")
    response = who.client.get("/api/admin/v1/applications/export.csv", headers={"X-CSRF-Token": who.csrf})
    assert response.status_code == 422
    assert arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'CSV_EXPORT'") == []
