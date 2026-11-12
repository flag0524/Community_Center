# 관리자 회원 조회·연락처 열람·검토 기록·거주지 확인(AU.MBR_R, FN-065, ADR-054). 회원 정보를 고치는 기능은 거주지 확인 결과뿐이다
import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_JOB_HSTRY, TB_MBR, TB_MNGR, TB_STLM
from app.domain.admin import application_service as applications
from app.domain.admin.member_schemas import (
    AdminMember,
    AdminMemberPage,
    AdminMemberSummary,
    MemberApplication,
    MemberContact,
    MemberReview,
    MemberReviewClose,
    MemberReviewCreate,
    ResidenceRecord,
    RevealRequest,
)
from app.domain.admin.member_types import MemberReviewKind, MemberReviewState, MemberStatus
from app.domain.admin.refund_service import mask_name, scoped
from app.domain.admin.types import AdminAuthority as AU
from app.domain.member.types import ResidenceStatus

STATUS = {
    "MS.ACTIVE": MemberStatus.ACTIVE,
    "MS.LOCKED": MemberStatus.LOCKED,
    "MS.WITHDRAW": MemberStatus.WITHDRAWN,
}
STATUS_CODE = {value: code for code, value in STATUS.items()}
APPLICATION_LIMIT = 50  # 상세에 보이는 최근 신청 수. 전체 건수는 따로 준다
REVIEW_JOB, CLOSE_JOB = "MBR_REVIEW", "MBR_REVIEW_CLOSE"
IDEM_MARK = re.compile(r"\s\[idem [0-9a-f]{16}:[0-9a-f]{16}\]$")
CLOSE_TEXT = re.compile(r"^\[review (\d+)\] (.*)$", re.DOTALL)
KIND_TEXT = re.compile(r"^\[([A-Z_]+)\] (.*)$", re.DOTALL)


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return f"{phone[:3]}-****-{phone[-4:]}" if len(phone) >= 10 else "****"


def mask_email(email: str | None) -> str:
    if not email:
        return ""
    local, at, domain = email.partition("@")
    return f"{local[:1]}***{at}{domain}" if at else "***"


def _summary(row: Any) -> AdminMemberSummary:
    return AdminMemberSummary(
        member_id=str(int(row.MBR_SN)),
        login_id=str(row.LGN_ID),
        name_masked=mask_name(str(row.MBR_NM)),
        residence_declared=None,  # 회원이 입력한 거주 구분을 담는 컬럼이 없다(개정 요청 R33)
        residence_status=ResidenceStatus.VERIFIED
        if row.HAB_IDNTY_STTS_CD == "RV.OK"
        else ResidenceStatus.UNVERIFIED,
        joined_on=kst_today(row.MBR_JOIN_DT),
        status=STATUS[str(row.MBR_STTS_CD)],
    )


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    """회원의 범위는 회원 레코드의 거주 동이다. 동이 없는 회원은 묶음 전체 범위만 본다."""
    return query if scope.whole else query.where(TB_MBR.c.DONG_SN.in_(scope.dongs))


def _filtered(
    db: Session, admin: Admin, now: datetime, *, q: str | None, status: MemberStatus | None
) -> Select[Any]:
    """목록과 개인식별 명단 내보내기가 함께 쓰는 조회. 권한·범위·조건이 한 곳에서 정해진다."""
    scope = permit(db, admin, AU.MBR_R, now)
    query = _in_scope(select(TB_MBR).where(TB_MBR.c.OPER_BNDL_SN == admin.bundle_sn), scope)
    if q:
        needle = q.strip()
        query = query.where(
            or_(
                TB_MBR.c.LGN_ID.contains(needle, autoescape=True),
                TB_MBR.c.MBR_NM.contains(needle, autoescape=True),
            )
        )
    if status is not None:
        query = query.where(TB_MBR.c.MBR_STTS_CD == STATUS_CODE[status])
    return query.order_by(TB_MBR.c.MBR_JOIN_DT.desc(), TB_MBR.c.MBR_SN.desc())


def list_members(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    page: int,
    size: int,
    q: str | None,
    status: MemberStatus | None,
) -> AdminMemberPage:
    query = _filtered(db, admin, now, q=q, status=status)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AdminMemberPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _member(
    db: Session, admin: Admin, now: datetime, member_id: str, *, lock: bool = False
) -> tuple[Any, Scope]:
    """권한이 없으면 403, 없거나 범위 밖이면 같은 404다. 쓰기는 회원 행을 잠가 같은 회원의 요청을 한 줄로 세운다."""
    scope = permit(db, admin, AU.MBR_R, now)
    query = select(TB_MBR).where(TB_MBR.c.OPER_BNDL_SN == admin.bundle_sn, TB_MBR.c.MBR_SN == int(member_id))
    row = db.execute(query.with_for_update() if lock else query).first()
    if row is None or not scope.covers(None if row.DONG_SN is None else int(row.DONG_SN)):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row, scope


# --- 검토 기록(작업이력, 개정 요청 R12) ---------------------------------------------------------


def _reviews(db: Session, bundle_sn: int, member_sn: int) -> list[MemberReview]:
    rows = db.execute(
        select(TB_JOB_HSTRY, TB_MNGR.c.MNGR_NM)
        .select_from(TB_JOB_HSTRY.outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN))
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(member_sn),
            TB_JOB_HSTRY.c.JOB_CD.in_((REVIEW_JOB, CLOSE_JOB)),
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN)
    ).all()
    closes: dict[str, Any] = {}
    for r in rows:
        if r.JOB_CD == CLOSE_JOB and (m := CLOSE_TEXT.match(str(r.CHG_CN))):
            closes[m.group(1)] = (m.group(2), r.REG_DT)
    items: list[MemberReview] = []
    for r in rows:
        if r.JOB_CD != REVIEW_JOB:
            continue
        head = KIND_TEXT.match(IDEM_MARK.sub("", str(r.CHG_CN)))
        assert head is not None  # 이 서비스가 쓴 행만 이 작업 코드를 쓴다
        closed = closes.get(str(int(r.JOB_HSTRY_SN)))
        items.append(
            MemberReview(
                review_id=str(int(r.JOB_HSTRY_SN)),
                kind=MemberReviewKind(head.group(1)),
                state=MemberReviewState.CLOSED if closed else MemberReviewState.OPEN,
                reason=head.group(2),
                recorded_by=str(r.MNGR_NM or ""),
                recorded_at=utc(r.REG_DT),
                closed_note=closed[0] if closed else None,
                closed_at=utc(closed[1]) if closed else None,
            )
        )
    return items[::-1]  # 최근 기록이 먼저다


def _review_mark(idem_key: str, body: MemberReviewCreate) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"{body.kind.value}:{body.reason}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


# --- 조회 -------------------------------------------------------------------------------------


def _detail(db: Session, admin: Admin, now: datetime, row: Any, scope: Scope) -> AdminMember:
    sn = int(row.MBR_SN)
    mine = scoped(applications._base(admin.bundle_sn).where(TB_ATNLC_APLY.c.MBR_SN == sn), scope)
    shown = db.execute(
        mine.order_by(TB_ATNLC_APLY.c.APLY_DT.desc(), TB_ATNLC_APLY.c.ATNLC_APLY_SN.desc()).limit(
            APPLICATION_LIMIT
        )
    ).all()
    count = int(db.execute(select(func.count()).select_from(mine.order_by(None).subquery())).scalar_one())
    paid = db.execute(
        scoped(
            select(func.coalesce(func.sum(TB_STLM.c.STLM_AMT), 0))
            .select_from(
                TB_STLM.join(
                    TB_ATNLC_APLY,
                    (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN)
                    & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN),
                ).join(
                    TB_CORS,
                    (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
                    & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
                )
            )
            .where(
                TB_STLM.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_ATNLC_APLY.c.MBR_SN == sn,
                TB_STLM.c.STLM_STTS_CD == "PS.PAID",
            ),
            scope,
        )
    ).scalar_one()
    summaries = applications._summaries(db, admin, list(shown), now)
    base = _summary(row)
    return AdminMember(
        **base.model_dump(),
        phone_masked=mask_phone(row.MBL_TELNO),
        email_masked=mask_email(row.EML_ADDR),
        application_count=count,
        paid_total=int(paid),
        applications=[
            MemberApplication(
                application_no=s.application_no,
                course_name=s.course_name,
                display_state=s.display_state,
                payment_status=s.payment_status,
            )
            for s in summaries
        ],
        reviews=_reviews(db, admin.bundle_sn, sn),
        can_review=base.status is not MemberStatus.WITHDRAWN,
    )


def get_member(db: Session, admin: Admin, *, now: datetime, member_id: str) -> AdminMember:
    row, scope = _member(db, admin, now, member_id)
    return _detail(db, admin, now, row, scope)


def _audit(
    db: Session, admin: Admin, job: str, member_sn: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_MBR",
        key=member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def reveal_contact(
    db: Session, admin: Admin, *, now: datetime, request_id: str, member_id: str, body: RevealRequest
) -> MemberContact:
    """사유를 적어야 원문을 주고 열람할 때마다 누가·누구의·왜를 기록한다. 연락처 값은 기록하지 않는다."""
    row, _ = _member(db, admin, now, member_id)
    _audit(db, admin, "MBR_REVEAL", int(row.MBR_SN), request_id, now, f"연락처 열람 사유: {body.reason}")
    return MemberContact(phone=str(row.MBL_TELNO or ""), email=str(row.EML_ADDR or ""))


def _closed_to_withdrawn(row: Any) -> None:
    if row.MBR_STTS_CD == "MS.WITHDRAW":
        raise ApiError(ErrorCode.CONFLICT_STATE, "탈퇴한 회원에는 기록할 수 없습니다.")


def create_review(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    member_id: str,
    body: MemberReviewCreate,
    idem_key: str,
) -> MemberReview:
    """검토 사유만 기록하고 회원 상태는 바꾸지 않는다. 같은 종류가 검토 중이면 새로 남기지 않는다."""
    row, _ = _member(db, admin, now, member_id, lock=True)
    sn = int(row.MBR_SN)
    mark = _review_mark(idem_key, body)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.JOB_HSTRY_SN, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(sn),
            TB_JOB_HSTRY.c.JOB_CD == REVIEW_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:  # 같은 키의 재전송은 처음 결과를 준다. 내용이 다르면 409다
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return next(
            r for r in _reviews(db, admin.bundle_sn, sn) if r.review_id == str(int(prior.JOB_HSTRY_SN))
        )
    _closed_to_withdrawn(row)
    if any(
        r.kind is body.kind and r.state is MemberReviewState.OPEN for r in _reviews(db, admin.bundle_sn, sn)
    ):
        raise ApiError(ErrorCode.CONFLICT_STATE, "같은 종류의 검토가 이미 진행 중입니다.")
    record_job(
        db,
        actor="AK.ADMIN",
        job=REVIEW_JOB,
        table="TB_MBR",
        key=sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"[{body.kind.value}] {body.reason} {mark}",
    )
    made = db.execute(
        select(TB_JOB_HSTRY.c.JOB_HSTRY_SN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(sn),
            TB_JOB_HSTRY.c.JOB_CD == REVIEW_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).scalar_one()
    return next(r for r in _reviews(db, admin.bundle_sn, sn) if r.review_id == str(int(made)))


def close_review(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    member_id: str,
    review_id: str,
    body: MemberReviewClose,
) -> MemberReview:
    row, _ = _member(db, admin, now, member_id, lock=True)
    sn = int(row.MBR_SN)
    found = next((r for r in _reviews(db, admin.bundle_sn, sn) if r.review_id == review_id), None)
    if found is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if found.state is MemberReviewState.CLOSED:
        raise ApiError(ErrorCode.CONFLICT_STATE, "이미 처리 완료된 검토입니다.")
    record_job(
        db,
        actor="AK.ADMIN",
        job=CLOSE_JOB,
        table="TB_MBR",
        key=sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"[review {review_id}] {body.note}",
    )
    return next(r for r in _reviews(db, admin.bundle_sn, sn) if r.review_id == review_id)


# --- 거주지 확인 기록(개정 요청 R13) ------------------------------------------------------------


def record_residence(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    member_id: str,
    body: ResidenceRecord,
) -> AdminMember:
    """확인 결과를 회원 행과 작업이력에 남긴다. 확인 완료는 조리읍 거주(RA.JORI)로 본다(사용자 확정 2026-11-12)."""
    row, scope = _member(db, admin, now, member_id, lock=True)
    _closed_to_withdrawn(row)
    verified = body.result is ResidenceStatus.VERIFIED
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == row.MBR_SN)
        .values(
            HAB_IDNTY_STTS_CD="RV.OK" if verified else "RV.NONE",
            HAB_RGN_CD="RA.JORI" if verified else "RA.UNKNOWN",
            HAB_IDNTY_DT=now if verified else None,
            HAB_IDNTY_MNS_CD="RM.MANUAL" if verified else None,
            HAB_IDNTY_MNGR_SN=admin.admin_sn if verified else None,
            HAB_IDNTY_BSS_ID=request_id if verified else None,
            MDFCN_DT=now,
            RCRD_VER=TB_MBR.c.RCRD_VER + 1,
        )
    )
    _audit(
        db,
        admin,
        "MBR_RESIDENCE",
        int(row.MBR_SN),
        request_id,
        now,
        f"거주지 {body.result.value}: {body.note}",
    )
    fresh = db.execute(select(TB_MBR).where(TB_MBR.c.MBR_SN == row.MBR_SN)).one()
    return _detail(db, admin, now, fresh, scope)
