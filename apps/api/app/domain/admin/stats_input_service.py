# 연령·성별 집계자료 등록·목록·상세·승인·반려(권한은 임시 매핑, ADR-089)
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.locks import lock_bundle
from app.db.tables import TB_MBR_STATS_SRC, TB_MBR_STATS_TOT, TB_MNGR
from app.domain.admin.source_approval import (
    LIST_LIMIT,
    REGISTER,
    SourceTable,
    decide,
    fail,
    mark_of,
    next_version,
    parse_date,
    replayed,
    require_whole,
    viewer,
    ymd,
)
from app.domain.admin.stats_input_schemas import (
    SourceCreate,
    SourceDetail,
    SourceList,
    SourceRowView,
    SourceState,
    SourceSummary,
)

CREATE_JOB = "STATS_SRC_CREATE"
DECIDE_JOB = "STATS_SRC_DECIDE"
STATE = {"SA.WAIT": SourceState.WAIT, "SA.APPROVE": SourceState.APPROVED, "SA.REJECT": SourceState.REJECTED}
SPEC = SourceTable(
    table=TB_MBR_STATS_SRC,
    key="MBR_STATS_SRC_SN",
    waiting="SA.WAIT",
    approved="SA.APPROVE",
    rejected="SA.REJECT",
    waiting_label="검토대기",
    decide_job=DECIDE_JOB,
)


def _summary(row: Any) -> SourceSummary:
    return SourceSummary(
        source_id=str(int(row.MBR_STATS_SRC_SN)),
        dataset_id=str(row.DATST_ID),
        version=int(row.SRC_VER),
        provider=str(row.SRC_NM),
        period_start=parse_date(row.BGNG_YMD),
        period_end=parse_date(row.END_YMD),
        age_basis_date=parse_date(row.CRTR_YMD),
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
    viewer(db, admin, now)
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
    viewer(db, admin, now)
    return _detail(db, admin.bundle_sn, int(source_id))


def _validate(body: SourceCreate) -> None:
    if body.period_end < body.period_start:
        raise fail("periodEnd", "집계 기간의 끝은 시작보다 빠를 수 없습니다.")
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(body.rows):
        field = f"rows[{index}]"
        if row.lower_age is not None and row.upper_age is not None and row.lower_age > row.upper_age:
            raise fail(field, "하한 연령은 상한 연령보다 클 수 없습니다.")
        key = (row.age_group_id, row.gender_id)
        if key in seen:  # 같은 자료 안에서 구간·성별 조합이 겹치면 합산이 틀어진다(STAT-04)
            raise fail(field, "같은 연령구간·성별 분류가 두 번 들어 있습니다.")
        seen.add(key)


def create_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: SourceCreate, idem_key: str
) -> SourceDetail:
    """검토대기로 등록한다. 버전은 서버가 정하며 묶음 행을 잠가 버전 부여와 멱등 확인을 한 줄로 세운다."""
    require_whole(db, admin, now, REGISTER)
    _validate(body)
    bundle = admin.bundle_sn
    lock_bundle(db, bundle)
    mark = mark_of(idem_key, body)
    again = replayed(db, bundle, admin.admin_sn, mark, CREATE_JOB)
    if again is not None:
        return _detail(db, bundle, again)
    version = next_version(
        db,
        TB_MBR_STATS_SRC,
        TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle,
        TB_MBR_STATS_SRC.c.DATST_ID == body.dataset_id,
    )
    source_sn = int(
        db.execute(
            insert(TB_MBR_STATS_SRC)
            .values(
                OPER_BNDL_SN=bundle,
                SRC_NM=body.provider,
                SRC_BSS_ID=body.basis_id,
                DATST_ID=body.dataset_id,
                SRC_VER=version,
                BGNG_YMD=ymd(body.period_start),
                END_YMD=ymd(body.period_end),
                CRTR_YMD=ymd(body.age_basis_date),
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


def approve_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SourceDetail:
    decide(db, admin, SPEC, now=now, request_id=request_id, source_id=source_id, approve=True)
    return _detail(db, admin.bundle_sn, int(source_id))


def reject_source(
    db: Session, admin: Admin, *, now: datetime, request_id: str, source_id: str
) -> SourceDetail:
    decide(db, admin, SPEC, now=now, request_id=request_id, source_id=source_id, approve=False)
    return _detail(db, admin.bundle_sn, int(source_id))
