# 만족도 집계자료 등록·승인이 동시에 들어와도 버전이 겹치지 않고 같은 키는 한 번만 저장하며 한 자료는 한 번만 결정되는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app.domain.admin import satisfaction_input_service
from tests.arena import Arena, make_course, make_cycle, parallel
from tests.factory import RowFactory
from tests.test_admin_satisfaction_input import body
from tests.test_admin_stats_input_concurrent import second_session

pytestmark = pytest.mark.db

BASE = "/api/admin/v1/stats/satisfaction/sources"


def build(f: RowFactory) -> tuple[int, dict[str, Any]]:
    bundle = int(f.bundle())
    return bundle, make_course(f, bundle, make_cycle(f, bundle), "요가")


def post(
    client: Any, csrf: str, path: str, course: dict[str, Any] | None = None, key: str | None = None
) -> Any:
    headers = {"X-CSRF-Token": csrf, **({"Idempotency-Key": key} if key else {})}
    return lambda: client.post(path, json=body(course) if key and course else None, headers=headers)


def slow_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    real = satisfaction_input_service._validate

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)  # 최신 버전을 읽기 전 틈을 넓힌다
        return result

    monkeypatch.setattr(satisfaction_input_service, "_validate", slow)


def test_같은_강좌·계열의_동시_등록은_버전이_겹치지_않는다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, course = arena.build(build)
    arena.serve(bundle)
    one = arena.staff(bundle, "sat-a", "AU.CONF_W")
    two = arena.staff(bundle, "sat-b", "AU.CONF_W")
    slow_validate(monkeypatch)
    responses = parallel(
        [
            post(one.client, one.csrf, BASE, course, "conc-key-0001"),
            post(two.client, two.csrf, BASE, course, "conc-key-0002"),
        ]
    )
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert sorted(r.json()["version"] for r in responses) == [1, 2]
    assert len(arena.query("SELECT 1 FROM TB_CORS_DGSTFN_SRC WHERE OPER_BNDL_SN=:b", b=bundle)) == 2


def test_같은_키의_동시_등록은_한_번만_저장한다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, course = arena.build(build)
    arena.serve(bundle)
    one = arena.staff(bundle, "sat-c", "AU.CONF_W")
    client, csrf = second_session(arena, one.admin_sn)
    slow_validate(monkeypatch)
    responses = parallel(
        [
            post(one.client, one.csrf, BASE, course, "same-key-conc"),
            post(client, csrf, BASE, course, "same-key-conc"),
        ]
    )
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert len({r.json()["sourceId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_CORS_DGSTFN_SRC WHERE OPER_BNDL_SN=:b", b=bundle)) == 1
    assert len(arena.query("SELECT 1 FROM TB_CORS_DGSTFN_QITEM WHERE OPER_BNDL_SN=:b", b=bundle)) == 3


def test_동시에_승인과_반려를_해도_한_번만_결정한다(arena: Arena) -> None:
    bundle, course = arena.build(build)
    arena.serve(bundle)
    maker = arena.staff(bundle, "sat-d", "AU.CONF_W")
    boss1 = arena.staff(bundle, "sat-e", "AU.GRANT_W")
    boss2 = arena.staff(bundle, "sat-f", "AU.GRANT_W")
    made = post(maker.client, maker.csrf, BASE, course, "decide-key-01")()
    assert made.status_code == 201, made.text
    path = f"{BASE}/{made.json()['sourceId']}"
    responses = parallel(
        [post(boss1.client, boss1.csrf, f"{path}/approve"), post(boss2.client, boss2.csrf, f"{path}/reject")]
    )
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    decided = arena.query(
        "SELECT 1 FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='SATISFACTION_SRC_DECIDE'", b=bundle
    )
    assert len(decided) == 1
