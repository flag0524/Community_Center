# 인증 라우터가 쓰는 의존성: 설정, 시계, 운영묶음, 쿠키·CSRF 처리, 현재 로그인한 회원·관리자
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.sms import build_sender
from app.adapters.sms.base import SmsSender
from app.auth.sessions import SessionRecord, find_active, touch
from app.auth.tokens import csrf_for, new_token, same
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.db.tables import TB_MBR, TB_MNGR
from app.routers.deps import ADMIN_SESSION_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME

Clock = Callable[[], datetime]
Kind = Literal["member", "admin"]
COOKIE_NAMES = {"member": SESSION_COOKIE_NAME, "admin": ADMIN_SESSION_COOKIE_NAME}
# 로그인 전 CSRF(더블 서브밋)에 쓰는 시드 쿠키. 세션 쿠키와 이름이 달라 서로 대신할 수 없다.
SEED_COOKIE_NAMES = {"member": "jori_csrf_seed", "admin": "jori_admin_csrf_seed"}


def get_sms_sender(settings: Annotated[Settings, Depends(get_settings)]) -> SmsSender:
    return build_sender(settings)


def utc_now() -> datetime:
    """DB가 UTC naive로 저장하므로 시각은 timezone 없는 UTC로 다룬다. 시험에서 get_clock을 바꿔 끼운다."""
    return datetime.now(UTC).replace(tzinfo=None)


def get_clock() -> Clock:
    return utc_now


_resolvers: dict[str, BundleResolver] = {}


def get_bundle_resolver(settings: Annotated[Settings, Depends(get_settings)]) -> BundleResolver:
    """DB를 쓰지 않는 의존성이다. 잘못된 입력이 DB 조회까지 일으키지 않게, 조회는 핸들러가 검증 뒤에 한다."""
    return _resolvers.setdefault(settings.site_id, BundleResolver(settings.site_id))


def request_id_of(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else new_token()


def set_cookie(response: Response, settings: Settings, name: str, value: str) -> None:
    # HttpOnly로 스크립트가 읽지 못하게 하고 SameSite=Lax로 다른 사이트의 요청에 실리지 않게 한다(ADR-008)
    response.set_cookie(name, value, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def clear_cookie(response: Response, settings: Settings, name: str) -> None:
    response.delete_cookie(name, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


def session_csrf(settings: Settings, record: SessionRecord) -> str:
    return csrf_for(settings.secret_key, "session", record.token_hash)


def anonymous_csrf(settings: Settings, seed: str) -> str:
    return csrf_for(settings.secret_key, "anon", seed)


def verify_csrf(request: Request, settings: Settings, kind: Kind, record: SessionRecord | None) -> None:
    """상태 변경 요청의 X-CSRF-Token을 확인한다(DV17). 로그인 뒤에는 세션, 전에는 시드 쿠키에서 파생한다."""
    given = request.headers.get(CSRF_HEADER_NAME)
    if record is not None:
        expected: str | None = session_csrf(settings, record)
    else:
        seed = request.cookies.get(SEED_COOKIE_NAMES[kind])
        expected = anonymous_csrf(settings, seed) if seed else None
    if not same(given, expected):
        raise ApiError(ErrorCode.FORBIDDEN)


def current_session(request: Request, kind: Kind, db: Session, now: datetime) -> SessionRecord | None:
    return find_active(db, request.cookies.get(COOKIE_NAMES[kind]), kind, now)


def active_member(db: Session, member_sn: int) -> bool:
    """세션이 살아 있어도 계정이 탈퇴·제한이면 인증된 것으로 보지 않는다."""
    status = db.execute(select(TB_MBR.c.MBR_STTS_CD).where(TB_MBR.c.MBR_SN == member_sn)).scalar_one_or_none()
    return status == "MS.ACTIVE"


def active_admin(db: Session, admin_sn: int) -> bool:
    use = db.execute(select(TB_MNGR.c.USE_YN).where(TB_MNGR.c.MNGR_SN == admin_sn)).scalar_one_or_none()
    return use == "Y"


# 화면이 저절로 부르는 조회에 붙인다. 사용자의 활동이 아니어서 유휴 시간을 늘리지 않는다
BACKGROUND_HEADER = "X-Background"


@dataclass(frozen=True)
class Member:
    """로그인한 회원. 회원 번호와 운영묶음은 요청 값이 아니라 세션에서만 온다(RQ-SER-NF-001)."""

    member_sn: int
    bundle_sn: int
    record: SessionRecord


def require_member(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
) -> Member:
    """살아 있는 회원 세션이 있어야 한다. 활동으로 보는 요청은 유휴 시간을 처음부터 다시 센다(AUTH-05)."""
    now = clock()
    record = current_session(request, "member", db, now)
    if record is None or record.member_sn is None or record.bundle_sn is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED)
    member_sn, bundle_sn = record.member_sn, record.bundle_sn
    if bundle_sn != bundles.resolve(db) or not active_member(db, member_sn):
        raise ApiError(ErrorCode.UNAUTHENTICATED)
    if request.headers.get(BACKGROUND_HEADER) != "1":
        record = touch(db, record, "member", now)
    return Member(member_sn, bundle_sn, record)
