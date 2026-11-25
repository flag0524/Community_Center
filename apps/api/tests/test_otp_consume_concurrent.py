# ruff: noqa: SIM300
# 실제 가입·복구의 인증 소비와 다른 연결의 재발급을 함께 실행한다.
import hashlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from typing import Any

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError

from app.adapters.sms.mock import MockSmsSender
from app.auth import join, recovery
from app.auth.otp import issue_otp
from app.core.errors import ApiError, ErrorCode
from app.db import tables
from app.db.session import open_session
from app.domain.admin import retention_service
from app.domain.admin.retention_types import RetentionTarget
from app.domain.member.schemas import AgreementItem
from app.domain.member.types import OtpPurpose, TermType
from tests.arena import Arena
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db


def assert_bundle_locked(arena: Arena, bundle: int) -> None:
    with open_session(arena.engine) as probe:
        with pytest.raises(OperationalError) as caught:
            probe.execute(
                select(tables.TB_OPER_BNDL.c.OPER_BNDL_SN)
                .where(tables.TB_OPER_BNDL.c.OPER_BNDL_SN == bundle)
                .with_for_update(nowait=True)
            )
        assert caught.value.orig is not None
        assert caught.value.orig.args[0] in (1205, 3572)
        probe.rollback()


@pytest.mark.parametrize("purpose", [OtpPurpose.JOIN, OtpPurpose.ID_FIND, OtpPurpose.PASSWORD_RESET])
def test_인증_소비와_재발급이_겹쳐도_가입과_복구가_완료된다(
    otp_arena: Arena, monkeypatch: pytest.MonkeyPatch, purpose: OtpPurpose
) -> None:
    arena = otp_arena
    phone, name = "01012345678", "검증회원"

    def build(f: RowFactory) -> int:
        # build는 호출마다 새 운영묶음을 만든다. 같은 묶음에 행을 더하려면 한 번의 build 안에서 만든다
        bundle_sn = f.bundle()
        if purpose is OtpPurpose.JOIN:
            f.make(
                "TB_SITE_CONTS",
                OPER_BNDL_SN=bundle_sn,
                CONTS_TYPE_CD="CT.TERMS",
                CONTS_ID="terms",
                CONTS_CN="약관",
                CONTS_HASH_VL=hashlib.sha256("약관".encode()).hexdigest(),
                VER_NM="v1",
                PSTG_YN="Y",
                ESNTL_YN="Y",
            )
        else:
            f.make("TB_MBR", OPER_BNDL_SN=bundle_sn, LGN_ID=f"otp-{bundle_sn}", MBR_NM=name, MBL_TELNO=phone)
        return bundle_sn

    bundle = arena.build(build)
    login_id = f"otp-{bundle}"
    sender = MockSmsSender()
    with open_session(arena.engine) as db:
        issued = issue_otp(
            db,
            arena.settings,
            sender,
            bundle_sn=bundle,
            purpose=purpose,
            phone=phone,
            name=name,
            login_id=login_id,
            request_id=uuid.uuid4().hex,
            now=START,
        )
        db.commit()
    match = re.search(r"(?<!\d)\d{6}(?!\d)", sender.outbox[0].text)
    assert match is not None
    code = match.group()
    locked, release, resend_started = Event(), Event(), Event()
    module = join if purpose is OtpPurpose.JOIN else recovery
    original = module.consume_otp

    def pause_after_consume(*args: Any, **kwargs: Any) -> Any:
        row = original(*args, **kwargs)
        locked.set()
        assert release.wait(10), "소비 재개 신호 누락"
        return row

    monkeypatch.setattr(module, "consume_otp", pause_after_consume)

    def consume() -> None:
        with open_session(arena.engine) as db:
            db.execute(text("SET SESSION innodb_lock_wait_timeout=3"))
            common: dict[str, Any] = dict(
                bundle_sn=bundle,
                cert_id=issued.cert_id,
                code=code,
                request_id=uuid.uuid4().hex,
                now=START,
            )
            if purpose is OtpPurpose.JOIN:
                join.join_member(
                    db,
                    arena.settings,
                    **common,
                    login_id=login_id,
                    password="Strong-Pass-12",
                    email="otp@example.invalid",
                    agreements=[AgreementItem(term_type=TermType.TERMS_OF_USE, version="v1", agreed=True)],
                )
            elif purpose is OtpPurpose.ID_FIND:
                assert recovery.find_login_id(db, arena.settings, **common) is not None
            else:
                assert recovery.reset_password(
                    db, arena.settings, **common, login_id=login_id, new_password="Brand-New-Pass-77"
                )
            db.commit()

    def resend() -> ErrorCode:
        with open_session(arena.engine) as db:
            connection = db.connection()

            def before_execute(
                conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
            ) -> None:
                if "TB_OPER_BNDL" in statement and "FOR UPDATE" in statement:
                    resend_started.set()

            event.listen(connection, "before_cursor_execute", before_execute)
            try:
                issue_otp(
                    db,
                    arena.settings,
                    sender,
                    bundle_sn=bundle,
                    purpose=purpose,
                    phone=phone,
                    name=name,
                    login_id=login_id,
                    request_id=uuid.uuid4().hex,
                    now=START,
                )
                pytest.fail("같은 번호의 재발급이 허용됨")
            except ApiError as error:
                db.rollback()
                return error.code
            finally:
                event.remove(connection, "before_cursor_execute", before_execute)

    with ThreadPoolExecutor(2) as pool:
        consuming = pool.submit(consume)
        try:
            assert locked.wait(10), "인증 소비 시작 실패"
            # 인증 행을 쥔 소비자가 부모 행도 먼저 잠갔는지 별도 연결에서 증명한다.
            assert_bundle_locked(arena, bundle)
            resending = pool.submit(resend)
            assert resend_started.wait(10), "재발급 시작 실패"
        finally:
            release.set()
        consuming.result(timeout=10)
        assert resending.result(timeout=10) is ErrorCode.OTP_RESEND_TOO_SOON
    with open_session(arena.engine) as db:
        used = db.execute(
            select(tables.TB_CERT_DMND.c.CERT_USE_CMPTN_DT).where(
                tables.TB_CERT_DMND.c.CERT_DMND_SN == issued.cert_sn
            )
        ).scalar_one()
        assert used is not None
    assert len(sender.outbox) == 1


# 관리자 실행과 일일 워커가 공유하는 실제 _due_keys/삭제/감사 경로를 사용한다.
def test_인증기록_파기와_새_발급도_같은_잠금_순서로_완료된다(
    otp_arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    arena = otp_arena
    bundle = arena.build(lambda f: f.bundle())
    phone, sender = "01012345678", MockSmsSender()
    with open_session(arena.engine) as db:
        old = issue_otp(
            db,
            arena.settings,
            sender,
            bundle_sn=bundle,
            purpose=OtpPurpose.ID_FIND,
            phone=phone,
            name="없는회원",
            login_id=None,
            request_id=uuid.uuid4().hex,
            now=START - timedelta(days=31),
        )
        db.commit()
    assert sender.outbox == []
    locked, release, issuing_started = Event(), Event(), Event()
    original = retention_service._due_keys

    def pause_after_lock(*args: Any, **kwargs: Any) -> Any:
        keys = original(*args, **kwargs)
        assert keys == [old.cert_sn]
        locked.set()
        assert release.wait(10), "파기 재개 신호 누락"
        return keys

    monkeypatch.setattr(retention_service, "_due_keys", pause_after_lock)

    def purge() -> int:
        with open_session(arena.engine) as db:
            db.execute(text("SET SESSION innodb_lock_wait_timeout=3"))
            count = retention_service.purge_target(
                db, bundle, RetentionTarget.AUTH_RECORDS, now=START, request_id=uuid.uuid4().hex
            )
            db.commit()
            return count

    def issue() -> int:
        with open_session(arena.engine) as db:
            connection = db.connection()

            def before_execute(
                conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
            ) -> None:
                if "TB_OPER_BNDL" in statement and "FOR UPDATE" in statement:
                    issuing_started.set()

            event.listen(connection, "before_cursor_execute", before_execute)
            try:
                issued = issue_otp(
                    db,
                    arena.settings,
                    sender,
                    bundle_sn=bundle,
                    purpose=OtpPurpose.JOIN,
                    phone=phone,
                    name="신규회원",
                    login_id=None,
                    request_id=uuid.uuid4().hex,
                    now=START,
                )
                db.commit()
                return issued.cert_sn
            finally:
                event.remove(connection, "before_cursor_execute", before_execute)

    with ThreadPoolExecutor(2) as pool:
        purging = pool.submit(purge)
        try:
            assert locked.wait(10), "인증기록 파기 시작 실패"
            assert_bundle_locked(arena, bundle)
            issuing = pool.submit(issue)
            assert issuing_started.wait(10), "신규 발급 시작 실패"
        finally:
            release.set()
        assert purging.result(timeout=10) == 1
        new_sn = issuing.result(timeout=10)
    with open_session(arena.engine) as db:
        ids = (
            db.execute(
                select(tables.TB_CERT_DMND.c.CERT_DMND_SN).where(tables.TB_CERT_DMND.c.OPER_BNDL_SN == bundle)
            )
            .scalars()
            .all()
        )
        assert ids == [new_sn]
    assert len(sender.outbox) == 1
