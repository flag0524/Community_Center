# ruff: noqa: SIM300
# 실제 MariaDB의 묶음 행 잠금이 여러 연결의 OTP 동시 발급을 한 번으로 제한하는지 검증한다
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import select, text

from app.adapters.sms.mock import MockSmsSender
from app.auth.otp import issue_otp
from app.core.errors import ApiError
from app.db import tables
from app.db.session import open_session
from app.domain.member.types import OtpPurpose
from tests.arena import Arena, parallel
from tests.world import START

pytestmark = pytest.mark.db


def attempt(
    arena: Arena,
    sender: MockSmsSender,
    bundle: int,
    phone: str,
    purpose: OtpPurpose = OtpPurpose.JOIN,
    ready: Barrier | None = None,
    now: datetime = START,
) -> Callable[[], str]:
    def run() -> str:
        with open_session(arena.engine) as db:
            try:
                if ready is not None:
                    # RR에서는 앞선 조회의 스냅샷을 만들고, RC에서도 동일한 경합을 실행한다.
                    db.execute(text("SELECT COUNT(*) FROM TB_CERT_DMND")).scalar_one()
                    ready.wait(timeout=10)
                issued = issue_otp(
                    db,
                    arena.settings,
                    sender,
                    bundle_sn=bundle,
                    purpose=purpose,
                    phone=phone,
                    name="동시회원",
                    login_id="absent",
                    request_id=uuid.uuid4().hex,
                    now=now,
                )
                db.commit()
                return str(issued.cert_sn)
            except ApiError as error:
                db.rollback()
                return error.code.value

    return run


def test_새_브라우저_6개가_같은_번호를_요청해도_한_건만_발급한다(otp_arena: Arena) -> None:
    arena = otp_arena
    bundle = arena.build(lambda f: f.bundle())
    sender = MockSmsSender()
    ready = Barrier(6)
    results = parallel([attempt(arena, sender, bundle, "01012345678", ready=ready) for _ in range(6)])
    assert sum(r.isdigit() for r in results) == 1
    assert results.count("OTP_RESEND_TOO_SOON") == 5 and len(sender.outbox) == 1
    assert arena.query("SELECT COUNT(*) n FROM TB_CERT_DMND WHERE OPER_BNDL_SN=:b", b=bundle)[0]["n"] == 1


def test_가입과_아이디찾기와_비밀번호재설정도_같은_번호_제한을_공유한다(otp_arena: Arena) -> None:
    arena = otp_arena
    bundle = arena.build(lambda f: f.bundle())
    sender = MockSmsSender()
    purposes = [OtpPurpose.JOIN, OtpPurpose.ID_FIND, OtpPurpose.PASSWORD_RESET] * 2
    results = parallel([attempt(arena, sender, bundle, "01012345678", purpose) for purpose in purposes])
    assert sum(r.isdigit() for r in results) == 1
    assert results.count("OTP_RESEND_TOO_SOON") == 5 and len(sender.outbox) <= 1


def test_서로_다른_번호의_동시_요청은_모두_발급한다(otp_arena: Arena) -> None:
    arena = otp_arena
    bundle = arena.build(lambda f: f.bundle())
    sender = MockSmsSender()
    results = parallel([attempt(arena, sender, bundle, f"0101234567{i}") for i in range(3)])
    assert all(r.isdigit() for r in results) and len(set(results)) == 3 and len(sender.outbox) == 3


def test_소수초_발급_시각이_DB에_보존되고_60초_전에_재발급되지_않는다(otp_arena: Arena) -> None:
    arena = otp_arena
    bundle = arena.build(lambda f: f.bundle())
    sender = MockSmsSender()
    origin = START + timedelta(microseconds=900000)
    first = attempt(arena, sender, bundle, "01012345678", now=origin)()
    assert first.isdigit()
    with arena.engine.connect() as connection:
        stored = connection.execute(
            select(tables.TB_CERT_DMND.c.REG_DT).where(tables.TB_CERT_DMND.c.CERT_DMND_SN == int(first))
        ).scalar_one()
    assert stored == origin
    assert (
        attempt(arena, sender, bundle, "01012345678", now=START + timedelta(seconds=60))()
        == "OTP_RESEND_TOO_SOON"
    )
    second = attempt(arena, sender, bundle, "01012345678", now=origin + timedelta(seconds=60))()
    assert second.isdigit() and len(sender.outbox) == 2
