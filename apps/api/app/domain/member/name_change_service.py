# 회원 이름 변경 요청과 관리자 검토·반영. 요청은 작업이력에만 남기고 승인하면 이름을 바꾼다(ADR-090)
import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Numeric, cast, select, update
from sqlalchemy.orm import Session, aliased

from app.audit import record_job
from app.auth.admin_access import Admin, scope_for
from app.auth.crypto import DecryptError, decrypt, encrypt
from app.auth.deps import Member
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import TB_JOB_HSTRY, TB_MBR, TB_MNGR
from app.domain.admin.refund_service import mask_name
from app.domain.admin.types import AdminAuthority as AU
from app.domain.member.name_change_schemas import (
    AdminNameChange,
    AdminNameChangeList,
    MyNameChange,
    MyNameChangeList,
    NameChangeCreate,
    NameChangeDecide,
    NameChangeFilter,
    NameChangeState,
)
from app.domain.member.profile_service import _check_password, _lock

REQUEST_JOB = "NAME_CHANGE_REQUEST"
DECIDE_JOB = "NAME_CHANGE_DECIDE"
DECIDE = AU.GRANT_W  # 임시. AU.MBR_W는 켜지 않는다. 전용 권한이 승인되면 바꾼다
ANON_NAME = "탈퇴회원"
LIST_LIMIT = 20
APPROVE_LABEL = "승인"
REJECT_LABEL = "반려"


def _mark(idem_key: str, body: NameChangeCreate) -> str:
    """멱등 표식. 비밀번호는 해시에도 넣지 않는다."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"{body.new_name.strip()}|{body.reason.strip()}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _payload(secret: str, change: str) -> tuple[str, str]:
    """요청 이력 메모에서 새 이름과 사유를 꺼낸다. 메모는 '요청 {표식} {암호문}'이다."""
    token = change.rsplit(" ", 1)[1]
    data = json.loads(decrypt(secret, token))
    return str(data["n"]), str(data["r"])


def _state(decision: str | None) -> tuple[NameChangeState, str | None]:
    if decision is None:
        return NameChangeState.PENDING, None
    label, _, note = decision.partition(" ")
    state = NameChangeState.APPROVED if label == APPROVE_LABEL else NameChangeState.REJECTED
    return state, (note or None)


def _query() -> Any:
    decided = aliased(TB_JOB_HSTRY)
    query = (
        select(
            TB_JOB_HSTRY.c.JOB_HSTRY_SN,
            TB_JOB_HSTRY.c.MBR_SN,
            TB_JOB_HSTRY.c.CHG_CN,
            TB_JOB_HSTRY.c.REG_DT,
            decided.c.CHG_CN.label("DEC_CN"),
            decided.c.REG_DT.label("DEC_DT"),
            TB_MNGR.c.MNGR_NM,
            TB_MBR.c.MBR_NM,
            TB_MBR.c.LGN_ID,
        )
        .select_from(TB_JOB_HSTRY)
        .join(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_JOB_HSTRY.c.OPER_BNDL_SN)
            & (TB_MBR.c.MBR_SN == TB_JOB_HSTRY.c.MBR_SN),
        )
        .outerjoin(
            decided,
            (decided.c.OPER_BNDL_SN == TB_JOB_HSTRY.c.OPER_BNDL_SN)
            & (decided.c.JOB_CD == DECIDE_JOB)
            & (
                cast(decided.c.TRGT_KEY_VL, Numeric(22, 0)) == TB_JOB_HSTRY.c.JOB_HSTRY_SN
            ),  # 결정 이력의 키는 요청 번호다
        )
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == decided.c.MNGR_SN)
        .where(TB_JOB_HSTRY.c.JOB_CD == REQUEST_JOB)
    )
    return query, decided


def _mine(secret: str, row: Any) -> MyNameChange:
    name, reason = _payload(secret, str(row.CHG_CN))
    state, note = _state(None if row.DEC_CN is None else str(row.DEC_CN))
    return MyNameChange(
        request_id=str(int(row.JOB_HSTRY_SN)),
        requested_name=name,
        reason=reason,
        state=state,
        requested_at=utc(row.REG_DT),
        decided_at=None if row.DEC_DT is None else utc(row.DEC_DT),
        decision_note=note,
    )


def _admin_view(secret: str, row: Any) -> AdminNameChange:
    return AdminNameChange(
        **_mine(secret, row).model_dump(),
        member_id=str(int(row.MBR_SN)),
        login_id=str(row.LGN_ID),
        current_name_masked=mask_name(str(row.MBR_NM)),
        decided_by=None if row.MNGR_NM is None else str(row.MNGR_NM),
    )


# --- 회원 -----------------------------------------------------------------------------------------


def my_requests(db: Session, settings: Settings, member: Member) -> MyNameChangeList:
    query, _ = _query()
    rows = db.execute(
        query.where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == member.bundle_sn, TB_JOB_HSTRY.c.MBR_SN == member.member_sn
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
        .limit(LIST_LIMIT)
    ).all()
    return MyNameChangeList(items=[_mine(settings.secret_key, r) for r in rows])


def _found(db: Session, settings: Settings, bundle: int, sn: int) -> MyNameChange:
    query, _ = _query()
    row = db.execute(
        query.where(TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle, TB_JOB_HSTRY.c.JOB_HSTRY_SN == sn)
    ).one()
    return _mine(settings.secret_key, row)


def create_request(
    db: Session,
    settings: Settings,
    member: Member,
    body: NameChangeCreate,
    *,
    request_id: str,
    now: datetime,
    idem_key: str,
) -> MyNameChange:
    """비밀번호를 다시 확인한 회원만 요청한다. 진행 중인 요청은 한 건뿐이고 같은 키는 처음 결과를 준다."""
    row = _lock(db, member)
    _check_password(row, body.password, "password")
    name = body.new_name.strip()
    if not name or any(ord(ch) < 32 for ch in name):
        raise ApiError(ErrorCode.VALIDATION_FAILED, fields={"newName": "이름 형식이 맞지 않습니다."})
    mark = _mark(idem_key, body)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.JOB_HSTRY_SN, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == member.bundle_sn,
            TB_JOB_HSTRY.c.MBR_SN == member.member_sn,
            TB_JOB_HSTRY.c.JOB_CD == REQUEST_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _found(db, settings, member.bundle_sn, int(prior.JOB_HSTRY_SN))
    if name == str(row.MBR_NM).strip() or name == ANON_NAME:  # type: ignore[attr-defined]
        raise ApiError(
            ErrorCode.RULE_REJECTED,
            "현재 이름과 같거나 사용할 수 없는 이름입니다.",
            fields={"newName": "현재 이름과 같거나 사용할 수 없는 이름입니다."},
        )
    if any(r.state is NameChangeState.PENDING for r in my_requests(db, settings, member).items):
        raise ApiError(ErrorCode.CONFLICT_STATE, "검토 중인 이름 변경 요청이 이미 있습니다.")
    token = encrypt(
        settings.secret_key, json.dumps({"n": name, "r": body.reason.strip()}, ensure_ascii=False)
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job=REQUEST_JOB,
        table="TB_MBR",
        key=member.member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=member.bundle_sn,
        member_sn=member.member_sn,
        change=f"요청 {mark} {token}",
    )
    created = db.execute(
        select(TB_JOB_HSTRY.c.JOB_HSTRY_SN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == member.bundle_sn,
            TB_JOB_HSTRY.c.MBR_SN == member.member_sn,
            TB_JOB_HSTRY.c.JOB_CD == REQUEST_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).scalar_one()
    return _found(db, settings, member.bundle_sn, int(created))


# --- 관리자 ---------------------------------------------------------------------------------------


def _whole(db: Session, admin: Admin, now: datetime) -> None:
    if not scope_for(db, admin, DECIDE, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def list_requests(
    db: Session, settings: Settings, admin: Admin, *, now: datetime, state: NameChangeFilter
) -> AdminNameChangeList:
    """검토 중(PENDING) 또는 처리를 마친(DECIDED) 요청. 오래된 것부터 100건까지 준다."""
    _whole(db, admin, now)
    query, decided = _query()
    query = query.where(TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn)
    pending = state is NameChangeFilter.PENDING
    query = query.where(decided.c.JOB_HSTRY_SN.is_(None) if pending else decided.c.JOB_HSTRY_SN.is_not(None))
    order = TB_JOB_HSTRY.c.JOB_HSTRY_SN.asc() if pending else TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc()
    rows = db.execute(query.order_by(order).limit(100)).all()
    return AdminNameChangeList(items=[_admin_view(settings.secret_key, r) for r in rows])


def decide(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    name_change_id: str,
    body: NameChangeDecide,
    approve: bool,
) -> AdminNameChange:
    """검토 중인 요청만 결정한다. 회원 행을 잠근 뒤 결정 여부를 보고 승인하면 이름을 바꾼다."""
    _whole(db, admin, now)
    bundle, sn = admin.bundle_sn, int(name_change_id)
    query, _ = _query()
    base = query.where(TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle, TB_JOB_HSTRY.c.JOB_HSTRY_SN == sn)
    found = db.execute(base).first()
    if found is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    member = db.execute(
        select(TB_MBR.c.MBR_STTS_CD)
        .where(TB_MBR.c.OPER_BNDL_SN == bundle, TB_MBR.c.MBR_SN == found.MBR_SN)
        .with_for_update()
    ).one()
    if db.execute(base).one().DEC_CN is not None:  # 잠금을 기다리는 사이 다른 담당자가 결정했을 수 있다
        raise ApiError(ErrorCode.CONFLICT_STATE, "이미 처리한 요청입니다.")
    if approve:
        if str(member.MBR_STTS_CD).strip() != "MS.ACTIVE":
            raise ApiError(ErrorCode.CONFLICT_STATE, "정상 회원의 요청만 승인할 수 있습니다.")
        try:
            new_name, _ = _payload(settings.secret_key, str(found.CHG_CN))
        except (DecryptError, ValueError, KeyError, IndexError) as error:
            raise ApiError(ErrorCode.INTERNAL_ERROR) from error
        db.execute(
            update(TB_MBR)
            .where(TB_MBR.c.OPER_BNDL_SN == bundle, TB_MBR.c.MBR_SN == found.MBR_SN)
            .values(MBR_NM=new_name, RCRD_VER=TB_MBR.c.RCRD_VER + 1, MDFCN_DT=now)
        )
    label = APPROVE_LABEL if approve else REJECT_LABEL
    note = (body.note or "").strip()
    record_job(
        db,
        actor="AK.ADMIN",
        job=DECIDE_JOB,
        table="TB_JOB_HSTRY",
        key=sn,  # 결정 이력은 요청 이력의 번호를 가리킨다
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=f"{label} {note}".strip(),
    )
    return _admin_view(settings.secret_key, db.execute(base).one())
