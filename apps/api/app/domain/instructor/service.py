# 강사 모집공고 조회와 회원의 강사 지원(작성·수정·내 지원내역). 공고는 게시글에 이어진 모집 정보이고 지원서는 회원의 이름·휴대전화를 쓴다(FN-019, FN-027, ADR-065)
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.idempotent import find_prior
from app.db.tables import (
    TB_BBS,
    TB_CORS,
    TB_CORS_CLSF,
    TB_INSTR,
    TB_INSTR_APLY,
    TB_INSTR_RCRT,
    TB_MBR,
    TB_PST,
)
from app.db.versioned import update_versioned
from app.domain.board.sanitize import plain_text
from app.domain.instructor.schemas import (
    InstructorApplication,
    InstructorApplicationPage,
    InstructorApplyWrite,
    InstructorDetail,
    InstructorPage,
    InstructorSummary,
    RecruitmentDetail,
    RecruitmentPage,
    RecruitmentSummary,
)
from app.domain.instructor.types import InstructorApplyStatus, RecruitmentStatus

STATUS = {  # 스키마의 심사 상태는 대기·승인·반려 세 가지뿐이다(개정 요청 R37)
    "IA.WAIT": InstructorApplyStatus.REVIEWING,
    "IA.APPROVE": InstructorApplyStatus.SELECTED,
    "IA.REJECT": InstructorApplyStatus.REJECTED,
}
EDITABLE = ("IA.WAIT",)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


# --- 공개 강사 ----------------------------------------------------------------------------------

VISIBLE_COURSES = ("CS.OPEN", "CS.RUN", "CS.CLOSE")  # 공개 강좌 목록과 같은 기준


def _public_instructors(bundle_sn: int) -> Select[Any]:
    """승인되고 공개로 정한 강사. 이름은 회원정보의 이름이며 심사 정보·증빙은 어디에도 없다(FN-018)."""
    return (
        select(TB_INSTR.c.INSTR_SN, TB_INSTR.c.CRR_CN, TB_INSTR.c.QLFC_CN, TB_MBR.c.MBR_NM)
        .select_from(TB_INSTR)
        .join(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_INSTR.c.OPER_BNDL_SN) & (TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN),
        )
        .where(
            TB_INSTR.c.OPER_BNDL_SN == bundle_sn,
            TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE",
            TB_INSTR.c.RLS_YN == "Y",
        )
    )


def _teaching(
    db: Session, bundle_sn: int, instructor_sns: list[int]
) -> dict[int, tuple[list[str], str | None]]:
    """강사별 공개 강좌 이름(중복 없이 가나다순)과 분야. 분야는 가장 최근 강좌의 분류 이름이다."""
    if not instructor_sns:
        return {}
    rows = db.execute(
        select(TB_CORS.c.INSTR_SN, TB_CORS.c.CORS_NM, TB_CORS_CLSF.c.CORS_CLSF_NM)
        .select_from(TB_CORS)
        .outerjoin(
            TB_CORS_CLSF,
            (TB_CORS_CLSF.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN)
            & (TB_CORS_CLSF.c.CORS_CLSF_SN == TB_CORS.c.CORS_CLSF_SN)
            & (TB_CORS_CLSF.c.DEL_YN == "N"),
        )
        .where(
            TB_CORS.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS.c.INSTR_SN.in_(instructor_sns),
            TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_COURSES),
        )
        .order_by(TB_CORS.c.CORS_SN.desc())
    ).all()
    names: dict[int, set[str]] = {}
    field: dict[int, str] = {}
    for row in rows:
        sn = int(row.INSTR_SN)
        names.setdefault(sn, set()).add(str(row.CORS_NM))
        if sn not in field and row.CORS_CLSF_NM is not None:
            field[sn] = str(row.CORS_CLSF_NM)
    return {sn: (sorted(names.get(sn, set())), field.get(sn)) for sn in instructor_sns}


def list_instructors(
    db: Session, bundle_sn: int, now: datetime, *, q: str | None, page: int, size: int
) -> InstructorPage:
    query = _public_instructors(bundle_sn)
    if q and q.strip():
        needle = q.strip()
        taught = (
            select(TB_CORS.c.CORS_SN)
            .where(
                TB_CORS.c.OPER_BNDL_SN == TB_INSTR.c.OPER_BNDL_SN,
                TB_CORS.c.INSTR_SN == TB_INSTR.c.INSTR_SN,
                TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_COURSES),
                TB_CORS.c.CORS_NM.contains(needle, autoescape=True),
            )
            .exists()
        )
        query = query.where(or_(TB_MBR.c.MBR_NM.contains(needle, autoescape=True), taught))
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(
        query.order_by(TB_MBR.c.MBR_NM, TB_INSTR.c.INSTR_SN).limit(size).offset((page - 1) * size)
    ).all()
    teaching = _teaching(db, bundle_sn, [int(r.INSTR_SN) for r in rows])
    return InstructorPage(
        items=[
            InstructorSummary(
                instructor_id=str(int(r.INSTR_SN)),
                name=str(r.MBR_NM),
                category_name=teaching[int(r.INSTR_SN)][1],
                course_names=teaching[int(r.INSTR_SN)][0],
            )
            for r in rows
        ],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get_instructor(db: Session, bundle_sn: int, instructor_id: str) -> InstructorDetail:
    row = db.execute(_public_instructors(bundle_sn).where(TB_INSTR.c.INSTR_SN == int(instructor_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    courses, field = _teaching(db, bundle_sn, [int(row.INSTR_SN)])[int(row.INSTR_SN)]
    career = "\n".join(str(v).strip() for v in (row.CRR_CN, row.QLFC_CN) if v is not None and str(v).strip())
    return InstructorDetail(
        instructor_id=str(int(row.INSTR_SN)),
        name=str(row.MBR_NM),
        category_name=field,
        course_names=courses,
        career=career or None,
    )


# --- 모집공고 -----------------------------------------------------------------------------------


def _recruitment_query(bundle_sn: int, now: datetime) -> Select[Any]:
    """게시된 공고글에 이어진 모집 정보. 기간이 비어 있는 공고는 공개하지 않는다."""
    published = func.coalesce(TB_PST.c.PSTG_BGNG_DT, TB_PST.c.REG_DT)
    return (
        select(TB_INSTR_RCRT, TB_PST.c.PST_TTL, TB_PST.c.PST_CN, published.label("PUB_DT"))
        .select_from(TB_INSTR_RCRT)
        .join(
            TB_PST,
            (TB_PST.c.OPER_BNDL_SN == TB_INSTR_RCRT.c.OPER_BNDL_SN)
            & (TB_PST.c.PST_SN == TB_INSTR_RCRT.c.PST_SN),
        )
        .join(TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN))
        .where(
            TB_INSTR_RCRT.c.OPER_BNDL_SN == bundle_sn,
            TB_INSTR_RCRT.c.RCRT_BGNG_DT.is_not(None),
            TB_INSTR_RCRT.c.RCRT_END_DT.is_not(None),
            TB_BBS.c.USE_YN == "Y",
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.PRVT_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),
            (TB_PST.c.PSTG_BGNG_DT.is_(None)) | (TB_PST.c.PSTG_BGNG_DT <= now),
            (TB_PST.c.PSTG_END_DT.is_(None)) | (TB_PST.c.PSTG_END_DT > now),
        )
    )


def _recruitment_status(row: Any, now: datetime) -> RecruitmentStatus:
    if now < row.RCRT_BGNG_DT:
        return RecruitmentStatus.UPCOMING
    return RecruitmentStatus.OPEN if now <= row.RCRT_END_DT else RecruitmentStatus.CLOSED


def _headcount(row: Any) -> int | None:
    return None if row.RCRT_NOPE is None else int(row.RCRT_NOPE)


def list_recruitments(db: Session, bundle_sn: int, now: datetime, *, page: int, size: int) -> RecruitmentPage:
    query = _recruitment_query(bundle_sn, now)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(
        query.order_by(
            func.coalesce(TB_PST.c.PSTG_BGNG_DT, TB_PST.c.REG_DT).desc(), TB_INSTR_RCRT.c.INSTR_RCRT_SN.desc()
        )
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return RecruitmentPage(
        items=[
            RecruitmentSummary(
                recruitment_id=str(int(r.INSTR_RCRT_SN)),
                title=str(r.PST_TTL),
                status=_recruitment_status(r, now),
                period_start=kst_today(r.RCRT_BGNG_DT),
                period_end=kst_today(r.RCRT_END_DT),
                headcount=_headcount(r),
            )
            for r in rows
        ],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _applied(db: Session, bundle_sn: int, member_sn: int, recruitment_sn: int) -> bool:
    return (
        db.execute(
            select(TB_INSTR_APLY.c.INSTR_APLY_SN).where(
                TB_INSTR_APLY.c.OPER_BNDL_SN == bundle_sn,
                TB_INSTR_APLY.c.MBR_SN == member_sn,
                TB_INSTR_APLY.c.INSTR_RCRT_SN == recruitment_sn,
            )
        ).first()
        is not None
    )


def get_recruitment(
    db: Session, bundle_sn: int, now: datetime, recruitment_id: str, member_sn: int | None
) -> RecruitmentDetail:
    row = db.execute(
        _recruitment_query(bundle_sn, now).where(TB_INSTR_RCRT.c.INSTR_RCRT_SN == int(recruitment_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    status = _recruitment_status(row, now)
    applied = member_sn is not None and _applied(db, bundle_sn, member_sn, int(row.INSTR_RCRT_SN))
    guide = plain_text(str(row.PST_CN))
    return RecruitmentDetail(
        recruitment_id=str(int(row.INSTR_RCRT_SN)),
        title=str(row.PST_TTL),
        status=status,
        announced_on=kst_today(row.PUB_DT),
        period_start=kst_today(row.RCRT_BGNG_DT),
        period_end=kst_today(row.RCRT_END_DT),
        headcount=_headcount(row),
        field=None,
        guide=guide or None,
        can_apply=status is RecruitmentStatus.OPEN and not applied,
    )


# --- 내 지원 ------------------------------------------------------------------------------------


def _mine_query(bundle_sn: int, member_sn: int) -> Select[Any]:
    return (
        select(TB_INSTR_APLY, TB_PST.c.PST_TTL)
        .select_from(TB_INSTR_APLY)
        .join(
            TB_INSTR_RCRT,
            (TB_INSTR_RCRT.c.OPER_BNDL_SN == TB_INSTR_APLY.c.OPER_BNDL_SN)
            & (TB_INSTR_RCRT.c.INSTR_RCRT_SN == TB_INSTR_APLY.c.INSTR_RCRT_SN),
        )
        .join(
            TB_PST,
            (TB_PST.c.OPER_BNDL_SN == TB_INSTR_RCRT.c.OPER_BNDL_SN)
            & (TB_PST.c.PST_SN == TB_INSTR_RCRT.c.PST_SN),
        )
        .where(TB_INSTR_APLY.c.OPER_BNDL_SN == bundle_sn, TB_INSTR_APLY.c.MBR_SN == member_sn)
    )


def _application(row: Any) -> InstructorApplication:
    return InstructorApplication(
        application_id=str(int(row.INSTR_APLY_SN)),
        recruitment_id=str(int(row.INSTR_RCRT_SN)),
        recruitment_title=str(row.PST_TTL),
        desired_course=str(row.HOPE_CORS_NM),
        category_name="" if row.HOPE_FLD_NM is None else str(row.HOPE_FLD_NM),
        career="" if row.CRR_CN is None else str(row.CRR_CN),
        status=STATUS[str(row.SRNG_STTS_CD)],
        applied_at=utc(row.SBMSN_DT),
        can_edit=str(row.SRNG_STTS_CD) in EDITABLE,
    )


def list_mine(
    db: Session, bundle_sn: int, member_sn: int, now: datetime, *, page: int, size: int
) -> InstructorApplicationPage:
    query = _mine_query(bundle_sn, member_sn)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(
        query.order_by(TB_INSTR_APLY.c.SBMSN_DT.desc(), TB_INSTR_APLY.c.INSTR_APLY_SN.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return InstructorApplicationPage(
        items=[_application(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _mine(db: Session, bundle_sn: int, member_sn: int, application_id: str) -> Any:
    row = db.execute(
        _mine_query(bundle_sn, member_sn).where(TB_INSTR_APLY.c.INSTR_APLY_SN == int(application_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_mine(db: Session, bundle_sn: int, member_sn: int, application_id: str) -> InstructorApplication:
    return _application(_mine(db, bundle_sn, member_sn, application_id))


def _lock_member(db: Session, bundle_sn: int, member_sn: int) -> Any:
    return db.execute(
        select(TB_MBR.c.MBL_TELNO_ENCPT_VL)
        .where(TB_MBR.c.OPER_BNDL_SN == bundle_sn, TB_MBR.c.MBR_SN == member_sn)
        .with_for_update()
    ).one()


def _category(db: Session, bundle_sn: int, name: str) -> str:
    """사용 중인 강좌 분류의 이름만 받는다. 저장은 분류의 표시 이름으로 한다."""
    found = db.execute(
        select(TB_CORS_CLSF.c.CORS_CLSF_NM).where(
            TB_CORS_CLSF.c.OPER_BNDL_SN == bundle_sn,
            and_(TB_CORS_CLSF.c.USE_YN == "Y", TB_CORS_CLSF.c.DEL_YN == "N"),
            TB_CORS_CLSF.c.CORS_CLSF_NM == name.strip(),
        )
    ).first()
    if found is None:
        raise _fail("categoryName", "희망 분야를 확인해 주세요.")
    return str(found.CORS_CLSF_NM)


def _texts(body: InstructorApplyWrite) -> tuple[str, str]:
    course, career = body.desired_course.strip(), body.career.strip()
    if not course:
        raise _fail("desiredCourse", "희망 강좌명을 입력해 주세요.")
    if not career:
        raise _fail("career", "경력 및 강의소개를 입력해 주세요.")
    return course, career


def create_mine(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    member_sn: int,
    body: InstructorApplyWrite,
    idem_key: str,
    now: datetime,
    request_id: str,
) -> InstructorApplication:
    """회원 행을 잠근 뒤 같은 키의 이전 지원을 먼저 찾고, 없으면 공고·분류·중복을 검사해 접수한다."""
    member = _lock_member(db, bundle_sn, member_sn)
    course, career = _texts(body)
    key = f"m{member_sn}-{hashlib.sha256(idem_key.encode()).hexdigest()[:40]}"
    prior = find_prior(
        db,
        select(TB_INSTR_APLY),
        TB_INSTR_APLY,
        bundle_sn,
        key,
        lambda p: (
            int(p.INSTR_RCRT_SN) == int(body.recruitment_id)
            and p.HOPE_CORS_NM == course
            and p.CRR_CN == career
            and str(p.HOPE_FLD_NM).casefold() == body.category_name.strip().casefold()
        ),
    )
    if prior is not None:
        return get_mine(db, bundle_sn, member_sn, str(int(prior.INSTR_APLY_SN)))
    recruitment = db.execute(
        _recruitment_query(bundle_sn, now).where(TB_INSTR_RCRT.c.INSTR_RCRT_SN == int(body.recruitment_id))
    ).first()
    if recruitment is None:
        raise _fail("recruitmentId", "모집공고를 찾을 수 없습니다.")
    if _recruitment_status(recruitment, now) is not RecruitmentStatus.OPEN:
        raise _fail("recruitmentId", "모집중인 공고만 지원할 수 있습니다.")
    if _applied(db, bundle_sn, member_sn, int(body.recruitment_id)):
        raise _fail("recruitmentId", "이미 지원한 공고입니다.")
    category = _category(db, bundle_sn, body.category_name)
    if not member.MBL_TELNO_ENCPT_VL:
        raise ApiError(
            ErrorCode.RULE_REJECTED, "회원정보에 휴대전화가 없어 지원할 수 없습니다. 먼저 등록해 주세요."
        )
    profile = db.execute(select(TB_MBR.c.MBR_NM).where(TB_MBR.c.MBR_SN == member_sn)).one()
    created = int(
        db.execute(
            TB_INSTR_APLY.insert()
            .values(
                OPER_BNDL_SN=bundle_sn,
                INSTR_RCRT_SN=int(body.recruitment_id),
                RCPT_CHNL_CD="IC.ONLINE",
                MBR_SN=member_sn,
                APLCT_NM=str(profile.MBR_NM),
                TELNO_ENCPT_VL=member.MBL_TELNO_ENCPT_VL,  # 같은 키·결합 데이터의 암호문을 그대로 옮긴다
                HOPE_CORS_NM=course,
                HOPE_FLD_NM=category,
                CRR_CN=career,
                RLS_HOPE_YN="N",
                SBMSN_DT=now,
                SRNG_STTS_CD="IA.WAIT",
                IDEM_KEY=key,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_INSTR_APLY.c.INSTR_APLY_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="INSTR_APLY_CREATE",
        table="TB_INSTR_APLY",
        key=created,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="ONLINE 접수",
    )
    return get_mine(db, bundle_sn, member_sn, str(created))


def update_mine(
    db: Session,
    *,
    bundle_sn: int,
    member_sn: int,
    application_id: str,
    body: InstructorApplyWrite,
    now: datetime,
    request_id: str,
) -> InstructorApplication:
    """서류 검토중인 내 지원서만 고친다. 회원 행 → 지원서 행 순서로 잠그고 잠근 뒤 상태를 다시 읽는다."""
    _mine(db, bundle_sn, member_sn, application_id)
    _lock_member(db, bundle_sn, member_sn)
    db.execute(
        select(TB_INSTR_APLY.c.INSTR_APLY_SN)
        .where(TB_INSTR_APLY.c.INSTR_APLY_SN == int(application_id))
        .with_for_update()
    ).one()
    row = _mine(db, bundle_sn, member_sn, application_id)
    if str(row.SRNG_STTS_CD) not in EDITABLE:
        raise _fail("status", "서류 검토중인 지원서만 고칠 수 있습니다.")
    if int(row.INSTR_RCRT_SN) != int(body.recruitment_id):
        raise _fail("recruitmentId", "지원한 공고는 바꿀 수 없습니다.")
    course, career = _texts(body)
    category = _category(db, bundle_sn, body.category_name)
    update_versioned(
        db,
        TB_INSTR_APLY,
        {"OPER_BNDL_SN": bundle_sn, "INSTR_APLY_SN": int(application_id)},
        int(row.RCRD_VER),
        {"HOPE_CORS_NM": course, "HOPE_FLD_NM": category, "CRR_CN": career},
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="INSTR_APLY_UPDATE",
        table="TB_INSTR_APLY",
        key=int(application_id),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="지원서 수정",
    )
    return get_mine(db, bundle_sn, member_sn, application_id)
