# 주민 쪽 감면 사전심사(신청·조회·철회). 조리읍 거주가 확인된 회원이 기수별로 신청하고 결과만 본다. 심사 내용·처리자는 주지 않는다(FN-038, ADR-064)
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.errors import ApiError, ErrorCode
from app.core.times import kst_today, kst_ymd
from app.db.tables import TB_EDU_CYCL, TB_FILE, TB_JOB_HSTRY, TB_MBR, TB_RDCT_BFHD_SRNG
from app.db.versioned import update_versioned
from app.domain.admin.reduction_service import CODE_STATUS, CODE_TYPE, STATUS_CODE, TYPE_CODE
from app.domain.admin.reduction_types import ReductionStatus
from app.domain.reduction.schemas import (
    MyReduction,
    MyReductionCreate,
    MyReductionList,
    MyReductionOptions,
    MyReductionSummary,
    ReductionCycleOption,
)

APPLY_JOB = "RDCT_APPLY"
BLOCK_NOT_RESIDENT = (
    "조리읍 거주가 확인된 회원만 감면 사전심사를 신청할 수 있습니다. 센터에서 거주 확인을 받아 주세요."
)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _member(db: Session, bundle_sn: int, member_sn: int, *, lock: bool = False) -> Any:
    query = select(TB_MBR.c.MBR_SN, TB_MBR.c.HAB_RGN_CD, TB_MBR.c.HAB_IDNTY_STTS_CD).where(
        TB_MBR.c.OPER_BNDL_SN == bundle_sn, TB_MBR.c.MBR_SN == member_sn
    )
    return db.execute(query.with_for_update() if lock else query).one()


def _resident(member: Any) -> bool:
    return bool(member.HAB_RGN_CD == "RA.JORI" and member.HAB_IDNTY_STTS_CD == "RV.OK")


def _evidence_count() -> Any:
    return (
        select(func.count())
        .where(
            TB_FILE.c.OPER_BNDL_SN == TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN,
            TB_FILE.c.RDCT_BFHD_SRNG_SN == TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN,
            TB_FILE.c.FILE_STTS_CD != "FS.DELETE",
        )
        .scalar_subquery()
    )


def _base(bundle_sn: int, member_sn: int) -> Select[Any]:
    """내 심사만이다. 남의 심사는 없는 것과 같다."""
    return (
        select(TB_RDCT_BFHD_SRNG, TB_EDU_CYCL.c.EDU_CYCL_NM, _evidence_count().label("EVIDENCE_CNT"))
        .join(
            TB_EDU_CYCL,
            (TB_EDU_CYCL.c.OPER_BNDL_SN == TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN)
            & (TB_EDU_CYCL.c.EDU_CYCL_SN == TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN),
        )
        .where(TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == bundle_sn, TB_RDCT_BFHD_SRNG.c.MBR_SN == member_sn)
    )


def _summary(row: Any) -> MyReductionSummary:
    return MyReductionSummary(
        review_id=str(int(row.RDCT_BFHD_SRNG_SN)),
        cycle_name=str(row.EDU_CYCL_NM),
        reduction_type=CODE_TYPE[str(row.RDCT_TYPE_CD)],
        status=CODE_STATUS[str(row.SRNG_STTS_CD)],
        applied_on=kst_today(row.APLY_DT),
        evidence_count=int(row.EVIDENCE_CNT),
    )


def _detail(row: Any) -> MyReduction:
    status = CODE_STATUS[str(row.SRNG_STTS_CD)]
    received = status is ReductionStatus.RECEIVED
    return MyReduction(
        **_summary(row).model_dump(),
        valid_until=(
            kst_today(row.VLD_END_DT) if status is ReductionStatus.APPROVED and row.VLD_END_DT else None
        ),
        reject_reason=str(row.RJCT_RSN) if status is ReductionStatus.REJECTED and row.RJCT_RSN else None,
        can_add_evidence=received,
        can_withdraw=received,
    )


def _mine(db: Session, bundle_sn: int, member_sn: int, review_id: str) -> Any:
    row = db.execute(
        _base(bundle_sn, member_sn).where(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == int(review_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_options(db: Session, *, bundle_sn: int, member_sn: int, now: datetime) -> MyReductionOptions:
    member = _member(db, bundle_sn, member_sn)
    if not _resident(member):
        return MyReductionOptions(cycles=[], can_apply=False, block_reason=BLOCK_NOT_RESIDENT)
    cycles = db.execute(
        select(TB_EDU_CYCL.c.EDU_CYCL_SN, TB_EDU_CYCL.c.EDU_CYCL_NM)
        .where(
            TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn,
            TB_EDU_CYCL.c.USE_YN == "Y",
            TB_EDU_CYCL.c.EDU_END_YMD >= kst_ymd(now),
        )
        .order_by(TB_EDU_CYCL.c.EDU_BGNG_YMD, TB_EDU_CYCL.c.EDU_CYCL_SN)
    ).all()
    return MyReductionOptions(
        cycles=[ReductionCycleOption(id=str(int(c.EDU_CYCL_SN)), name=str(c.EDU_CYCL_NM)) for c in cycles],
        can_apply=True,
        block_reason=None,
    )


def list_mine(db: Session, *, bundle_sn: int, member_sn: int) -> MyReductionList:
    rows = db.execute(
        _base(bundle_sn, member_sn).order_by(
            TB_RDCT_BFHD_SRNG.c.APLY_DT.desc(), TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN.desc()
        )
    ).all()
    return MyReductionList(items=[_summary(r) for r in rows])


def get_mine(db: Session, *, bundle_sn: int, member_sn: int, review_id: str) -> MyReduction:
    return _detail(_mine(db, bundle_sn, member_sn, review_id))


def _marker(idem_key: str, body: MyReductionCreate) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"{body.cycle_id}:{body.reduction_type.value}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _replayed(db: Session, bundle_sn: int, member_sn: int, mark: str) -> int | None:
    """같은 키로 이미 신청했으면 그 번호를 준다. 내용이 다르면 409다."""
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.MBR_SN == member_sn,
            TB_JOB_HSTRY.c.JOB_CD == APPLY_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def _blocking(db: Session, bundle_sn: int, member_sn: int, cycle_sn: int, now: datetime) -> bool:
    """같은 기수에 접수 중이거나 아직 유효한 승인이 있다. 반려·철회·기간이 끝난 승인은 막지 않는다."""
    return (
        db.execute(
            select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN).where(
                TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == bundle_sn,
                TB_RDCT_BFHD_SRNG.c.MBR_SN == member_sn,
                TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN == cycle_sn,
                or_(
                    TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == STATUS_CODE[ReductionStatus.RECEIVED],
                    (TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == STATUS_CODE[ReductionStatus.APPROVED])
                    & (TB_RDCT_BFHD_SRNG.c.VLD_END_DT.is_(None) | (TB_RDCT_BFHD_SRNG.c.VLD_END_DT > now)),
                ),
            )
        ).first()
        is not None
    )


def create_mine(
    db: Session,
    *,
    bundle_sn: int,
    member_sn: int,
    body: MyReductionCreate,
    idem_key: str,
    now: datetime,
    request_id: str,
) -> MyReduction:
    """회원 행을 잠근 뒤 거주 확인·기수·중복을 검사하고 접수 건을 만든다. 금액·비율은 받지 않는다."""
    member = _member(db, bundle_sn, member_sn, lock=True)
    mark = _marker(idem_key, body)
    prior = _replayed(db, bundle_sn, member_sn, mark)
    if prior is not None:
        return get_mine(db, bundle_sn=bundle_sn, member_sn=member_sn, review_id=str(prior))
    if not _resident(member):
        raise ApiError(ErrorCode.RULE_REJECTED, BLOCK_NOT_RESIDENT)
    cycle = db.execute(
        select(TB_EDU_CYCL.c.EDU_CYCL_SN).where(
            TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn,
            TB_EDU_CYCL.c.EDU_CYCL_SN == int(body.cycle_id),
            TB_EDU_CYCL.c.USE_YN == "Y",
            TB_EDU_CYCL.c.EDU_END_YMD >= kst_ymd(now),
        )
    ).first()
    if cycle is None:
        raise _fail("cycleId", "신청할 수 없는 교육기수입니다.")
    if _blocking(db, bundle_sn, member_sn, int(body.cycle_id), now):
        raise _fail("cycleId", "같은 기수에 접수 중이거나 승인된 심사가 있습니다.")
    created = int(
        db.execute(
            TB_RDCT_BFHD_SRNG.insert()
            .values(
                OPER_BNDL_SN=bundle_sn,
                MBR_SN=member_sn,
                EDU_CYCL_SN=int(body.cycle_id),
                RDCT_TYPE_CD=TYPE_CODE[body.reduction_type],
                SRNG_STTS_CD=STATUS_CODE[ReductionStatus.RECEIVED],
                APLY_DT=now,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job=APPLY_JOB,
        table="TB_RDCT_BFHD_SRNG",
        key=created,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"{body.reduction_type.value} 신청 {mark}",
    )
    return get_mine(db, bundle_sn=bundle_sn, member_sn=member_sn, review_id=str(created))


def withdraw_mine(
    db: Session, *, bundle_sn: int, member_sn: int, review_id: str, now: datetime, request_id: str
) -> MyReduction:
    """접수 상태일 때만 철회한다. 증빙은 보존기간 규칙을 따르므로 지우지 않는다. 결정된 신청은 새로 신청한다."""
    _mine(db, bundle_sn, member_sn, review_id)
    _member(db, bundle_sn, member_sn, lock=True)  # 회원 → 심사 순서로 잠근다(관리자 결정·재심사와 같다)
    db.execute(
        select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN)
        .where(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == int(review_id))
        .with_for_update()
    ).one()
    row = _mine(db, bundle_sn, member_sn, review_id)  # 잠근 뒤 다시 읽는다
    if CODE_STATUS[str(row.SRNG_STTS_CD)] is not ReductionStatus.RECEIVED:
        raise ApiError(ErrorCode.CONFLICT_STATE, "접수 상태인 신청만 철회할 수 있습니다.")
    update_versioned(
        db,
        TB_RDCT_BFHD_SRNG,
        {"OPER_BNDL_SN": bundle_sn, "RDCT_BFHD_SRNG_SN": int(review_id)},
        int(row.RCRD_VER),
        {"SRNG_STTS_CD": STATUS_CODE[ReductionStatus.REVOKED]},
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="RDCT_WITHDRAW",
        table="TB_RDCT_BFHD_SRNG",
        key=int(review_id),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="신청 철회",
    )
    return get_mine(db, bundle_sn=bundle_sn, member_sn=member_sn, review_id=review_id)
