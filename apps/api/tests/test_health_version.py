# 배포 검증용 /api/health/version(커밋·리비전·코드표 체크섬·설정 해시)을 실제 MariaDB로 확인하는 시험
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db.session import get_db
from tests.world import World

pytestmark = pytest.mark.db


def with_settings(w: World, **values: Any) -> None:
    settings = replace(w.settings, **values)
    w.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]


def version(w: World) -> dict[str, Any]:
    response = w.client.get("/api/health/version")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_인증_없이_커밋과_마이그레이션_리비전과_코드_수를_준다(world: World) -> None:
    with_settings(world, build_commit="abc1234")
    body = version(world)
    assert body["commit"] == "abc1234"
    assert body["migration"] == "0004"
    assert body["codeCount"] == 187
    assert len(body["codeSetChecksum"]) == 64 and len(body["configHash"]) == 64


def test_커밋을_알리지_않으면_unknown이다(world: World) -> None:
    assert version(world)["commit"] == "unknown"


def test_코드표_체크섬은_코드가_늘면_바뀌고_표시명을_고쳐도_그대로다(world: World) -> None:
    before = version(world)
    world.db.execute(text("UPDATE TB_COM_CD SET CD_NM='바꾼 이름' WHERE COM_CD='CT.VISUAL'"))
    renamed = version(world)
    assert renamed["codeSetChecksum"] == before["codeSetChecksum"] and renamed["codeCount"] == 187
    world.factory.make("TB_COM_CD")
    added = version(world)
    assert added["codeCount"] == 188 and added["codeSetChecksum"] != before["codeSetChecksum"]


def test_설정_해시는_공개_설정이_다르면_바뀌고_비밀값에는_영향받지_않으며_응답에_비밀이_없다(
    world: World,
) -> None:
    base = version(world)["configHash"]
    with_settings(world, secret_key="다른 비밀키 " + "y" * 40, database_url="mysql+pymysql://x:secret@h/db")
    same = world.client.get("/api/health/version")
    assert same.json()["configHash"] == base
    assert "다른 비밀키" not in same.text and "secret" not in same.text
    with_settings(world, pg_provider="other-pg")
    assert version(world)["configHash"] != base
    with_settings(world, site_id="another-site")
    assert version(world)["configHash"] != base


class BrokenSession:
    """읽기가 실패하는 세션. 실제 테이블을 바꾸지 않고(DDL은 되돌릴 수 없다) DB 장애를 흉내 낸다."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("연결 끊김"))


def test_DB를_읽을_수_없으면_503이다(world: World) -> None:
    world.client.app.dependency_overrides[get_db] = lambda: BrokenSession()  # type: ignore[attr-defined]
    response = world.client.get("/api/health/version")
    assert response.status_code == 503 and response.json() == {"status": "degraded", "database": False}
