# 집계자료 등록·승인이 동시에 들어와도 버전이 겹치지 않고 같은 키는 한 번만 저장하며 한 자료는 한 번만 결정되는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import session_csrf
from app.auth.sessions import issue_session
from app.db.session import open_session
from app.domain.admin import stats_input_service
from app.routers.deps import ADMIN_SESSION_COOKIE_NAME
from tests.arena import Arena, parallel
from tests.test_admin_stats_input import body
from tests.world import START

pytestmark = pytest.mark.db

BASE = "/api/admin/v1/stats/age-gender/sources"


def second_session(arena: Arena, admin_sn: int) -> tuple[TestClient, str]:
    """같은 담당자의 두 번째 세션과 그 CSRF 토큰."""
    with open_session(arena.engine) as session:
        token, record = issue_session(session, bundle_sn=None, member_sn=None, admin_sn=admin_sn, now=START)
        session.commit()
    client = TestClient(arena.app, base_url="https://testserver", raise_server_exceptions=False)
    client.cookies.set(ADMIN_SESSION_COOKIE_NAME, token)
    return client, session_csrf(arena.settings, record)


def post(client: TestClient, csrf: str, path: str, key: str | None = None, **values: Any) -> Any:
    headers = {"X-CSRF-Token": csrf, **({"Idempotency-Key": key} if key else {})}
    return lambda: client.post(path, json=body(**values) if key else None, headers=headers)


def test_같은_계열의_동시_등록은_버전이_겹치지_않는다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = arena.build(lambda f: int(f.bundle()))
    arena.serve(bundle)
    one = arena.staff(bundle, "reg-a", "AU.CONF_W")
    two = arena.staff(bundle, "reg-b", "AU.CONF_W")
    real = stats_input_service._validate

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)  # 서로 같은 최신 버전을 읽기 쉬운 틈을 넓힌다
        return result

    monkeypatch.setattr(stats_input_service, "_validate", slow)
    responses = parallel(
        [post(one.client, one.csrf, BASE, "conc-key-0001"), post(two.client, two.csrf, BASE, "conc-key-0002")]
    )
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert sorted(r.json()["version"] for r in responses) == [1, 2]
    assert len(arena.query("SELECT 1 FROM TB_MBR_STATS_SRC WHERE OPER_BNDL_SN=:b", b=bundle)) == 2


def test_같은_키의_동시_등록은_한_번만_저장한다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = arena.build(lambda f: int(f.bundle()))
    arena.serve(bundle)
    one = arena.staff(bundle, "reg-c", "AU.CONF_W")
    client, csrf = second_session(arena, one.admin_sn)
    real = stats_input_service._validate

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)
        return result

    monkeypatch.setattr(stats_input_service, "_validate", slow)
    responses = parallel(
        [post(one.client, one.csrf, BASE, "same-key-conc"), post(client, csrf, BASE, "same-key-conc")]
    )
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert len({r.json()["sourceId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_MBR_STATS_SRC WHERE OPER_BNDL_SN=:b", b=bundle)) == 1
    assert len(arena.query("SELECT 1 FROM TB_MBR_STATS_TOT WHERE OPER_BNDL_SN=:b", b=bundle)) == 4


def test_동시에_승인과_반려를_해도_한_번만_결정한다(arena: Arena) -> None:
    bundle = arena.build(lambda f: int(f.bundle()))
    arena.serve(bundle)
    maker = arena.staff(bundle, "reg-d", "AU.CONF_W")
    boss1 = arena.staff(bundle, "boss-a", "AU.GRANT_W")
    boss2 = arena.staff(bundle, "boss-b", "AU.GRANT_W")
    made = post(maker.client, maker.csrf, BASE, "decide-key-01")()
    assert made.status_code == 201, made.text
    path = f"{BASE}/{made.json()['sourceId']}"
    responses = parallel(
        [post(boss1.client, boss1.csrf, f"{path}/approve"), post(boss2.client, boss2.csrf, f"{path}/reject")]
    )
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    assert (
        len(
            arena.query(
                "SELECT 1 FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='STATS_SRC_DECIDE'", b=bundle
            )
        )
        == 1
    )
