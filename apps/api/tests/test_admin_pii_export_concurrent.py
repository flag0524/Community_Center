# 같은 멱등키의 개인식별 명단 요청이 동시에 와도 한 번만 만들어 주는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.admin import pii_export
from tests.arena import Arena, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> int:
    bundle = f.bundle()
    member = make_member(f, bundle, "payer")
    course = make_course(f, bundle, make_cycle(f, bundle), "강좌", EDU_BGNG_YMD="20261201")
    make_application(f, bundle, member, course, "ES.CONFIRM")
    return bundle


def test_같은_멱등키를_동시에_보내도_암호화_파일은_한_번만_만든다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = pii_export.build_zip

    def slow(*args: str | bytes) -> bytes:
        time.sleep(0.3)  # 확인과 기록 사이의 틈을 넓혀 잠금이 없으면 겹치게 한다
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(pii_export, "build_zip", slow)
    bundle = arena.build(build)
    arena.serve(bundle)
    who = arena.staff(bundle, "s1", "AU.EXPORT", "AU.APLY_R")
    headers = {"X-CSRF-Token": who.csrf, "Idempotency-Key": "same-key-0001"}
    clients: list[TestClient] = []
    for _ in range(
        4
    ):  # 같은 담당자의 세션을 쓰는 서로 다른 연결. 한 연결을 공유하면 요청이 순서대로 처리된다
        c = TestClient(arena.app, base_url="https://testserver", raise_server_exceptions=False)
        c.cookies.update(who.client.cookies)
        clients.append(c)

    def sender(c: TestClient) -> Callable[[], Any]:
        return lambda: c.post(f"{ADMIN}/exports/pii", json={"target": "APPLICATIONS"}, headers=headers)

    calls = [sender(c) for c in clients]
    codes = sorted(r.status_code for r in parallel(calls))
    assert codes == [200, 409, 409, 409], codes
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='PII_EXPORT'")) == 1
