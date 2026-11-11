# 관리자 인증 의존성과 기능권한·범위·유효기간 판정(같은 배정 행에서 함께 검사, R19·R20, RQ-SER-NF-003)
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.deps import (
    BACKGROUND_HEADER,
    Clock,
    active_admin,
    current_session,
    get_bundle_resolver,
    get_clock,
    verify_csrf,
)
from app.auth.sessions import SessionRecord, touch
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.db.tables import TB_MNGR_ROLE, TB_MNGR_SCP, TB_ROLE_AUTHRT
from app.domain.admin.types import AdminAuthority

# SK.SYSTEM 배정은 운영구조·역할배정 권한만 갖는다. 회원·결제·콘텐츠 같은 업무 권한은 묶음·동 배정이 있어야 한다(R20, R29)
STRUCTURE_AUTHORITIES = frozenset(
    {
        AdminAuthority.GRP_R,
        AdminAuthority.GRP_W,
        AdminAuthority.DONG_W,
        AdminAuthority.MNGR_W,
        AdminAuthority.ROLE_W,
        AdminAuthority.GRANT_W,
    }
)


@dataclass(frozen=True)
class Admin:
    """로그인한 관리자. 관리자 번호와 운영묶음은 요청 값이 아니라 세션과 배포 설정에서만 온다."""

    admin_sn: int
    bundle_sn: int
    record: SessionRecord


@dataclass(frozen=True)
class Scope:
    """한 기능권한이 미치는 범위. 묶음 전체이거나 특정 동들이다. 비어 있으면 권한이 없는 것이다."""

    whole: bool = False
    dongs: frozenset[int] = frozenset()

    def empty(self) -> bool:
        return not self.whole and not self.dongs

    def covers(self, dong_sn: int | None) -> bool:
        """강좌의 운영 동이 범위 안인가. 동이 없는 강좌(묶음 공통)는 묶음 전체 범위만 다룬다."""
        return self.whole or (dong_sn is not None and dong_sn in self.dongs)


def scope_for(db: Session, admin: Admin, authority: AdminAuthority, now: datetime) -> Scope:
    """배정 행마다 (역할이 이 권한을 가짐 + 사용 중 + 유효기간 안 + 범위)를 함께 보고, 맞는 행의 범위만 합친다.

    서로 다른 행의 역할과 동을 곱집합으로 섞지 않는다. 유효 종료 시각은 포함하지 않는다.
    """
    rows = db.execute(
        select(TB_MNGR_SCP.c.SCP_TYPE_CD, TB_MNGR_SCP.c.DONG_SN)
        .join(TB_MNGR_ROLE, TB_MNGR_ROLE.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
        .join(
            TB_ROLE_AUTHRT,
            (TB_ROLE_AUTHRT.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
            & (TB_ROLE_AUTHRT.c.AUTHRT_CD == authority.value),
        )
        .where(
            TB_MNGR_SCP.c.MNGR_SN == admin.admin_sn,
            TB_MNGR_SCP.c.USE_YN == "Y",
            TB_MNGR_ROLE.c.USE_YN == "Y",
            TB_MNGR_SCP.c.VLD_BGNG_DT <= now,
            or_(TB_MNGR_SCP.c.VLD_END_DT.is_(None), TB_MNGR_SCP.c.VLD_END_DT > now),
            or_(TB_MNGR_SCP.c.OPER_BNDL_SN.is_(None), TB_MNGR_SCP.c.OPER_BNDL_SN == admin.bundle_sn),
        )
    ).all()
    whole = False
    dongs: set[int] = set()
    for row in rows:
        kind = str(row.SCP_TYPE_CD).strip()
        if kind == "SK.SYSTEM":
            whole = whole or authority in STRUCTURE_AUTHORITIES
        elif kind == "SK.GROUP":
            whole = True
        elif kind == "SK.DONG" and row.DONG_SN is not None:
            dongs.add(int(row.DONG_SN))
    return Scope(whole, frozenset(dongs))


def permit(db: Session, admin: Admin, authority: AdminAuthority, now: datetime) -> Scope:
    """권한이 하나도 없으면 403이다. 있으면 그 범위를 돌려주고, 대상 레코드가 범위 안인지는 호출한 쪽이 레코드의 값으로 본다."""
    scope = scope_for(db, admin, authority, now)
    if scope.empty():
        raise ApiError(ErrorCode.FORBIDDEN)
    return scope


def permit_any(db: Session, admin: Admin, authorities: tuple[AdminAuthority, ...], now: datetime) -> Scope:
    """여러 권한 중 하나라도 있으면 통과한다. 범위는 각 권한의 범위를 합친다."""
    whole = False
    dongs: set[int] = set()
    for authority in authorities:
        scope = scope_for(db, admin, authority, now)
        whole = whole or scope.whole
        dongs |= scope.dongs
    union = Scope(whole, frozenset(dongs))
    if union.empty():
        raise ApiError(ErrorCode.FORBIDDEN)
    return union


def require_admin(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
) -> Admin:
    """살아 있는 관리자 세션이 있어야 한다. 사용 중지된 계정은 세션이 있어도 인증되지 않는다."""
    now = clock()
    record = current_session(request, "admin", db, now)
    if record is None or record.admin_sn is None or not active_admin(db, record.admin_sn):
        raise ApiError(ErrorCode.UNAUTHENTICATED)
    if request.headers.get(BACKGROUND_HEADER) != "1":
        record = touch(db, record, "admin", now)
    return Admin(record.admin_sn or 0, bundles.resolve(db), record)


def require_admin_write(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[Admin, Depends(require_admin)],
) -> Admin:
    """상태를 바꾸는 요청은 로그인에 더해 CSRF 토큰도 맞아야 한다(DV17)."""
    verify_csrf(request, settings, "admin", admin.record)
    return admin
