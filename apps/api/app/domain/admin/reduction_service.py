# 관리자 감면 사전심사(조회 AU.APLY_R, 증빙 열람·심사·재심사 AU.APLY_W, 범위는 회원의 거주 동). 승인·반려는 접수 건만 한 번 하고 재심사는 새 건이다(FN-038, ADR-063)
import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_EDU_CYCL,
    TB_FILE,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_MNGR,
    TB_RDCT_BFHD_SRNG,
    TB_RDCT_HSTRY,
    TB_RDCT_HSTRY_FILE,
)
from app.db.versioned import update_versioned
from app.domain.admin.file_service import EVIDENCE_VIEW_JOB
from app.domain.admin.file_service import STATUS as FILE_STATUS
from app.domain.admin.reduction_schemas import (
    EvidenceView,
    ReductionDecisionRequest,
    ReductionEvidence,
    ReductionHistoryPage,
    ReductionHistoryRow,
    ReductionReview,
    ReductionReviewPage,
    ReductionReviewSummary,
)
from app.domain.admin.reduction_types import ReductionDecision, ReductionStatus, ReductionType
from app.domain.admin.refund_service import kst_start, mask_name
from app.domain.admin.types import AdminAuthority as AU

TYPE_CODE = {
    ReductionType.LIVELIHOOD: "DR.LIVELIHD",
    ReductionType.VETERAN: "DR.VETERAN",
    ReductionType.DISABLED: "DR.DISABLED",
}
CODE_TYPE = {code: kind for kind, code in TYPE_CODE.items()}
STATUS_CODE = {
    ReductionStatus.RECEIVED: "DS.RECEIVED",
    ReductionStatus.APPROVED: "DS.APPROVED",
    ReductionStatus.REJECTED: "DS.REJECTED",
    ReductionStatus.REVOKED: "DS.REVOKED",
}
CODE_STATUS = {code: status for status, code in STATUS_CODE.items()}
RESULT = {"DR.APPROVE": ReductionDecision.APPROVE, "DR.REJECT": ReductionDecision.REJECT}
RESULT_CODE = {value: code for code, value in RESULT.items()}
DECIDED = (ReductionStatus.APPROVED, ReductionStatus.REJECTED)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _covers(scope: Scope, dong_sn: Any) -> bool:
    return scope.covers(None if dong_sn is None else int(dong_sn))


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    return query if scope.whole else query.where(TB_MBR.c.DONG_SN.in_(scope.dongs))


def _valid_end(day: date) -> datetime:
    """유효 종료일의 마지막 순간(한국 시각 23:59:59)을 DB의 UTC 시각으로. 그날까지 쓸 수 있고 다음 날부터 못 쓴다."""
    return kst_start(day + timedelta(days=1)) - timedelta(seconds=1)


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


def _base(bundle_sn: int) -> Select[Any]:
    return (
        select(
            TB_RDCT_BFHD_SRNG,
            TB_MBR.c.MBR_NM,
            TB_MBR.c.DONG_SN,
            TB_MBR.c.HAB_RGN_CD,
            TB_MBR.c.HAB_IDNTY_STTS_CD,
            TB_EDU_CYCL.c.EDU_CYCL_NM,
            TB_MNGR.c.MNGR_NM.label("REVIEWER_NM"),
            _evidence_count().label("EVIDENCE_CNT"),
        )
        .select_from(TB_RDCT_BFHD_SRNG)
        .join(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN)
            & (TB_MBR.c.MBR_SN == TB_RDCT_BFHD_SRNG.c.MBR_SN),
        )
        .join(
            TB_EDU_CYCL,
            (TB_EDU_CYCL.c.OPER_BNDL_SN == TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN)
            & (TB_EDU_CYCL.c.EDU_CYCL_SN == TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN),
        )
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_RDCT_BFHD_SRNG.c.SRNG_MNGR_SN)
        .where(TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == bundle_sn)
    )


def _summary(row: Any) -> ReductionReviewSummary:
    return ReductionReviewSummary(
        review_id=str(int(row.RDCT_BFHD_SRNG_SN)),
        member_name=mask_name(str(row.MBR_NM)),
        cycle_name=str(row.EDU_CYCL_NM),
        reduction_type=CODE_TYPE[str(row.RDCT_TYPE_CD)],
        evidence_count=int(row.EVIDENCE_CNT),
        applied_on=kst_today(row.APLY_DT),
        status=CODE_STATUS[str(row.SRNG_STTS_CD)],
    )


def list_reductions(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    status: ReductionStatus | None,
    cycle_id: str | None,
    page: int,
    size: int,
) -> ReductionReviewPage:
    """접수된 심사가 먼저이고 접수는 오래된 신청부터, 나머지는 최근 신청부터 나온다."""
    query = _in_scope(_base(admin.bundle_sn), permit(db, admin, AU.APLY_R, now))
    received = TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == STATUS_CODE[ReductionStatus.RECEIVED]
    if status is not None:
        query = query.where(TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == STATUS_CODE[status])
    if cycle_id is not None:
        query = query.where(TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN == int(cycle_id))
    query = query.order_by(
        case((received, 0), else_=1),
        case((received, TB_RDCT_BFHD_SRNG.c.APLY_DT), else_=None).asc(),
        TB_RDCT_BFHD_SRNG.c.APLY_DT.desc(),
        TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN.desc(),
    )
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return ReductionReviewPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _evidence(db: Session, bundle_sn: int, review_sn: int) -> list[ReductionEvidence]:
    rows = db.execute(
        select(TB_FILE.c.FILE_SN, TB_FILE.c.FILE_NM, TB_FILE.c.FILE_SZ, TB_FILE.c.FILE_STTS_CD)
        .where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.RDCT_BFHD_SRNG_SN == review_sn,
            TB_FILE.c.FILE_STTS_CD != "FS.DELETE",
        )
        .order_by(TB_FILE.c.FILE_SN)
    )
    return [
        ReductionEvidence(
            file_id=str(int(r.FILE_SN)),
            file_name=str(r.FILE_NM),
            size_bytes=int(r.FILE_SZ),
            status=FILE_STATUS[str(r.FILE_STTS_CD)],
        )
        for r in rows
    ]


def _views(db: Session, bundle_sn: int, review_sn: int) -> list[EvidenceView]:
    names = {
        str(int(r.FILE_SN)): str(r.FILE_NM)
        for r in db.execute(
            select(TB_FILE.c.FILE_SN, TB_FILE.c.FILE_NM).where(
                TB_FILE.c.OPER_BNDL_SN == bundle_sn, TB_FILE.c.RDCT_BFHD_SRNG_SN == review_sn
            )
        )
    }
    rows = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT, TB_MNGR.c.MNGR_NM, TB_JOB_HSTRY.c.CHG_CN)
        .join(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == EVIDENCE_VIEW_JOB,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(review_sn),
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
    )
    return [
        EvidenceView(at=utc(r.REG_DT), by=str(r.MNGR_NM), file_name=names.get(str(r.CHG_CN), "삭제된 파일"))
        for r in rows
    ]


def _detail(db: Session, admin: Admin, now: datetime, row: Any) -> ReductionReview:
    review_sn = int(row.RDCT_BFHD_SRNG_SN)
    status = CODE_STATUS[str(row.SRNG_STTS_CD)]
    writable = _covers(permit_scope(db, admin, AU.APLY_W, now), row.DONG_SN)
    sibling = status in DECIDED and _open_sibling(db, admin.bundle_sn, row)
    return ReductionReview(
        **_summary(row).model_dump(),
        residence_confirmed=_resident(row),
        evidence=_evidence(db, admin.bundle_sn, review_sn) if writable else [],
        evidence_views=_views(db, admin.bundle_sn, review_sn) if writable else [],
        reviewed_by=None if row.REVIEWER_NM is None else str(row.REVIEWER_NM),
        reviewed_at=None if row.SRNG_DT is None else utc(row.SRNG_DT),
        review_note=None if row.SRNG_CN is None else str(row.SRNG_CN),
        reject_reason=None if row.RJCT_RSN is None else str(row.RJCT_RSN),
        valid_until=None if row.VLD_END_DT is None else kst_today(row.VLD_END_DT),
        version=int(row.RCRD_VER),
        can_decide=writable and status is ReductionStatus.RECEIVED,
        can_re_review=writable and status in DECIDED and not sibling,
        can_view_evidence=writable,
    )


def permit_scope(db: Session, admin: Admin, authority: AU, now: datetime) -> Scope:
    """권한이 없는 담당자에게는 비어 있는 범위를 준다. 조회 권한은 따로 확인했다."""
    try:
        return permit(db, admin, authority, now)
    except ApiError:
        return Scope()


def _resident(row: Any) -> bool:
    """조리읍 거주를 센터가 확인한 회원이다. 승인은 이 회원만 받는다(FN-038)."""
    return bool(row.HAB_RGN_CD == "RA.JORI" and row.HAB_IDNTY_STTS_CD == "RV.OK")


def _open_sibling(db: Session, bundle_sn: int, row: Any) -> bool:
    """같은 회원·기수에 접수 중인 다른 심사가 있다."""
    return (
        db.execute(
            select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN).where(
                TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == bundle_sn,
                TB_RDCT_BFHD_SRNG.c.MBR_SN == row.MBR_SN,
                TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN == row.EDU_CYCL_SN,
                TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == STATUS_CODE[ReductionStatus.RECEIVED],
            )
        ).first()
        is not None
    )


def _load(db: Session, admin: Admin, now: datetime, review_id: str, authority: AU) -> Any:
    scope = permit(db, admin, authority, now)
    row = db.execute(
        _base(admin.bundle_sn).where(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == int(review_id))
    ).first()
    if row is None or not _covers(scope, row.DONG_SN):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_reduction(db: Session, admin: Admin, *, now: datetime, review_id: str) -> ReductionReview:
    return _detail(db, admin, now, _load(db, admin, now, review_id, AU.APLY_R))


def _lock(db: Session, admin: Admin, now: datetime, review_id: str) -> Any:
    """회원 행을 먼저, 심사 행을 다음에 잠근다(재심사·회원 쪽 신청과 같은 순서). 잠근 뒤 다시 읽는다."""
    row = _load(db, admin, now, review_id, AU.APLY_W)
    db.execute(
        select(TB_MBR.c.MBR_SN)
        .where(TB_MBR.c.OPER_BNDL_SN == admin.bundle_sn, TB_MBR.c.MBR_SN == row.MBR_SN)
        .with_for_update()
    ).one()
    db.execute(
        select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN)
        .where(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == row.RDCT_BFHD_SRNG_SN)
        .with_for_update()
    ).one()
    return _load(db, admin, now, review_id, AU.APLY_W)


def _check(
    body: ReductionDecisionRequest, row: Any, now: datetime
) -> tuple[str | None, str | None, date | None]:
    note = body.review_note.strip() if body.review_note and body.review_note.strip() else None
    reason = body.reject_reason.strip() if body.reject_reason and body.reject_reason.strip() else None
    if body.decision is ReductionDecision.APPROVE:
        if reason is not None:
            raise _fail("rejectReason", "승인에는 반려 사유를 입력하지 않습니다.")
        if body.valid_until is None:
            raise _fail("validUntil", "승인은 유효 종료일이 필요합니다.")
        if body.valid_until < kst_today(now):
            raise _fail("validUntil", "유효 종료일은 오늘 이후여야 합니다.")
        if not _resident(row):
            raise _fail("decision", "조리읍 거주가 확인되지 않은 회원은 승인할 수 없습니다.")
        return note, None, body.valid_until
    if reason is None:
        raise _fail("rejectReason", "반려는 사유가 필요합니다.")
    if body.valid_until is not None:
        raise _fail("validUntil", "반려에는 유효 종료일을 입력하지 않습니다.")
    return note, reason, None


def decide_reduction(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    review_id: str,
    body: ReductionDecisionRequest,
) -> ReductionReview:
    """접수 건만 승인·반려한다. 결정한 뒤에는 고치지 않고 다시 보려면 재심사로 새 건을 만든다."""
    row = _lock(db, admin, now, review_id)
    if body.version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    if CODE_STATUS[str(row.SRNG_STTS_CD)] is not ReductionStatus.RECEIVED:
        raise ApiError(
            ErrorCode.CONFLICT_STATE,
            "접수 상태인 심사만 결정할 수 있습니다. 다시 보려면 재심사를 요청하세요.",
        )
    note, reason, valid_until = _check(body, row, now)
    approve = body.decision is ReductionDecision.APPROVE
    update_versioned(
        db,
        TB_RDCT_BFHD_SRNG,
        {"OPER_BNDL_SN": admin.bundle_sn, "RDCT_BFHD_SRNG_SN": int(row.RDCT_BFHD_SRNG_SN)},
        body.version,
        {
            "SRNG_STTS_CD": STATUS_CODE[ReductionStatus.APPROVED if approve else ReductionStatus.REJECTED],
            "SRNG_MNGR_SN": admin.admin_sn,
            "SRNG_DT": now,
            "SRNG_CN": note,
            "RJCT_RSN": reason,
            "VLD_END_DT": None if valid_until is None else _valid_end(valid_until),
        },
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job="RDCT_REVIEW_APPROVE" if approve else "RDCT_REVIEW_REJECT",
        table="TB_RDCT_BFHD_SRNG",
        key=int(row.RDCT_BFHD_SRNG_SN),
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=json.dumps({"validUntil": None if valid_until is None else valid_until.isoformat()}),
    )
    return get_reduction(db, admin, now=now, review_id=review_id)


def _marker(idem_key: str, review_id: str) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"re-review:{review_id}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _replayed(db: Session, admin: Admin, mark: str) -> int | None:
    """같은 키로 이미 만들었으면 그 번호를 준다. 다른 심사에 같은 키를 쓰면 409다."""
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == "RDCT_RE_REVIEW",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def re_review_reduction(
    db: Session, admin: Admin, *, now: datetime, request_id: str, review_id: str, idem_key: str
) -> ReductionReview:
    """결정된 심사를 그대로 두고 같은 회원·기수·유형의 새 심사건을 접수 상태로 만든다(증빙은 새로 받는다)."""
    row = _lock(db, admin, now, review_id)
    mark = _marker(idem_key, review_id)
    prior = _replayed(db, admin, mark)
    if prior is not None:
        return get_reduction(db, admin, now=now, review_id=str(prior))
    if CODE_STATUS[str(row.SRNG_STTS_CD)] not in DECIDED:
        raise ApiError(ErrorCode.CONFLICT_STATE, "승인·반려된 심사만 재심사할 수 있습니다.")
    if _open_sibling(db, admin.bundle_sn, row):
        raise ApiError(ErrorCode.CONFLICT_STATE, "같은 회원·기수에 접수 중인 심사가 있습니다.")
    created = int(
        db.execute(
            TB_RDCT_BFHD_SRNG.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                MBR_SN=row.MBR_SN,
                EDU_CYCL_SN=row.EDU_CYCL_SN,
                RDCT_TYPE_CD=row.RDCT_TYPE_CD,
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
        actor="AK.ADMIN",
        job="RDCT_RE_REVIEW",
        table="TB_RDCT_BFHD_SRNG",
        key=created,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"원 심사 {review_id} {mark}",
    )
    return get_reduction(db, admin, now=now, review_id=str(created))


def list_history(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    result: ReductionDecision | None,
    from_date: date | None,
    to_date: date | None,
    page: int,
    size: int,
) -> ReductionHistoryPage:
    """신청에 적용된 감면 판정 이력. 판정마다 새 행이 쌓이고 고치지 않으며 범위는 신청한 강좌의 동이다."""
    scope = permit(db, admin, AU.APLY_R, now)
    files = (
        select(func.count())
        .where(
            TB_RDCT_HSTRY_FILE.c.OPER_BNDL_SN == TB_RDCT_HSTRY.c.OPER_BNDL_SN,
            TB_RDCT_HSTRY_FILE.c.RDCT_HSTRY_SN == TB_RDCT_HSTRY.c.RDCT_HSTRY_SN,
        )
        .scalar_subquery()
    )
    query = (
        select(
            TB_RDCT_HSTRY,
            TB_MBR.c.MBR_NM,
            TB_EDU_CYCL.c.EDU_CYCL_NM,
            TB_MNGR.c.MNGR_NM,
            files.label("FILE_CNT"),
        )
        .select_from(TB_RDCT_HSTRY)
        .join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_RDCT_HSTRY.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_RDCT_HSTRY.c.ATNLC_APLY_SN),
        )
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
        .join(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN),
        )
        .join(
            TB_EDU_CYCL,
            (TB_EDU_CYCL.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN)
            & (TB_EDU_CYCL.c.EDU_CYCL_SN == TB_CORS.c.EDU_CYCL_SN),
        )
        .join(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_RDCT_HSTRY.c.DCSN_MNGR_SN)
        .where(TB_RDCT_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn)
    )
    if not scope.whole:
        query = query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    if result is not None:
        query = query.where(TB_RDCT_HSTRY.c.DCSN_RSLT_CD == RESULT_CODE[result])
    if from_date is not None:
        query = query.where(TB_RDCT_HSTRY.c.DCSN_DT >= kst_start(from_date))
    if to_date is not None:
        query = query.where(TB_RDCT_HSTRY.c.DCSN_DT < kst_start(to_date + timedelta(days=1)))
    query = query.order_by(TB_RDCT_HSTRY.c.DCSN_DT.desc(), TB_RDCT_HSTRY.c.RDCT_HSTRY_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return ReductionHistoryPage(
        items=[
            ReductionHistoryRow(
                history_id=str(int(r.RDCT_HSTRY_SN)),
                decided_at=utc(r.DCSN_DT),
                member_name=mask_name(str(r.MBR_NM)),
                cycle_name=str(r.EDU_CYCL_NM),
                result=RESULT[str(r.DCSN_RSLT_CD)],
                amount=None if r.RDCT_AMT is None else int(r.RDCT_AMT),
                reason=None if r.DCSN_RSN is None else str(r.DCSN_RSN),
                decided_by=str(r.MNGR_NM),
                evidence_count=int(r.FILE_CNT),
                application_no=str(int(r.ATNLC_APLY_SN)),
            )
            for r in rows
        ],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )
