# 관리자 권한 배정(AU.GRANT_W). 배정은 수정하지 않고 새로 만들거나 회수하며, 부여자가 가진 권한·범위·기간을 넘는 배정과 자기 배정은 막는다(FN-056, NF-SER-004, ADR-068)
import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import STRUCTURE_AUTHORITIES, Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_DONG, TB_JOB_HSTRY, TB_MNGR, TB_MNGR_ROLE, TB_MNGR_SCP, TB_ROLE_AUTHRT
from app.db.versioned import update_versioned
from app.domain.admin.refund_service import kst_start
from app.domain.admin.role_schemas import (
    AssignmentAdminOption,
    AssignmentCreate,
    AssignmentDongOption,
    AssignmentOptions,
    AssignmentRevoke,
    AssignmentRoleOption,
    RoleAssignment,
    RoleAssignmentPage,
    RoleAssignmentSummary,
)
from app.domain.admin.role_types import AssignmentScope, AssignmentStatus
from app.domain.admin.types import AdminAuthority as AU

SCOPE_CODE = {
    AssignmentScope.SYSTEM: "SK.SYSTEM",
    AssignmentScope.GROUP: "SK.GROUP",
    AssignmentScope.DONG: "SK.DONG",
}
CODE_SCOPE = {code: scope for scope, code in SCOPE_CODE.items()}
# 동 담당자에게는 줄 수 없는 묶음 공통 권한. 구조 권한과 강사 승인·교육기수·게시판 정의다(TDD 4.4)
BUNDLE_WIDE = STRUCTURE_AUTHORITIES | {AU.INSTR_W, AU.CONF_W, AU.BBS_W}
KNOWN = {a.value: a for a in AU}
GRANT_JOB, REVOKE_JOB = "ROLE_GRANT", "ROLE_REVOKE"
GRANTER = TB_MNGR.alias("granter")


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


# --- 조회 ---------------------------------------------------------------------------------------


def _status(row: Any, now: datetime) -> AssignmentStatus:
    if row.USE_YN != "Y":
        return AssignmentStatus.REVOKED
    if row.VLD_BGNG_DT > now:
        return AssignmentStatus.SCHEDULED
    if row.VLD_END_DT is not None and row.VLD_END_DT <= now:
        return AssignmentStatus.EXPIRED
    return AssignmentStatus.ACTIVE


def _base(bundle_sn: int, grant: Scope) -> Select[Any]:
    """내 부여 범위 안의 배정. 묶음 전체면 운영묶음과 전체 운영구조 배정, 동 범위면 그 동의 배정만이다."""
    seen = (
        or_(TB_MNGR_SCP.c.SCP_TYPE_CD == "SK.SYSTEM", TB_MNGR_SCP.c.OPER_BNDL_SN == bundle_sn)
        if grant.whole
        else and_(
            TB_MNGR_SCP.c.SCP_TYPE_CD == "SK.DONG",
            TB_MNGR_SCP.c.OPER_BNDL_SN == bundle_sn,
            TB_MNGR_SCP.c.DONG_SN.in_(grant.dongs),
        )
    )
    return (
        select(
            TB_MNGR_SCP,
            TB_MNGR.c.MNGR_NM.label("ADMIN_NM"),
            TB_MNGR_ROLE.c.ROLE_NM,
            GRANTER.c.MNGR_NM.label("GRANTER_NM"),
            TB_DONG.c.DONG_NM,
        )
        .select_from(TB_MNGR_SCP)
        .join(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_MNGR_SCP.c.MNGR_SN)
        .join(TB_MNGR_ROLE, TB_MNGR_ROLE.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
        .join(GRANTER, GRANTER.c.MNGR_SN == TB_MNGR_SCP.c.GRNT_MNGR_SN)
        .outerjoin(TB_DONG, TB_DONG.c.DONG_SN == TB_MNGR_SCP.c.DONG_SN)
        .where(seen)
    )


def _label(row: Any) -> str:
    kind = CODE_SCOPE[str(row.SCP_TYPE_CD).strip()]
    if kind is AssignmentScope.SYSTEM:
        return "전체 운영구조"
    if kind is AssignmentScope.GROUP:
        return "운영묶음 전체"
    return str(row.DONG_NM)


def _valid_to(row: Any) -> date | None:
    """저장한 종료 시각은 마지막 날 다음 날의 시작이라 하루를 빼서 마지막 날을 돌려준다."""
    return None if row.VLD_END_DT is None else kst_today(row.VLD_END_DT - timedelta(seconds=1))


def _summary(row: Any, now: datetime) -> RoleAssignmentSummary:
    return RoleAssignmentSummary(
        assignment_id=str(int(row.MNGR_SCP_SN)),
        admin_name=str(row.ADMIN_NM),
        role_name=str(row.ROLE_NM),
        scope=CODE_SCOPE[str(row.SCP_TYPE_CD).strip()],
        scope_label=_label(row),
        valid_from=kst_today(row.VLD_BGNG_DT),
        valid_to=_valid_to(row),
        status=_status(row, now),
        granted_by=str(row.GRANTER_NM),
    )


def _authorities(db: Session, role_sn: int) -> list[AU]:
    codes = db.execute(
        select(TB_ROLE_AUTHRT.c.AUTHRT_CD).where(TB_ROLE_AUTHRT.c.ROLE_SN == role_sn)
    ).scalars()
    return sorted((KNOWN[str(c).strip()] for c in codes if str(c).strip() in KNOWN), key=lambda a: a.value)


def _detail(db: Session, admin: Admin, now: datetime, row: Any) -> RoleAssignment:
    status = _status(row, now)
    return RoleAssignment(
        **_summary(row, now).model_dump(),
        authorities=_authorities(db, int(row.ROLE_SN)),
        granted_at=utc(row.REG_DT),
        version=int(row.RCRD_VER),
        can_revoke=status in (AssignmentStatus.ACTIVE, AssignmentStatus.SCHEDULED)
        and int(row.MNGR_SN) != admin.admin_sn,
    )


def list_assignments(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    status: AssignmentStatus | None,
    q: str | None,
    page: int,
    size: int,
) -> RoleAssignmentPage:
    grant = permit(db, admin, AU.GRANT_W, now)
    query = _base(admin.bundle_sn, grant)
    live = TB_MNGR_SCP.c.USE_YN == "Y"
    if status is AssignmentStatus.REVOKED:
        query = query.where(TB_MNGR_SCP.c.USE_YN == "N")
    elif status is AssignmentStatus.SCHEDULED:
        query = query.where(live, TB_MNGR_SCP.c.VLD_BGNG_DT > now)
    elif status is AssignmentStatus.EXPIRED:
        query = query.where(live, TB_MNGR_SCP.c.VLD_END_DT.is_not(None), TB_MNGR_SCP.c.VLD_END_DT <= now)
    elif status is AssignmentStatus.ACTIVE:
        query = query.where(
            live,
            TB_MNGR_SCP.c.VLD_BGNG_DT <= now,
            or_(TB_MNGR_SCP.c.VLD_END_DT.is_(None), TB_MNGR_SCP.c.VLD_END_DT > now),
        )
    if q and q.strip():
        query = query.where(TB_MNGR.c.MNGR_NM.contains(q.strip(), autoescape=True))
    query = query.order_by(TB_MNGR_SCP.c.REG_DT.desc(), TB_MNGR_SCP.c.MNGR_SCP_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return RoleAssignmentPage(
        items=[_summary(r, now) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
        can_grant=True,
    )


def _load(db: Session, admin: Admin, now: datetime, assignment_id: str) -> Any:
    grant = permit(db, admin, AU.GRANT_W, now)
    row = db.execute(
        _base(admin.bundle_sn, grant).where(TB_MNGR_SCP.c.MNGR_SCP_SN == int(assignment_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_assignment(db: Session, admin: Admin, *, now: datetime, assignment_id: str) -> RoleAssignment:
    return _detail(db, admin, now, _load(db, admin, now, assignment_id))


# --- 위임 판정 ----------------------------------------------------------------------------------


def _held(db: Session, admin: Admin, now: datetime) -> list[Any]:
    """내가 가진 (권한, 범위 유형, 동, 시작, 끝). 사용 중이고 아직 끝나지 않은 배정만이다."""
    return list(
        db.execute(
            select(
                TB_ROLE_AUTHRT.c.AUTHRT_CD,
                TB_MNGR_SCP.c.SCP_TYPE_CD,
                TB_MNGR_SCP.c.DONG_SN,
                TB_MNGR_SCP.c.VLD_BGNG_DT,
                TB_MNGR_SCP.c.VLD_END_DT,
            )
            .select_from(TB_MNGR_SCP)
            .join(TB_MNGR_ROLE, TB_MNGR_ROLE.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
            .join(TB_ROLE_AUTHRT, TB_ROLE_AUTHRT.c.ROLE_SN == TB_MNGR_SCP.c.ROLE_SN)
            .where(
                TB_MNGR_SCP.c.MNGR_SN == admin.admin_sn,
                TB_MNGR_SCP.c.USE_YN == "Y",
                TB_MNGR_ROLE.c.USE_YN == "Y",
                or_(TB_MNGR_SCP.c.OPER_BNDL_SN.is_(None), TB_MNGR_SCP.c.OPER_BNDL_SN == admin.bundle_sn),
                or_(TB_MNGR_SCP.c.VLD_END_DT.is_(None), TB_MNGR_SCP.c.VLD_END_DT > now),
            )
        ).all()
    )


def _gives(held: Any, authority: AU, scope: AssignmentScope, dong_sn: int | None) -> bool:
    """내 배정 한 줄이 이 권한을 이 범위로 줄 수 있는가. 전체 운영구조 배정은 구조 권한만 다룬다(R29)."""
    kind = str(held.SCP_TYPE_CD).strip()
    if kind == "SK.SYSTEM":
        return authority in STRUCTURE_AUTHORITIES and scope in (AssignmentScope.SYSTEM, AssignmentScope.GROUP)
    if kind == "SK.GROUP":
        return scope in (AssignmentScope.GROUP, AssignmentScope.DONG)
    return scope is AssignmentScope.DONG and held.DONG_SN is not None and int(held.DONG_SN) == dong_sn


def _inside(intervals: list[tuple[datetime, datetime | None]], begin: datetime, end: datetime | None) -> bool:
    """[begin, end)가 내 배정 기간들을 이은 하나의 기간 안에 드는가. end가 None이면 끝이 없다."""
    merged: list[tuple[datetime, datetime | None]] = []
    for start, stop in sorted(intervals, key=lambda i: i[0]):
        if merged and (merged[-1][1] is None or start <= merged[-1][1]):
            last = merged[-1][1]
            merged[-1] = (merged[-1][0], None if last is None or stop is None else max(last, stop))
        else:
            merged.append((start, stop))
    return any(s <= begin and (e is None or (end is not None and end <= e)) for s, e in merged)


def _allowed_scopes(authorities: list[AU]) -> list[AssignmentScope]:
    """역할이 담은 권한으로 정해지는, 줄 수 있는 범위 유형."""
    scopes = [AssignmentScope.GROUP]
    if all(a in STRUCTURE_AUTHORITIES for a in authorities):
        scopes.insert(0, AssignmentScope.SYSTEM)
    if not any(a in BUNDLE_WIDE for a in authorities):
        scopes.append(AssignmentScope.DONG)
    return scopes


def _delegable(
    held: list[Any],
    authorities: list[AU],
    scope: AssignmentScope,
    dong_sn: int | None,
    begin: datetime | None,
    end: datetime | None,
) -> bool:
    """역할의 모든 권한을 내가 이 범위로 줄 수 있고, 기간을 주면 그 기간 내내 갖고 있는가(TDD 4.4)."""
    for authority in authorities:
        rows = [
            r
            for r in held
            if str(r.AUTHRT_CD).strip() == authority.value and _gives(r, authority, scope, dong_sn)
        ]
        if not rows:
            return False
        if begin is not None and not _inside([(r.VLD_BGNG_DT, r.VLD_END_DT) for r in rows], begin, end):
            return False
    return True


def get_options(db: Session, admin: Admin, *, now: datetime) -> AssignmentOptions:
    """위임할 수 있는 것만이다. 내가 가진 권한·범위를 넘는 역할과 자기 자신은 목록에 없다."""
    grant = permit(db, admin, AU.GRANT_W, now)
    held = _held(db, admin, now)
    dong_query = select(TB_DONG.c.DONG_SN, TB_DONG.c.DONG_NM).where(TB_DONG.c.OPER_BNDL_SN == admin.bundle_sn)
    if not grant.whole:
        dong_query = dong_query.where(TB_DONG.c.DONG_SN.in_(grant.dongs))
    dongs = db.execute(dong_query.order_by(TB_DONG.c.DONG_NM, TB_DONG.c.DONG_SN)).all()
    roles: list[AssignmentRoleOption] = []
    for role in db.execute(
        select(TB_MNGR_ROLE.c.ROLE_SN, TB_MNGR_ROLE.c.ROLE_NM)
        .where(TB_MNGR_ROLE.c.USE_YN == "Y")
        .order_by(TB_MNGR_ROLE.c.ROLE_NM, TB_MNGR_ROLE.c.ROLE_SN)
    ):
        authorities = _authorities(db, int(role.ROLE_SN))
        if not authorities:
            continue
        scopes = [
            scope
            for scope in _allowed_scopes(authorities)
            if (scope is AssignmentScope.SYSTEM or grant.whole or scope is AssignmentScope.DONG)
            and (
                any(_delegable(held, authorities, scope, int(d.DONG_SN), None, None) for d in dongs)
                if scope is AssignmentScope.DONG
                else _delegable(held, authorities, scope, None, None, None)
            )
        ]
        if scopes:
            roles.append(
                AssignmentRoleOption(
                    id=str(int(role.ROLE_SN)), name=str(role.ROLE_NM), scopes=scopes, authorities=authorities
                )
            )
    admins = db.execute(
        select(TB_MNGR.c.MNGR_SN, TB_MNGR.c.MNGR_NM)
        .where(TB_MNGR.c.USE_YN == "Y", TB_MNGR.c.MNGR_SN != admin.admin_sn)
        .order_by(TB_MNGR.c.MNGR_NM, TB_MNGR.c.MNGR_SN)
    ).all()
    return AssignmentOptions(
        admins=[AssignmentAdminOption(id=str(int(a.MNGR_SN)), name=str(a.MNGR_NM)) for a in admins],
        roles=roles,
        dongs=[AssignmentDongOption(id=str(int(d.DONG_SN)), name=str(d.DONG_NM)) for d in dongs],
    )


# --- 배정·회수 ----------------------------------------------------------------------------------


def _marker(idem_key: str, body: AssignmentCreate) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _replayed(db: Session, admin: Admin, mark: str) -> int | None:
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.MNGR_SN == admin.admin_sn,
            TB_JOB_HSTRY.c.JOB_CD == GRANT_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def _period(body: AssignmentCreate, now: datetime) -> tuple[datetime, datetime | None]:
    if body.valid_from < kst_today(now):
        raise _fail("validFrom", "시작일은 오늘 이후여야 합니다.")
    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise _fail("validTo", "종료일은 시작일 이후여야 합니다.")
    end = None if body.valid_to is None else kst_start(body.valid_to + timedelta(days=1))
    return kst_start(body.valid_from), end


def create_assignment(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    body: AssignmentCreate,
    idem_key: str,
) -> RoleAssignment:
    """부여자의 권한·범위·기간 안에서만 새 배정을 만든다. 자기 자신에게는 줄 수 없다(R28)."""
    grant = permit(db, admin, AU.GRANT_W, now)
    target_sn = int(body.admin_id)
    target = db.execute(
        select(TB_MNGR.c.USE_YN)
        .where(TB_MNGR.c.MNGR_SN == target_sn)
        .with_for_update()  # 같은 대상의 배정을 한 줄로 세운다
    ).first()
    mark = _marker(idem_key, body)
    prior = _replayed(db, admin, mark)
    if prior is not None:
        return get_assignment(db, admin, now=now, assignment_id=str(prior))
    if target is None or target.USE_YN != "Y":
        raise _fail("adminId", "배정할 관리자를 찾을 수 없습니다.")
    if target_sn == admin.admin_sn:
        raise _fail("adminId", "자기 자신에게는 배정할 수 없습니다. 다른 권한 관리자가 대신 배정해야 합니다.")
    role = db.execute(
        select(TB_MNGR_ROLE.c.ROLE_SN).where(
            TB_MNGR_ROLE.c.ROLE_SN == int(body.role_id), TB_MNGR_ROLE.c.USE_YN == "Y"
        )
    ).first()
    authorities = _authorities(db, int(body.role_id)) if role is not None else []
    if role is None or not authorities:
        raise _fail("roleId", "배정할 역할을 찾을 수 없습니다.")
    dong_sn: int | None = None
    if body.scope is AssignmentScope.DONG:
        if body.dong_id is None:
            raise _fail("dongId", "동 범위는 동을 골라야 합니다.")
        dong_sn = int(body.dong_id)
        found = db.execute(
            select(TB_DONG.c.DONG_SN).where(
                TB_DONG.c.OPER_BNDL_SN == admin.bundle_sn, TB_DONG.c.DONG_SN == dong_sn
            )
        ).first()
        if found is None:
            raise _fail("dongId", "동을 찾을 수 없습니다.")
    elif body.dong_id is not None:
        raise _fail("dongId", "동은 동 범위일 때만 고릅니다.")
    if body.scope not in _allowed_scopes(authorities):
        raise _fail("scope", "이 역할은 선택한 범위로 줄 수 없습니다.")
    covered = grant.whole if body.scope is not AssignmentScope.DONG else grant.covers(dong_sn)
    begin, end = _period(body, now)
    if not covered or not _delegable(_held(db, admin, now), authorities, body.scope, dong_sn, begin, end):
        raise _fail("roleId", "내가 가진 권한·범위·기간을 넘는 배정은 할 수 없습니다.")
    overlap = db.execute(
        select(TB_MNGR_SCP.c.MNGR_SCP_SN).where(
            TB_MNGR_SCP.c.MNGR_SN == target_sn,
            TB_MNGR_SCP.c.ROLE_SN == int(body.role_id),
            TB_MNGR_SCP.c.SCP_TYPE_CD == SCOPE_CODE[body.scope],
            TB_MNGR_SCP.c.DONG_SN.is_(None) if dong_sn is None else TB_MNGR_SCP.c.DONG_SN == dong_sn,
            TB_MNGR_SCP.c.USE_YN == "Y",
            or_(TB_MNGR_SCP.c.VLD_END_DT.is_(None), TB_MNGR_SCP.c.VLD_END_DT > begin),
            *([TB_MNGR_SCP.c.VLD_BGNG_DT < end] if end is not None else []),
        )
    ).first()
    if overlap is not None:
        raise _fail("roleId", "같은 역할·범위의 배정이 그 기간에 이미 있습니다.")
    created = int(
        db.execute(
            TB_MNGR_SCP.insert()
            .values(
                MNGR_SN=target_sn,
                ROLE_SN=int(body.role_id),
                SCP_TYPE_CD=SCOPE_CODE[body.scope],
                OPER_BNDL_SN=None if body.scope is AssignmentScope.SYSTEM else admin.bundle_sn,
                DONG_SN=dong_sn,
                VLD_BGNG_DT=begin,
                VLD_END_DT=end,
                GRNT_MNGR_SN=admin.admin_sn,
                USE_YN="Y",
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_MNGR_SCP.c.MNGR_SCP_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=GRANT_JOB,
        table="TB_MNGR_SCP",
        key=created,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=json.dumps(
            {
                "admin": target_sn,
                "role": int(body.role_id),
                "scope": body.scope.value,
                "dong": dong_sn,
                "from": body.valid_from.isoformat(),
                "to": None if body.valid_to is None else body.valid_to.isoformat(),
            }
        )
        + " "
        + mark,
    )
    return get_assignment(db, admin, now=now, assignment_id=str(created))


def revoke_assignment(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    assignment_id: str,
    body: AssignmentRevoke,
) -> RoleAssignment:
    """배정을 지우지 않고 사용 중지로 바꾼다. 자기 배정은 회수할 수 없고 이미 끝났거나 회수한 배정은 409다."""
    _load(db, admin, now, assignment_id)
    db.execute(
        select(TB_MNGR_SCP.c.MNGR_SCP_SN)
        .where(TB_MNGR_SCP.c.MNGR_SCP_SN == int(assignment_id))
        .with_for_update()
    ).one()
    row = _load(db, admin, now, assignment_id)  # 잠근 뒤 다시 읽는다
    if body.version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    if int(row.MNGR_SN) == admin.admin_sn:
        raise _fail("assignmentId", "자기 배정은 회수할 수 없습니다. 다른 권한 관리자가 회수해야 합니다.")
    before = _status(row, now)
    if before not in (AssignmentStatus.ACTIVE, AssignmentStatus.SCHEDULED):
        raise ApiError(ErrorCode.CONFLICT_STATE, "유효하거나 시작 전인 배정만 회수할 수 있습니다.")
    update_versioned(
        db,
        TB_MNGR_SCP,
        {"MNGR_SCP_SN": int(assignment_id)},
        body.version,
        {"USE_YN": "N"},
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=REVOKE_JOB,
        table="TB_MNGR_SCP",
        key=int(assignment_id),
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=json.dumps(
            {"admin": int(row.MNGR_SN), "role": int(row.ROLE_SN), "before": before.value, "after": "REVOKED"}
        ),
    )
    return get_assignment(db, admin, now=now, assignment_id=assignment_id)
