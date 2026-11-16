# 같은 담당자의 같은 문자 발송 요청이 동시에 두 번 들어와도 요청과 수신명단이 한 번만 저장되는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import session_csrf
from app.auth.sessions import issue_session
from app.db.session import open_session
from app.domain.admin import sms_service
from app.routers.deps import ADMIN_SESSION_COOKIE_NAME
from tests.arena import Arena, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> int:
    bundle = f.bundle()
    course = make_course(f, bundle, make_cycle(f, bundle), "요가")
    for n in range(3):
        make_application(f, bundle, make_member(f, bundle, f"sm{n}"), course, "ES.CONFIRM")
    return bundle


def test_같은_키의_동시_발송은_요청과_명단을_한_번만_저장한다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = arena.build(build)
    arena.serve(bundle)
    one = arena.staff(bundle, "sender", "AU.SMS_SEND")
    with open_session(arena.engine) as session:  # 같은 담당자의 두 번째 세션
        token, record = issue_session(
            session, bundle_sn=None, member_sn=None, admin_sn=one.admin_sn, now=START
        )
        session.commit()
    second = TestClient(arena.app, base_url="https://testserver", raise_server_exceptions=False)
    second.cookies.set(ADMIN_SESSION_COOKIE_NAME, token)
    csrf = session_csrf(arena.settings, record)
    real = sms_service._audience

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)  # 대상을 산정하고 저장하기 전의 틈을 넓힌다. 키 유일 제약이 없으면 둘 다 저장한다
        return result

    monkeypatch.setattr(sms_service, "_audience", slow)
    payload = {
        "scope": "CENTER",
        "courseIds": [],
        "statuses": ["CONFIRMED"],
        "content": "[조리읍] 수강 안내입니다.",
        "confirmed": True,
        "expectedRecipientCount": 3,
    }

    def send(client: TestClient, token_: str) -> Any:
        return lambda: client.post(
            f"{ADMIN}/sms", json=payload, headers={"X-CSRF-Token": token_, "Idempotency-Key": "sms-conc-0001"}
        )

    responses = parallel([send(one.client, one.csrf), send(second, csrf)])
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert len({r.json()["smsId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_SMS_DMND WHERE OPER_BNDL_SN=:b", b=bundle)) == 1
    assert len(arena.query("SELECT 1 FROM TB_SMS_TRGT WHERE OPER_BNDL_SN=:b", b=bundle)) == 3
