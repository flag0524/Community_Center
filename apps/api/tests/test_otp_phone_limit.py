# SQLite로 실제 서비스 SQL·전화번호 검색키·시간 경계를 검증한다. MariaDB 행 잠금 경합은 별도 시험이다
import hashlib
import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Column, DefaultClause, Integer, MetaData, Table, create_engine, select, text
from sqlalchemy.orm import Session

from app.adapters.sms.base import SmsResult
from app.adapters.sms.mock import MockSmsSender
from app.auth.otp import issue_otp, phone_hash
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db import tables
from app.domain.member.types import OtpPurpose

NOW = datetime(2026, 11, 19, 7)
PHONE = "01012345678"
World = tuple[Session, Settings, MockSmsSender]


@pytest.fixture
def world() -> Iterator[World]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    names = ("TB_OPER_BNDL", "TB_MBR", "TB_CERT_DMND", "TB_SMS_DMND", "TB_SMS_TRGT", "TB_SMS_SNDNG_HSTRY")
    # 서비스의 검색·저장을 검증한다. MariaDB 제약은 별도 시험하고 PK만 SQLite 자동 채번으로 바꾼다.
    for name in names:
        Table(
            name,
            metadata,
            *(
                Column(
                    column.name,
                    Integer() if column.primary_key else column.type,
                    primary_key=column.primary_key,
                    nullable=not column.primary_key,
                    server_default=None
                    if column.primary_key or not isinstance(column.server_default, DefaultClause)
                    else text(str(column.server_default.arg)),
                )
                for column in tables.metadata.tables[name].columns
            ),
        )
    metadata.create_all(engine)
    with Session(engine) as db:
        db.execute(tables.TB_OPER_BNDL.insert().values(OPER_BNDL_SN=1, OPER_BNDL_NM="시험센터"))
        db.execute(tables.TB_OPER_BNDL.insert().values(OPER_BNDL_SN=2, OPER_BNDL_NM="다른센터"))
        db.commit()
        yield db, Settings(database_url="unused", site_id="test", secret_key="s" * 40), MockSmsSender()
    engine.dispose()


def issue(
    world: World,
    *,
    phone: str = PHONE,
    purpose: OtpPurpose = OtpPurpose.JOIN,
    bundle: int = 1,
    now: datetime = NOW,
) -> None:
    db, settings, sender = world
    try:
        issue_otp(
            db,
            settings,
            sender,
            bundle_sn=bundle,
            purpose=purpose,
            phone=phone,
            name="검증회원",
            login_id="test-member",
            request_id=uuid.uuid4().hex,
            now=now,
        )
        db.commit()
    except ApiError:
        db.rollback()
        raise


def test_검색키는_용도별_비밀키_HMAC이고_원문과_단순_해시가_아니다() -> None:
    digest = phone_hash("s" * 40, PHONE)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert PHONE not in digest and digest != hashlib.sha256(PHONE.encode()).hexdigest()
    assert digest == phone_hash("s" * 40, PHONE)
    assert digest != phone_hash("t" * 40, PHONE)
    assert digest != phone_hash("s" * 40, "01099998888")


@pytest.mark.parametrize("phone", ["010-1234-5678", " 01012345678", "０１０１２３４５６７８", "123"])
def test_비정규_전화번호는_원문을_노출하지_않고_거절한다(phone: str) -> None:
    with pytest.raises(ApiError) as caught:
        phone_hash("s" * 40, phone)
    assert caught.value.code is ErrorCode.VALIDATION_FAILED and phone not in caught.value.message


@pytest.mark.parametrize("seconds", [0, 59, 59.999999, 60, 61])
def test_60초_미만만_차단하고_정확히_60초부터_허용한다(world: World, seconds: float) -> None:
    issue(world)
    if seconds < 60:
        with pytest.raises(ApiError) as caught:
            issue(world, now=NOW + timedelta(seconds=seconds))
        assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON
        assert len(world[2].outbox) == 1
    else:
        issue(world, now=NOW + timedelta(seconds=seconds))
        assert len(world[2].outbox) == 2


@pytest.mark.parametrize("purpose", list(OtpPurpose)[:3])
def test_같은_번호는_목적을_바꿔도_다시_발급하지_않는다(world: World, purpose: OtpPurpose) -> None:
    issue(world)
    with pytest.raises(ApiError) as caught:
        issue(world, purpose=purpose)
    assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON
    assert len(world[2].outbox) == 1


def test_회원이_없는_가짜_요청도_번호_제한을_남긴다(world: World) -> None:
    issue(world, purpose=OtpPurpose.ID_FIND)
    assert world[2].outbox == []
    with pytest.raises(ApiError) as caught:
        issue(world)
    assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON and world[2].outbox == []


def test_다른_번호와_다른_묶음은_독립적으로_발급한다(world: World) -> None:
    issue(world)
    issue(world, phone="01099998888")
    issue(world, bundle=2)
    assert len(world[2].outbox) == 3


def test_인증을_사용_완료해도_재전송_제한은_남는다(world: World) -> None:
    issue(world)
    db, _, _ = world
    db.execute(tables.TB_CERT_DMND.update().values(CERT_USE_CMPTN_DT=NOW))
    db.commit()
    with pytest.raises(ApiError) as caught:
        issue(world)
    assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON


def test_저장된_검색키는_응답용_아이디나_암호문과_구분된다(world: World) -> None:
    issue(world)
    db, settings, _ = world
    row = db.execute(select(tables.TB_CERT_DMND)).one()
    assert phone_hash(settings.secret_key, PHONE) == row.TELNO_SRCH_HASH_VL
    assert row.TELNO_ENCPT_VL != row.TELNO_SRCH_HASH_VL and row.KEY_VER_ID == "v1"


def test_SMS는_발급_커밋_뒤에_호출한다(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    db, _, sender = world
    original = sender.send

    def checked_send(*, to: str, text: str, sender: str) -> SmsResult:
        assert not db.in_transaction()
        return original(to=to, text=text, sender=sender)

    monkeypatch.setattr(sender, "send", checked_send)
    issue(world)
    assert len(sender.outbox) == 1


@pytest.mark.parametrize("seconds", [59.1, 59.999999, 60])
def test_소수초에_발급해도_실제_60초를_채워야_한다(world: World, seconds: float) -> None:
    origin = NOW + timedelta(microseconds=900000)
    issue(world, now=origin)
    stored = world[0].execute(select(tables.TB_CERT_DMND.c.REG_DT)).scalar_one()
    assert stored == origin
    if seconds < 60:
        with pytest.raises(ApiError) as caught:
            issue(world, now=origin + timedelta(seconds=seconds))
        assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON
    else:
        issue(world, now=origin + timedelta(seconds=seconds))
        assert len(world[2].outbox) == 2


# --- 번호당 하루 상한(코드 리뷰 보안 중-2) --------------------------------------------------------

STEP = timedelta(seconds=61)  # 재전송 제한(60초)에 걸리지 않는 간격


def with_limit(world: World, limit: int) -> World:
    db, settings, sender = world
    return (
        db,
        Settings(
            database_url="unused", site_id="test", secret_key=settings.secret_key, otp_daily_limit=limit
        ),
        sender,
    )


def test_하루_상한은_기본_10건이고_초과하면_429로_거절한다(world: World) -> None:
    for i in range(10):
        issue(world, now=NOW + i * STEP)
    with pytest.raises(ApiError) as caught:
        issue(world, now=NOW + 10 * STEP)
    assert caught.value.code is ErrorCode.TOO_MANY_REQUESTS
    assert len(world[2].outbox) == 10


def test_상한_메시지는_잠시_후가_아니라_오늘_횟수_초과를_알린다(world: World) -> None:
    for i in range(10):
        issue(world, now=NOW + i * STEP)
    with pytest.raises(ApiError) as caught:
        issue(world, now=NOW + 10 * STEP)
    assert "오늘" in caught.value.message and "잠시" not in caught.value.message
    assert PHONE not in caught.value.message


def test_24시간이_지나면_상한이_풀린다(world: World) -> None:
    for i in range(10):
        issue(world, now=NOW + i * STEP)
    issue(world, now=NOW + timedelta(hours=24, seconds=1))  # 맨 처음 발급만 창 밖으로 나간다
    assert len(world[2].outbox) == 11


@pytest.mark.parametrize("seconds,blocked", [(-1, True), (0, False), (1, False)])
def test_24시간_경계는_정확히_24시간부터_허용한다(world: World, seconds: int, blocked: bool) -> None:
    one = with_limit(world, 1)
    issue(one)
    later = NOW + timedelta(hours=24, seconds=seconds)
    if blocked:
        with pytest.raises(ApiError) as caught:
            issue(one, now=later)
        assert caught.value.code is ErrorCode.TOO_MANY_REQUESTS
    else:
        issue(one, now=later)


def test_회원이_없는_가짜_요청도_하루_횟수에_센다(world: World) -> None:
    for i in range(10):
        issue(world, purpose=OtpPurpose.ID_FIND, now=NOW + i * STEP)
    assert world[2].outbox == []
    with pytest.raises(ApiError) as caught:
        issue(world, now=NOW + 10 * STEP)
    assert (
        caught.value.code is ErrorCode.TOO_MANY_REQUESTS
    )  # 회원이 있든 없든 같은 응답이어야 존재를 알 수 없다


def test_다른_번호와_다른_묶음은_하루_횟수를_따로_센다(world: World) -> None:
    for i in range(10):
        issue(world, now=NOW + i * STEP)
    issue(world, phone="01099998888", now=NOW + 10 * STEP)
    issue(world, bundle=2, now=NOW + 10 * STEP)


def test_상한은_설정으로_바꾼다(world: World) -> None:
    two = with_limit(world, 2)
    issue(two)
    issue(two, now=NOW + STEP)
    with pytest.raises(ApiError) as caught:
        issue(two, now=NOW + 2 * STEP)
    assert caught.value.code is ErrorCode.TOO_MANY_REQUESTS


def test_60초_이내_재요청은_상한보다_먼저_재전송_제한으로_거절한다(world: World) -> None:
    one = with_limit(world, 1)
    issue(one)
    with pytest.raises(ApiError) as caught:
        issue(one, now=NOW + timedelta(seconds=10))
    assert caught.value.code is ErrorCode.OTP_RESEND_TOO_SOON


def test_거절된_요청은_인증_행을_남기지_않는다(world: World) -> None:
    one = with_limit(world, 1)
    issue(one)
    with pytest.raises(ApiError):
        issue(one, now=NOW + STEP)
    db = world[0]
    assert db.execute(select(tables.TB_CERT_DMND.c.CERT_DMND_SN)).all().__len__() == 1


def test_하루_상한은_환경변수로_읽고_1_미만은_거절한다() -> None:
    from app.core.config import ConfigError, load_settings

    base = {"JORI_DATABASE_URL": "mysql+pymysql://u:p@h/x", "JORI_SITE_ID": "t", "JORI_SECRET_KEY": "k" * 40}
    assert load_settings(base).otp_daily_limit == 10
    assert load_settings({**base, "JORI_OTP_DAILY_LIMIT": "3"}).otp_daily_limit == 3
    for bad in ("0", "-2"):
        with pytest.raises(ConfigError):
            load_settings({**base, "JORI_OTP_DAILY_LIMIT": bad})
