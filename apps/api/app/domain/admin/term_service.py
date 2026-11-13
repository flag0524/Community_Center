# 관리자 약관·동의문 버전 관리(AU.SITE_W). 검토→확정→게시 순서로만 나아가고 확정·게시된 문안은 덮어쓰지 않는다(FN-055, R17, DV135, ADR-060)
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit
from app.auth.join import TERM_CONTENT_TYPES
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_JOB_HSTRY, TB_MBR_AGRE_HSTRY, TB_SITE_CONTS
from app.domain.admin.refund_service import kst_start
from app.domain.admin.term_schemas import (
    TermVersion,
    TermVersionAction,
    TermVersionCreate,
    TermVersionPage,
    TermVersionSummary,
    TermVersionUpdate,
)
from app.domain.admin.term_types import TermStatus
from app.domain.admin.types import AdminAuthority as AU
from app.domain.board.sanitize import clean_body, has_text
from app.domain.member.types import TermType

CODE_TYPE = {code: kind for kind, code in TERM_CONTENT_TYPES.items()}
TITLES = {
    TermType.TERMS_OF_USE: "이용약관",
    TermType.PRIVACY_CONSENT: "개인정보 수집·이용 동의",
    TermType.MARKETING_CONSENT: "마케팅 정보 수신 동의",
}
POSTED_ON = (
    select(func.max(TB_JOB_HSTRY.c.REG_DT))
    .where(
        TB_JOB_HSTRY.c.OPER_BNDL_SN == TB_SITE_CONTS.c.OPER_BNDL_SN,
        TB_JOB_HSTRY.c.JOB_CD == "TERM_PUBLISH",
        TB_JOB_HSTRY.c.TRGT_KEY_VL
        == TB_SITE_CONTS.c.SITE_CONTS_SN,  # 문자열 변환은 대조 순서가 달라 비교가 깨진다. 숫자로 비교한다
    )
    .correlate(TB_SITE_CONTS)
    .scalar_subquery()
)
AGREED = (
    select(func.count(func.distinct(TB_MBR_AGRE_HSTRY.c.MBR_SN)))
    .where(
        TB_MBR_AGRE_HSTRY.c.SITE_CONTS_SN == TB_SITE_CONTS.c.SITE_CONTS_SN,
        TB_MBR_AGRE_HSTRY.c.AGRE_ACT_CD == "AA.AGREE",
    )
    .correlate(TB_SITE_CONTS)
    .scalar_subquery()
)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _whole(db: Session, admin: Admin, now: datetime) -> None:
    """약관·동의문은 동 미지정 묶음 공통이라 묶음 전체 범위의 담당자만 다룬다(R17)."""
    if not permit(db, admin, AU.SITE_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _status(row: Any, now: datetime) -> TermStatus:
    if row.CONTS_HASH_VL is None:
        return TermStatus.REVIEW
    if row.PSTG_YN != "Y":
        return TermStatus.FIXED
    if row.PSTG_END_DT is not None and row.PSTG_END_DT <= now:
        return TermStatus.ENDED
    return TermStatus.PUBLISHED


def _base(bundle_sn: int) -> Select[Any]:
    return select(TB_SITE_CONTS, POSTED_ON.label("POSTED_DT"), AGREED.label("AGREED_CNT")).where(
        TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn, TB_SITE_CONTS.c.CONTS_TYPE_CD.in_(list(CODE_TYPE))
    )


def _summary(row: Any, now: datetime) -> TermVersionSummary:
    return TermVersionSummary(
        version_id=str(int(row.SITE_CONTS_SN)),
        term_type=CODE_TYPE[str(row.CONTS_TYPE_CD)],
        version_name=str(row.VER_NM),
        effective_on=kst_today(row.PSTG_BGNG_DT),
        essential=row.ESNTL_YN == "Y",
        status=_status(row, now),
        posted_on=None if row.POSTED_DT is None else kst_today(row.POSTED_DT),
        agreed_count=int(row.AGREED_CNT),
    )


def _detail(row: Any, now: datetime) -> TermVersion:
    status = _status(row, now)
    return TermVersion(
        **_summary(row, now).model_dump(),
        body=str(row.CONTS_CN),
        content_hash=None if row.CONTS_HASH_VL is None else str(row.CONTS_HASH_VL),
        version=int(row.RCRD_VER),
        can_edit=status is TermStatus.REVIEW,
        can_fix=status is TermStatus.REVIEW,
        can_publish=status is TermStatus.FIXED,
    )


def list_versions(
    db: Session, admin: Admin, *, now: datetime, term_type: TermType | None, page: int, size: int
) -> TermVersionPage:
    """종류별 버전 목록. 최신 시행일이 먼저 나온다. 저장 코드가 없는 종류는 빈 목록이다."""
    _whole(db, admin, now)
    query = _base(admin.bundle_sn)
    if term_type is not None:
        query = query.where(TB_SITE_CONTS.c.CONTS_TYPE_CD == TERM_CONTENT_TYPES.get(term_type, ""))
    query = query.order_by(TB_SITE_CONTS.c.PSTG_BGNG_DT.desc(), TB_SITE_CONTS.c.SITE_CONTS_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return TermVersionPage(
        items=[_summary(r, now) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _load(db: Session, admin: Admin, now: datetime, version_id: str) -> Any:
    _whole(db, admin, now)
    row = db.execute(_base(admin.bundle_sn).where(TB_SITE_CONTS.c.SITE_CONTS_SN == int(version_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_version(db: Session, admin: Admin, *, now: datetime, version_id: str) -> TermVersion:
    return _detail(_load(db, admin, now, version_id), now)


def _audit(
    db: Session, admin: Admin, job: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_SITE_CONTS",
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def _text(body: str | None) -> str:
    text = clean_body(body or "")
    if not has_text(text):
        raise _fail("body", "문안에 읽을 수 있는 글자가 없습니다.")
    return text


def _name_free(
    db: Session, bundle_sn: int, conts_id: str, name: str, *, except_sn: int | None = None
) -> None:
    query = select(TB_SITE_CONTS.c.SITE_CONTS_SN).where(
        TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn,
        TB_SITE_CONTS.c.CONTS_ID == conts_id,
        TB_SITE_CONTS.c.VER_NM == name,
    )
    if except_sn is not None:
        query = query.where(TB_SITE_CONTS.c.SITE_CONTS_SN != except_sn)
    if db.execute(query).first() is not None:
        raise _fail("versionName", "이미 있는 버전 이름입니다.")


def _mark(idem_key: str, term_type: TermType, body: TermVersionCreate) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"{term_type.value}:{body.model_dump_json()}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def create_version(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    term_type: TermType,
    body: TermVersionCreate,
    idem_key: str,
) -> TermVersion:
    """새 버전을 검토 상태로 만든다. 복제 원본을 주고 본문을 비우면 원본 본문을 복사한다."""
    _whole(db, admin, now)
    code = TERM_CONTENT_TYPES.get(term_type)
    if code is None:
        raise _fail("termType", "이 종류는 아직 저장할 수 없습니다(스키마 개정 요청 R16 대기).")
    # 같은 종류의 올리기를 한 줄로 세워 멱등 확인과 이름 중복 확인과 저장 사이의 틈을 막는다
    db.execute(
        select(TB_SITE_CONTS.c.SITE_CONTS_SN)
        .where(TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn, TB_SITE_CONTS.c.CONTS_TYPE_CD == code)
        .with_for_update()
    ).all()
    mark = _mark(idem_key, term_type, body)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == "TERM_CREATE",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return get_version(db, admin, now=now, version_id=str(prior.TRGT_KEY_VL))
    name = body.version_name.strip()
    if not name:
        raise _fail("versionName", "버전 이름을 입력해 주세요.")
    _name_free(db, admin.bundle_sn, term_type.value, name)
    source = body.body
    if source is None or not source.strip():
        if body.base_version_id is None:
            raise _fail("body", "본문을 입력하거나 복제할 이전 버전을 골라 주세요.")
        base = db.execute(
            select(TB_SITE_CONTS.c.CONTS_CN).where(
                TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_SITE_CONTS.c.SITE_CONTS_SN == int(body.base_version_id),
                TB_SITE_CONTS.c.CONTS_TYPE_CD == code,
            )
        ).first()
        if base is None:
            raise _fail("baseVersionId", "복제할 버전을 찾을 수 없습니다.")
        source = str(base.CONTS_CN)
    text = _text(source)
    sn = int(
        db.execute(
            TB_SITE_CONTS.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                DONG_SN=None,  # 약관·동의문은 동 미지정 묶음 공통이다(R17)
                CONTS_TYPE_CD=code,
                CONTS_ID=term_type.value,
                CONTS_TTL=TITLES[term_type],
                CONTS_CN=text,
                VER_NM=name,
                CONTS_HASH_VL=None,
                PSTG_BGNG_DT=kst_start(body.effective_on),
                PSTG_END_DT=None,
                PSTG_YN="N",
                ESNTL_YN="Y" if body.essential else "N",
                SORT_SEQ=0,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_SITE_CONTS.c.SITE_CONTS_SN)
        ).scalar_one()
    )
    _audit(db, admin, "TERM_CREATE", sn, request_id, now, f"{term_type.value} {name} {mark}")
    return get_version(db, admin, now=now, version_id=str(sn))


def _locked_review(
    db: Session, admin: Admin, now: datetime, version_id: str, version: int, *, need: TermStatus
) -> Any:
    """읽은 뒤 잠그고 상태와 버전을 다시 확인한다. 필요한 상태가 아니면 409다."""
    row = _load(db, admin, now, version_id)
    db.execute(
        select(TB_SITE_CONTS.c.SITE_CONTS_SN)
        .where(TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn, TB_SITE_CONTS.c.CONTS_ID == row.CONTS_ID)
        .with_for_update()  # 같은 종류의 행을 함께 잠가 게시가 서로 겹치지 않게 한다
    ).all()
    row = _load(db, admin, now, version_id)
    if _status(row, now) is not need:
        raise ApiError(ErrorCode.CONFLICT_STATE, "이 버전은 지금 이 작업을 할 수 없는 상태입니다.")
    if version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    return row


def update_version(
    db: Session, admin: Admin, *, now: datetime, request_id: str, version_id: str, body: TermVersionUpdate
) -> TermVersion:
    """검토 상태의 버전만 고친다. 확정·게시된 버전은 409다."""
    row = _locked_review(db, admin, now, version_id, body.version, need=TermStatus.REVIEW)
    name = body.version_name.strip()
    if not name:
        raise _fail("versionName", "버전 이름을 입력해 주세요.")
    _name_free(db, admin.bundle_sn, str(row.CONTS_ID), name, except_sn=int(row.SITE_CONTS_SN))
    text = _text(body.body)
    db.execute(
        update(TB_SITE_CONTS)
        .where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)
        .values(
            VER_NM=name,
            CONTS_CN=text,
            PSTG_BGNG_DT=kst_start(body.effective_on),
            ESNTL_YN="Y" if body.essential else "N",
            MDFCN_DT=now,
            RCRD_VER=TB_SITE_CONTS.c.RCRD_VER + 1,
        )
    )
    _audit(db, admin, "TERM_UPDATE", int(row.SITE_CONTS_SN), request_id, now, f"{row.CONTS_ID} {name} 수정")
    return get_version(db, admin, now=now, version_id=version_id)


def fix_version(
    db: Session, admin: Admin, *, now: datetime, request_id: str, version_id: str, body: TermVersionAction
) -> TermVersion:
    """검토 버전을 확정한다. 문안의 SHA-256 해시가 고정되고 이후에는 고칠 수 없다."""
    row = _locked_review(db, admin, now, version_id, body.version, need=TermStatus.REVIEW)
    digest = hashlib.sha256(str(row.CONTS_CN).encode()).hexdigest()
    db.execute(
        update(TB_SITE_CONTS)
        .where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)
        .values(CONTS_HASH_VL=digest, MDFCN_DT=now, RCRD_VER=TB_SITE_CONTS.c.RCRD_VER + 1)
    )
    _audit(
        db,
        admin,
        "TERM_FIX",
        int(row.SITE_CONTS_SN),
        request_id,
        now,
        f"{row.CONTS_ID} {row.VER_NM} 확정 {digest[:8]}",
    )
    return get_version(db, admin, now=now, version_id=version_id)


def publish_version(
    db: Session, admin: Admin, *, now: datetime, request_id: str, version_id: str, body: TermVersionAction
) -> TermVersion:
    """확정 버전을 게시한다. 시행일부터 주민에게 보이고 같은 종류의 이전 게시 버전은 그 시각에 게시 종료가 된다."""
    row = _locked_review(db, admin, now, version_id, body.version, need=TermStatus.FIXED)
    current = db.execute(
        select(TB_SITE_CONTS.c.SITE_CONTS_SN, TB_SITE_CONTS.c.PSTG_BGNG_DT).where(
            TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_SITE_CONTS.c.CONTS_ID == row.CONTS_ID,
            TB_SITE_CONTS.c.PSTG_YN == "Y",
            TB_SITE_CONTS.c.PSTG_END_DT.is_(None),
            TB_SITE_CONTS.c.SITE_CONTS_SN != row.SITE_CONTS_SN,
        )
    ).all()
    for old in current:
        if old.PSTG_BGNG_DT >= row.PSTG_BGNG_DT:
            raise _fail("effectiveOn", "시행일은 지금 게시 중인 버전의 시행일보다 뒤여야 합니다.")
    for old in current:
        db.execute(
            update(TB_SITE_CONTS)
            .where(TB_SITE_CONTS.c.SITE_CONTS_SN == old.SITE_CONTS_SN)
            .values(PSTG_END_DT=row.PSTG_BGNG_DT, MDFCN_DT=now, RCRD_VER=TB_SITE_CONTS.c.RCRD_VER + 1)
        )
    db.execute(
        update(TB_SITE_CONTS)
        .where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)
        .values(PSTG_YN="Y", MDFCN_DT=now, RCRD_VER=TB_SITE_CONTS.c.RCRD_VER + 1)
    )
    ended = ",".join(str(int(o.SITE_CONTS_SN)) for o in current) or "없음"
    _audit(
        db,
        admin,
        "TERM_PUBLISH",
        int(row.SITE_CONTS_SN),
        request_id,
        now,
        f"{row.CONTS_ID} {row.VER_NM} 게시(종료 {ended})",
    )
    return get_version(db, admin, now=now, version_id=version_id)
