# 연령·성별 집계자료 등록·목록·상세·승인·반려(권한은 임시 매핑, ADR-089)
import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit_any, scope_for
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import TB_JOB_HSTRY, TB_MBR_STATS_SRC, TB_MBR_STATS_TOT, TB_MNGR, TB_OPER_BNDL
from app.domain.admin.stats_input_schemas import (
    SourceCreate,
    SourceDetail,
    SourceList,
    SourceRowView,
    SourceState,
    SourceSummary,
)
from app.domain.admin.types import AdminAuthority as AU

REGISTER = AU.CONF_W  # 임시. 전용 권한 코드가 승인되면 바꾼다(PRD Q21)
DECIDE = AU.GRANT_W  # 임시
CREATE_JOB = "STATS_SRC_CREATE"
DECIDE_JOB = "STATS_SRC_DECIDE"
STATE = {"SA.WAIT": SourceState.WAIT, "SA.APPROVE": SourceState.APPROVED, "SA.REJECT": SourceState.REJECTED}
LIST_LIMIT = 100


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _date(value: Any) -> date | None:
    text = None if value is None else str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _whole_viewer(db: Session, admin: Admin, now: datetime) -> None:
    """자료는 묶음 공통이라 등록 또는 승인 권한이 묶음 전체 범위로 있어야 본다."""
    if not permit_any(db, admin, (REGISTER, DECIDE), now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _summary(row: Any) -> SourceSummary:
    return SourceSummary(
        source_id=str(int(row.MBR_STATS_SRC_SN)),
        dataset_id=str(row.DATST_ID),
        version=int(row.SRC_VER),
        provider=str(row.SRC_NM),
        period_start=_date(row.BGNG_YMD),
        period_end=_date(row.END_YMD),
        age_basis_date=_date(row.CRTR_YMD),
        state=STATE[str(row.APRV_STTS_CD).strip()],
        registered_at=utc(row.REG_DT),
        decided_at=None if row.APRV_DT is None else utc(row.APRV_DT),
        decided_by=None if row.MNGR_NM is None else str(row.MNGR_NM),
    )


def _source_query() -> Any:
    return select(TB_MBR_STATS_SRC, TB_MNGR.c.MNGR_NM).outerjoin(
        TB_MNGR, TB_MNGR.c.MNGR_SN == TB_MBR_STATS_SRC.c.APRV_MNGR_SN
    )


def list_sources(db: Session, admin: Admin, *, now: datetime) -> SourceList:
    _whole_viewer(db, admin, now)
    rows = db.execute(
        _source_query()
        .where(TB_MBR_STATS_SRC.c.OPER_BNDL_SN == admin.bundle_sn)
        .order_by(TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN.desc())
        .limit(LIST_LIMIT)
    ).all()
    return SourceList(items=[_summary(r) for r in rows])


def _detail(db: Session, bundle: int, source_sn: int) -> SourceDetail:
    row = db.execute(
        _source_query().where(
            TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle, TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN == source_sn
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    values = db.execute(
        select(TB_MBR_STATS_TOT)
        .where(TB_MBR_STATS_TOT.c.MBR_STATS_SRC_SN == source_sn)
        .order_by(TB_MBR_STATS_TOT.c.SORT_SEQ, TB_MBR_STATS_TOT.c.MBR_STATS_TOT_SN)
    ).all()
    return SourceDetail(
        **_summary(row).model_dump(),
        basis_id=str(row.SRC_BSS_ID),
        dedupe_note=str(row.TOT_CRTR_CN),
        rows=[
            SourceRowView(
                age_group_id=str(v.AGE_GROUP_ID),
                age_group_name=str(v.AGE_GROUP_NM),
                lower_age=None if v.LLMT_AGE is None else int(v.LLMT_AGE),
                upper_age=None if v.UPLMT_AGE is None else int(v.UPLMT_AGE),
                gender_id=str(v.GNDR_CLSF_ID),
                gender_name=str(v.GNDR_CLSF_NM),
                count=int(v.TOT_NOPE),
            )
            for v in values
        ],
    )


def get_source(db: Session, admin: Admin, *, now: datetime, source_id: str) -> SourceDetail:
    _whole_viewer(db, admin, now)
    return _detail(db, admin.bundle_sn, int(source_id))


def _validate(body: SourceCreate) -> None:
    if body.period_end < body.period_start:
        raise _fail("periodEnd", "집계 기간의 끝은 시작보다 빠를 수 없습니다.")
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(body.rows):
        field = f"rows[{index}]"
        if row.lower_age is not None and row.upper_age is not None and row.lower_age > row.upper_age:
            raise _fail(field, "하한 연령은 상한 연령보다 클 수 없습니다.")
        key = (row.age_group_id, row.gender_id)
        if key in seen:  # 같은 자료 안에서 구간·성별 조합이 겹치면 합산이 틀어진다(STAT-04)
            raise _fail(field, "같은 연령구간·성별 분류가 두 번 들어 있습니다.")
        seen.add(key)


def _mark(idem_key: str, body: SourceCreate) -> str:
    """멱등 표식. 대상 테이블에 멱등키 칸이 없어 작업이력 메모에 둔다."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _replayed(db: Session, bundle: int, admin_sn: int, mark: str) -> int | None:
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.CHG_CN, TB_JOB_HSTRY.c.TRGT_KEY_VL).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle,
            TB_JOB_HSTRY.c.MNGR_SN == admin_sn,  # 키는 담당자마다 따로 쓴다
            TB_JOB_HSTRY.c.JOB_CD == CREATE_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def create_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: SourceCreate, idem_key: str
) -> SourceDetail:
    """검토대기로 등록한다. 버전은 서버가 정하며 묶음 행을 잠가 버전 부여와 멱등 확인을 한 줄로 세운다."""
    if not scope_for(db, admin, REGISTER, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    _validate(body)
    bundle = admin.bundle_sn
    db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN).where(TB_OPER_BNDL.c.OPER_BNDL_SN == bundle).with_for_update()
    )
    mark = _mark(idem_key, body)
    again = _replayed(db, bundle, admin.admin_sn, mark)
    if again is not None:
        return _detail(db, bundle, again)
    latest = db.execute(
        select(TB_MBR_STATS_SRC.c.SRC_VER)
        .where(TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle, TB_MBR_STATS_SRC.c.DATST_ID == body.dataset_id)
        .order_by(TB_MBR_STATS_SRC.c.SRC_VER.desc())
        .limit(1)
    ).scalar()
    version = 1 if latest is None else int(latest) + 1
    source_sn = int(
        db.execute(
            insert(TB_MBR_STATS_SRC)
            .values(
                OPER_BNDL_SN=bundle,
                SRC_NM=body.provider,
                SRC_BSS_ID=body.basis_id,
                DATST_ID=body.dataset_id,
                SRC_VER=version,
                BGNG_YMD=_ymd(body.period_start),
                END_YMD=_ymd(body.period_end),
                CRTR_YMD=_ymd(body.age_basis_date),
                TOT_CRTR_CN=body.dedupe_note,
                APRV_STTS_CD="SA.WAIT",
                REG_DT=now,
            )
            .returning(TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN)
        ).scalar_one()
    )
    db.execute(
        insert(TB_MBR_STATS_TOT),
        [
            {
                "OPER_BNDL_SN": bundle,
                "MBR_STATS_SRC_SN": source_sn,
                "AGE_GROUP_ID": row.age_group_id,
                "AGE_GROUP_NM": row.age_group_name,
                "LLMT_AGE": row.lower_age,
                "UPLMT_AGE": row.upper_age,
                "GNDR_CLSF_ID": row.gender_id,
                "GNDR_CLSF_NM": row.gender_name,
                "TOT_NOPE": row.count,
                "SORT_SEQ": index,
                "REG_DT": now,
            }
            for index, row in enumerate(body.rows)
        ],
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=CREATE_JOB,
        table="TB_MBR_STATS_SRC",
        key=source_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=f"등록 버전 {version} 행 {len(body.rows)}건 {mark}",
    )
    return _detail(db, bundle, source_sn)


def _decide(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str, status: str, label: str
) -> SourceDetail:
    if not scope_for(db, admin, DECIDE, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    bundle, source_sn = admin.bundle_sn, int(source_id)
    current = db.execute(
        select(TB_MBR_STATS_SRC.c.APRV_STTS_CD)
        .where(TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle, TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN == source_sn)
        .with_for_update()
    ).first()
    if current is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if (
        str(current.APRV_STTS_CD).strip() != "SA.WAIT"
    ):  # 이미 결정한 자료는 다시 결정하지 않는다(승인본은 고치지 않는다)
        raise ApiError(ErrorCode.CONFLICT_STATE, "검토대기 상태의 자료만 승인하거나 반려할 수 있습니다.")
    db.execute(
        update(TB_MBR_STATS_SRC)
        .where(TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle, TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN == source_sn)
        .values(
            APRV_STTS_CD=status,
            APRV_MNGR_SN=admin.admin_sn,
            APRV_DT=now,
            MDFCN_DT=now,
            RCRD_VER=TB_MBR_STATS_SRC.c.RCRD_VER + 1,
        )
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=DECIDE_JOB,
        table="TB_MBR_STATS_SRC",
        key=source_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=label,
    )
    return _detail(db, bundle, source_sn)


def approve_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SourceDetail:
    return _decide(
        db, admin, now=now, request_id=request_id, source_id=source_id, status="SA.APPROVE", label="승인"
    )


def reject_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SourceDetail:
    return _decide(
        db, admin, now=now, request_id=request_id, source_id=source_id, status="SA.REJECT", label="반려"
    )
