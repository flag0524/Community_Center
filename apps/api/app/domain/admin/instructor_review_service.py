# 관리자 강사 심사(AU.INSTR_W). 방문·외부 접수 등록과 승인·반려·활동중지를 서버가 판정한다. 승인해도 강좌 배정·관리자 권한은 자동으로 주지 않는다(FN-051, DV110, ADR-062)
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, func, or_, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit
from app.auth.crypto import DecryptError, decrypt, encrypt
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.idempotent import insert_idempotent
from app.db.tables import TB_INSTR, TB_INSTR_APLY, TB_INSTR_RCRT, TB_JOB_HSTRY, TB_MBR
from app.db.versioned import update_versioned
from app.domain.admin.education_types import ApplicationSource, ReviewStatus
from app.domain.admin.instructor_review_schemas import (
    InstructorReview,
    InstructorReviewCreate,
    InstructorReviewPage,
    InstructorReviewSummary,
    InstructorReviewWrite,
)
from app.domain.admin.types import AdminAuthority as AU

SOURCE_CODE = {
    ApplicationSource.ONLINE: "IC.ONLINE",
    ApplicationSource.VISIT: "IC.VISIT",
    ApplicationSource.EXTERNAL: "IC.EXTERNAL",
}
CODE_SOURCE = {code: source for source, code in SOURCE_CODE.items()}
REVIEW_JOB = "INSTR_REVIEW"
# 한 번 심사하면 심사대기로 되돌리지 않는다. 반려는 끝이고 승인·활동중지는 서로 오갈 수 있다
ALLOWED = {
    ReviewStatus.PENDING: {ReviewStatus.PENDING, ReviewStatus.APPROVED, ReviewStatus.REJECTED},
    ReviewStatus.APPROVED: {ReviewStatus.APPROVED, ReviewStatus.SUSPENDED},
    ReviewStatus.SUSPENDED: {ReviewStatus.SUSPENDED, ReviewStatus.APPROVED},
    ReviewStatus.REJECTED: set(),
}


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _whole(db: Session, admin: Admin, now: datetime) -> None:
    """강사 승인은 묶음 공통의 일이라 묶음 전체 범위의 담당자만 한다(R28)."""
    if not permit(db, admin, AU.INSTR_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _base(bundle_sn: int) -> Select[Any]:
    source = TB_INSTR_APLY.outerjoin(
        TB_INSTR,
        (TB_INSTR.c.OPER_BNDL_SN == TB_INSTR_APLY.c.OPER_BNDL_SN)
        & (TB_INSTR.c.INSTR_SN == TB_INSTR_APLY.c.INSTR_SN),
    )
    return (
        select(
            TB_INSTR_APLY,
            TB_INSTR.c.INSTR_STTS_CD.label("INSTR_STTS"),
            TB_INSTR.c.RLS_YN.label("INSTR_RLS"),
            TB_INSTR.c.RJCT_RSN.label("INSTR_RSN"),
        )
        .select_from(source)
        .where(TB_INSTR_APLY.c.OPER_BNDL_SN == bundle_sn)
    )


def _status(row: Any) -> ReviewStatus:
    if row.SRNG_STTS_CD == "IA.WAIT":
        return ReviewStatus.PENDING
    if row.SRNG_STTS_CD == "IA.REJECT":
        return ReviewStatus.REJECTED
    return ReviewStatus.SUSPENDED if row.INSTR_STTS == "IS.STOP" else ReviewStatus.APPROVED


def _public(row: Any) -> bool:
    return _status(row) is ReviewStatus.APPROVED and row.INSTR_RLS == "Y"


def _summary(row: Any) -> InstructorReviewSummary:
    return InstructorReviewSummary(
        application_id=str(int(row.INSTR_APLY_SN)),
        applicant_name=str(row.APLCT_NM),
        desired_course=str(row.HOPE_CORS_NM),
        received_on=kst_today(row.SBMSN_DT),
        status=_status(row),
        is_public=_public(row),
    )


def _memo(db: Session, bundle_sn: int, application_sn: int) -> str | None:
    """검토 메모는 심사 작업이력의 가장 최근 값이다(메모를 담을 컬럼이 없다, 개정 요청 R36)."""
    note = db.execute(
        select(TB_JOB_HSTRY.c.CHG_CN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == REVIEW_JOB,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(application_sn),
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
        .limit(1)
    ).scalar()
    return None if note is None else json.loads(str(note)).get("memo")


def _detail(db: Session, bundle_sn: int, row: Any) -> InstructorReview:
    status = _status(row)
    reason = (
        row.RJCT_RSN
        if status is ReviewStatus.REJECTED
        else row.INSTR_RSN
        if status is ReviewStatus.SUSPENDED
        else None
    )
    return InstructorReview(
        **_summary(row).model_dump(),
        category_name=None if row.HOPE_FLD_NM is None else str(row.HOPE_FLD_NM),
        career="" if row.CRR_CN is None else str(row.CRR_CN),
        source=CODE_SOURCE[str(row.RCPT_CHNL_CD)],
        reason=None if reason is None else str(reason),
        memo=_memo(db, bundle_sn, int(row.INSTR_APLY_SN)),
        version=int(row.RCRD_VER),
        can_review=True,  # 심사 권한이 있는 담당자만 이 화면에 온다
    )


def list_reviews(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    q: str | None,
    status: ReviewStatus | None,
    is_public: bool | None,
    page: int,
    size: int,
) -> InstructorReviewPage:
    """심사대기가 먼저이고 각각 최근 접수가 먼저다."""
    _whole(db, admin, now)
    query = _base(admin.bundle_sn)
    if q and q.strip():
        needle = q.strip()
        query = query.where(
            or_(
                TB_INSTR_APLY.c.APLCT_NM.contains(needle, autoescape=True),
                TB_INSTR_APLY.c.HOPE_CORS_NM.contains(needle, autoescape=True),
            )
        )
    stopped = TB_INSTR.c.INSTR_STTS_CD == "IS.STOP"
    if status is ReviewStatus.PENDING:
        query = query.where(TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.WAIT")
    elif status is ReviewStatus.REJECTED:
        query = query.where(TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.REJECT")
    elif status is ReviewStatus.SUSPENDED:
        query = query.where(TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.APPROVE", stopped)
    elif status is ReviewStatus.APPROVED:
        query = query.where(
            TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.APPROVE", or_(TB_INSTR.c.INSTR_STTS_CD.is_(None), ~stopped)
        )
    if is_public is not None:
        public = _public_filter()
        query = query.where(public if is_public else ~public)
    query = query.order_by(
        case((TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.WAIT", 0), else_=1),
        TB_INSTR_APLY.c.SBMSN_DT.desc(),
        TB_INSTR_APLY.c.INSTR_APLY_SN.desc(),
    )
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return InstructorReviewPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _public_filter() -> Any:
    """공개 중인 강사: 승인(활동중지 아님)이고 공개 여부가 Y다."""
    return (
        (TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.APPROVE")
        & (TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE")
        & (TB_INSTR.c.RLS_YN == "Y")
    )


def _load(db: Session, admin: Admin, now: datetime, application_id: str) -> Any:
    _whole(db, admin, now)
    row = db.execute(
        _base(admin.bundle_sn).where(TB_INSTR_APLY.c.INSTR_APLY_SN == int(application_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_review(db: Session, admin: Admin, *, now: datetime, application_id: str) -> InstructorReview:
    return _detail(db, admin.bundle_sn, _load(db, admin, now, application_id))


def _audit(
    db: Session, admin: Admin, job: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_INSTR_APLY",
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def create_review(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    body: InstructorReviewCreate,
    idem_key: str,
) -> InstructorReview:
    """방문·외부로 받은 지원서를 대신 등록한다. 처음 상태는 심사대기다. 전화번호는 암호화해 저장하고 어디에도 되돌려 주지 않는다."""
    _whole(db, admin, now)
    if body.source is ApplicationSource.ONLINE:
        raise _fail(
            "source", "온라인 지원은 주민 화면으로만 들어옵니다. 방문·외부 접수만 등록할 수 있습니다."
        )
    recruitment = db.execute(
        select(TB_INSTR_RCRT.c.INSTR_RCRT_SN).where(
            TB_INSTR_RCRT.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_INSTR_RCRT.c.INSTR_RCRT_SN == int(body.recruitment_id),
        )
    ).first()
    if recruitment is None:
        raise _fail("recruitmentId", "모집 공고를 찾을 수 없습니다.")
    member_sn: int | None = None
    if body.member_login_id:
        found = db.execute(
            select(TB_MBR.c.MBR_SN, TB_MBR.c.MBR_STTS_CD).where(
                TB_MBR.c.OPER_BNDL_SN == admin.bundle_sn, TB_MBR.c.LGN_ID == body.member_login_id.strip()
            )
        ).first()
        if found is None or found.MBR_STTS_CD == "MS.WITHDRAW":
            raise _fail("memberLoginId", "연결할 회원을 찾을 수 없습니다.")
        member_sn = int(found.MBR_SN)
    name, course, career = body.applicant_name.strip(), body.desired_course.strip(), body.career.strip()
    for field, value in (("applicantName", name), ("desiredCourse", course), ("career", career)):
        if not value:
            raise _fail(field, "필수 항목입니다.")
    values: dict[str, Any] = {
        "OPER_BNDL_SN": admin.bundle_sn,
        "INSTR_RCRT_SN": int(body.recruitment_id),
        "RCPT_CHNL_CD": SOURCE_CODE[body.source],
        "MBR_SN": member_sn,
        "APLCT_NM": name,
        "TELNO_ENCPT_VL": encrypt(settings.secret_key, body.phone),
        "HOPE_CORS_NM": course,
        "CRR_CN": career,
        "RLS_HOPE_YN": "N",
        "SBMSN_DT": now,
        "RCPT_MNGR_SN": admin.admin_sn,
        "SRNG_STTS_CD": "IA.WAIT",
        "IDEM_KEY": f"admin-{idem_key}",
        "REG_DT": now,
        "RCRD_VER": 1,
    }

    def same(existing: Any) -> bool:
        try:
            phone = decrypt(settings.secret_key, str(existing["TELNO_ENCPT_VL"]))
        except DecryptError:
            return False
        return (
            existing["APLCT_NM"] == name
            and existing["HOPE_CORS_NM"] == course
            and existing["CRR_CN"] == career
            and existing["RCPT_CHNL_CD"] == values["RCPT_CHNL_CD"]
            and int(existing["INSTR_RCRT_SN"]) == int(body.recruitment_id)
            and (None if existing["MBR_SN"] is None else int(existing["MBR_SN"])) == member_sn
            and phone == body.phone
        )

    created, replayed = insert_idempotent(db, TB_INSTR_APLY, values, same)
    sn = int(created["INSTR_APLY_SN"])
    if not replayed:
        _audit(db, admin, "INSTR_APLY_CREATE", sn, request_id, now, f"{body.source.value} 접수")
    return get_review(db, admin, now=now, application_id=str(sn))


def _need_reason(target: ReviewStatus, body: InstructorReviewWrite) -> str | None:
    reason = body.reason.strip() if body.reason else None
    if target in (ReviewStatus.REJECTED, ReviewStatus.SUSPENDED) and not reason:
        raise _fail("reason", "반려·활동중지는 사유가 필요합니다.")
    if body.is_public and target is not ReviewStatus.APPROVED:
        raise _fail("isPublic", "공개는 승인된 강사만 할 수 있습니다.")
    return reason


def review(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    application_id: str,
    body: InstructorReviewWrite,
) -> InstructorReview:
    """심사 결과를 정한다. 반려·활동중지는 사유가 필수이고 공개는 승인된 강사만 가능하다. 강좌 배정과 관리자 권한은 주지 않는다."""
    _load(db, admin, now, application_id)
    db.execute(
        select(TB_INSTR_APLY.c.INSTR_APLY_SN)
        .where(TB_INSTR_APLY.c.INSTR_APLY_SN == int(application_id))
        .with_for_update()
    ).one()
    row = _load(db, admin, now, application_id)  # 잠근 뒤 상태를 다시 읽는다
    if body.version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    current, target = _status(row), body.status
    if target not in ALLOWED[current]:
        message = (
            "반려한 지원은 다시 심사할 수 없습니다. 새 지원서를 받아 주세요."
            if current is ReviewStatus.REJECTED
            else "이 상태에서는 선택한 결과로 바꿀 수 없습니다."
        )
        raise ApiError(ErrorCode.CONFLICT_STATE, message)
    reason = _need_reason(target, body)
    sn = int(row.INSTR_APLY_SN)
    changes: dict[str, Any] = {}
    if current is ReviewStatus.PENDING and target is not ReviewStatus.PENDING:
        changes.update(SRNG_MNGR_SN=admin.admin_sn, SRNG_DT=now)
    if target is ReviewStatus.REJECTED:
        changes.update(SRNG_STTS_CD="IA.REJECT", RJCT_RSN=reason)
    elif target is ReviewStatus.APPROVED and current is ReviewStatus.PENDING:
        changes.update(
            SRNG_STTS_CD="IA.APPROVE", INSTR_SN=_approve_instructor(db, admin, now, row, body.is_public)
        )
    elif current in (ReviewStatus.APPROVED, ReviewStatus.SUSPENDED) and row.INSTR_SN is not None:
        _update_instructor(db, now, admin, row, target, reason, body.is_public)
    update_versioned(
        db, TB_INSTR_APLY, {"OPER_BNDL_SN": admin.bundle_sn, "INSTR_APLY_SN": sn}, body.version, changes
    )
    memo = body.memo.strip() if body.memo and body.memo.strip() else None
    _audit(
        db,
        admin,
        REVIEW_JOB,
        sn,
        request_id,
        now,
        json.dumps({"s": target.value, "memo": memo}, ensure_ascii=False),
    )
    return get_review(db, admin, now=now, application_id=application_id)


def _approve_instructor(db: Session, admin: Admin, now: datetime, row: Any, public: bool) -> int:
    """승인하면 회원에 강사 행을 만든다. 회원과 연결된 지원서만 승인할 수 있다(사용자 확정 2026-11-13)."""
    if row.MBR_SN is None:
        raise _fail("status", "회원과 연결되지 않은 지원서는 승인할 수 없습니다. 회원 가입 후 연결해 주세요.")
    existing = db.execute(
        select(TB_INSTR.c.INSTR_SN)
        .where(TB_INSTR.c.OPER_BNDL_SN == admin.bundle_sn, TB_INSTR.c.MBR_SN == row.MBR_SN)
        .with_for_update()
    ).first()
    values: dict[str, Any] = {
        "INSTR_STTS_CD": "IS.APPROVE",
        "INSTR_INTRO_CN": row.INSTR_INTRO_CN,
        "CRR_CN": row.CRR_CN,
        "APRV_DT": now,
        "APRV_MNGR_SN": admin.admin_sn,
        "RJCT_RSN": None,
        "RLS_YN": "Y" if public else "N",
    }
    if existing is not None:
        db.execute(
            update(TB_INSTR)
            .where(TB_INSTR.c.INSTR_SN == existing.INSTR_SN)
            .values(**values, MDFCN_DT=now, RCRD_VER=TB_INSTR.c.RCRD_VER + 1)
        )
        return int(existing.INSTR_SN)
    return int(
        db.execute(
            TB_INSTR.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                MBR_SN=row.MBR_SN,
                APLY_DT=row.SBMSN_DT,
                REG_DT=now,
                RCRD_VER=1,
                **values,
            )
            .returning(TB_INSTR.c.INSTR_SN)
        ).scalar_one()
    )


def _update_instructor(
    db: Session, now: datetime, admin: Admin, row: Any, target: ReviewStatus, reason: str | None, public: bool
) -> None:
    values: dict[str, Any]
    if target is ReviewStatus.SUSPENDED:
        values = {"INSTR_STTS_CD": "IS.STOP", "RJCT_RSN": reason, "RLS_YN": "N"}
    else:
        values = {"INSTR_STTS_CD": "IS.APPROVE", "RJCT_RSN": None, "RLS_YN": "Y" if public else "N"}
        if row.INSTR_STTS == "IS.STOP":  # 활동중지에서 다시 승인할 때 승인자와 일시를 새로 남긴다
            values.update(APRV_DT=now, APRV_MNGR_SN=admin.admin_sn)
    db.execute(
        update(TB_INSTR)
        .where(TB_INSTR.c.INSTR_SN == row.INSTR_SN)
        .values(**values, MDFCN_DT=now, RCRD_VER=TB_INSTR.c.RCRD_VER + 1)
    )
