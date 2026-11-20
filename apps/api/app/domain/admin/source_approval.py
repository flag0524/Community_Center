# 집계자료(연령·성별, 만족도)의 등록·승인·반려 공통 기반. 도메인별 차이는 SourceTable에 둔다(ADR-113)
import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, scope_for
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_JOB_HSTRY
from app.domain.admin.types import AdminAuthority as AU

REGISTER = AU.CONF_W  # 임시. 전용 권한 코드가 승인되면 바꾼다(PRD Q21)
DECIDE = AU.GRANT_W  # 임시
LIST_LIMIT = 100


@dataclass(frozen=True)
class SourceTable:
    """승인 흐름이 같은 자료 테이블 하나의 차이. 상태 코드와 이력 이름이 테이블마다 다르다."""

    table: Table
    key: str  # 일련번호 컬럼
    waiting: str  # 결정 전 상태 코드
    approved: str
    rejected: str
    waiting_label: str  # 결정 전 상태를 부르는 말(오류 문구용)
    decide_job: str


def ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def parse_date(value: Any) -> date | None:
    text = None if value is None else str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def require_whole(db: Session, admin: Admin, now: datetime, *codes: AU) -> None:
    """자료는 묶음 공통이라 지정한 권한 중 하나가 묶음 전체 범위로 있어야 한다."""
    if not any(scope_for(db, admin, code, now, group_only=True).whole for code in codes):
        raise ApiError(ErrorCode.FORBIDDEN)


def viewer(db: Session, admin: Admin, now: datetime) -> None:
    """목록·상세는 등록 또는 승인 권한이 묶음 전체 범위로 있으면 본다."""
    require_whole(db, admin, now, REGISTER, DECIDE)


def next_version(db: Session, table: Table, *conditions: Any) -> int:
    """같은 계열의 다음 버전. 호출하기 전에 묶음 행을 잠가 버전 부여를 한 줄로 세워야 한다."""
    latest = db.execute(
        select(table.c.SRC_VER).where(*conditions).order_by(table.c.SRC_VER.desc()).limit(1)
    ).scalar()
    return 1 if latest is None else int(latest) + 1


def mark_of(idem_key: str, body: BaseModel) -> str:
    """멱등 표식. 대상 테이블에 멱등키 칸이 없어 작업이력 메모에 둔다."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def replayed(db: Session, bundle: int, admin_sn: int, mark: str, job: str) -> int | None:
    """같은 담당자가 같은 키로 이미 만든 자료의 일련번호. 키는 같고 내용이 다르면 충돌이다."""
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.CHG_CN, TB_JOB_HSTRY.c.TRGT_KEY_VL).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle,
            TB_JOB_HSTRY.c.MNGR_SN == admin_sn,  # 키는 담당자마다 따로 쓴다
            TB_JOB_HSTRY.c.JOB_CD == job,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def decide(
    db: Session,
    admin: Admin,
    spec: SourceTable,
    *,
    now: datetime,
    request_id: str,
    source_id: str,
    approve: bool,
) -> int:
    """결정 전 자료를 승인하거나 반려한다. 이미 결정한 자료는 다시 결정하지 않는다(승인본은 고치지 않는다)."""
    require_whole(db, admin, now, DECIDE)
    table = spec.table
    bundle, source_sn = admin.bundle_sn, int(source_id)
    where = (table.c.OPER_BNDL_SN == bundle, table.c[spec.key] == source_sn)
    current = db.execute(select(table.c.APRV_STTS_CD).where(*where).with_for_update()).first()
    if current is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if str(current.APRV_STTS_CD).strip() != spec.waiting:
        raise ApiError(
            ErrorCode.CONFLICT_STATE, f"{spec.waiting_label} 상태의 자료만 승인하거나 반려할 수 있습니다."
        )
    db.execute(
        update(table)
        .where(*where)
        .values(
            APRV_STTS_CD=spec.approved if approve else spec.rejected,
            APRV_MNGR_SN=admin.admin_sn,
            APRV_DT=now,
            MDFCN_DT=now,
            RCRD_VER=table.c.RCRD_VER + 1,
        )
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job=spec.decide_job,
        table=table.name,
        key=source_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change="승인" if approve else "반려",
    )
    return source_sn
