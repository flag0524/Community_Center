# 관리자 교육기수·강좌 관리: 기수 등록·수정, 강좌 등록·수정·공개·접수마감·폐강(FN-047·048·057, ADR-047)
import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit, permit_any, scope_for
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_CORS_CLSF,
    TB_CORS_SCHDL,
    TB_DONG,
    TB_EDU_CYCL,
    TB_FCLT,
    TB_INSTR,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_OPER_BNDL,
    TB_RFND,
    TB_STLM,
)
from app.db.versioned import update_versioned
from app.domain.admin.csv_export import audit_export, build_csv, fetch_all
from app.domain.admin.education_schemas import (
    AdminCourse,
    AdminCoursePage,
    AdminCourseSummary,
    CancelPreview,
    CourseActions,
    CourseOptions,
    CourseUpdate,
    CourseWrite,
    Cycle,
    CyclePage,
    CycleUpdate,
    CycleWrite,
    Option,
)
from app.domain.admin.education_types import CourseAdminStatus, CycleStatus
from app.domain.admin.refund_service import kst_start, scoped
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.seats import cancel_ready_payments, count_by_status, lock_course, set_status
from app.domain.application.service import ACTIVE, SEAT_STATUSES
from app.domain.course.service import _education_state, reception_state, ymd
from app.domain.payment.service import lock_payment
from app.domain.refund.service import reserved_amount

DUPLICATE_ENTRY = 1062
READ = (AU.CORS_R, AU.CORS_W)
OPTION_READERS = (AU.CORS_R, AU.CORS_W, AU.CONF_W, AU.ATND_R, AU.APLY_R, AU.STAT_R, AU.SMS_SEND)
STATUS = {
    "CS.DRAFT": CourseAdminStatus.DRAFT,
    "CS.OPEN": CourseAdminStatus.PUBLISHED,
    "CS.RUN": CourseAdminStatus.PUBLISHED,
    "CS.CLOSE": CourseAdminStatus.RECEPTION_CLOSED,
    "CS.END": CourseAdminStatus.RECEPTION_CLOSED,
    "CS.CANCEL": CourseAdminStatus.CANCELLED,
}
STATUS_CODES = {
    CourseAdminStatus.DRAFT: ("CS.DRAFT",),
    CourseAdminStatus.PUBLISHED: ("CS.OPEN", "CS.RUN"),
    CourseAdminStatus.RECEPTION_CLOSED: ("CS.CLOSE", "CS.END"),
    CourseAdminStatus.CANCELLED: ("CS.CANCEL",),
}
EDITABLE = ("CS.DRAFT", "CS.OPEN", "CS.RUN", "CS.CLOSE")
CANCELLABLE = ("CS.OPEN", "CS.RUN", "CS.CLOSE")
DEFAULT_CLASS_CODE = (
    "CC.ETC"  # 센터별 분류는 CORS_CLSF_SN이 정한다. 코드 컬럼은 스키마가 보존용으로 둔 값이다
)
PAYMENT_WINDOW_MINUTES = 10
COURSE_CANCEL_REASON = "폐강"
NONE_ID = "0"  # 동·분류·강사가 비어 있는 기존 강좌를 계약의 필수 번호 필드에 담을 때 쓴다


def _naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _fingerprint(body: BaseModel) -> str:
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]


def _idem_mark(idem_key: str, body: BaseModel) -> str:
    """등록 요청의 멱등 표식. 기수·강좌 테이블에 멱등키 컬럼이 없어 작업이력 메모에 해시로 남긴다(개정 요청 R28)."""
    return f"[idem {hashlib.sha256(idem_key.encode()).hexdigest()[:16]}:{_fingerprint(body)}]"


def _replayed(db: Session, bundle_sn: int, job: str, idem_key: str, body: BaseModel) -> int | None:
    """같은 키로 이미 등록했으면 그 대상 번호를 준다. 내용이 다르면 409다. 호출 전에 직렬화용 잠금을 잡는다."""
    mark = _idem_mark(idem_key, body)
    prefix = mark.split(":")[0]
    found = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == job,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix + ":", autoescape=True),
        )
    ).first()
    if found is None:
        return None
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return int(found.TRGT_KEY_VL)


def _audit(
    db: Session, admin: Admin, job: str, table: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table=table,
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


# --- 교육기수 ---------------------------------------------------------------------------------


def _config_scope(db: Session, admin: Admin, now: datetime) -> None:
    """기수는 묶음 공통 설정이다. 동 범위 배정만으로는 다룰 수 없다(R28)."""
    if not permit(db, admin, AU.CONF_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _cycle_values(body: CycleWrite) -> dict[str, Any]:
    fields: dict[str, str] = {}
    if body.reception_end < body.reception_start:
        fields["receptionEnd"] = "모집 종료일은 시작일 이후여야 합니다."
    if body.education_end < body.education_start:
        fields["educationEnd"] = "교육 종료일은 시작일 이후여야 합니다."
    if fields:
        raise ApiError(ErrorCode.RULE_REJECTED, fields=fields)
    return {
        "EDU_YR": str(body.year),
        "EDU_CYCL": body.order,
        "EDU_CYCL_NM": body.name.strip(),
        "EDU_BGNG_YMD": _ymd(body.education_start),
        "EDU_END_YMD": _ymd(body.education_end),
        # 모집기간은 한국 날짜다. 종료일은 그날 끝까지라 다음 날 0시(미포함)로 저장한다
        "RCPT_BGNG_DT": kst_start(body.reception_start),
        "RCPT_END_DT": kst_start(body.reception_end + timedelta(days=1)),
        # 상태 컬럼이 없어 사용중만 Y로 둔다. 작성중·사용중지는 N이고 읽을 때 연결 강좌로 가른다(사용자 확정, R29)
        "USE_YN": "Y" if body.status is CycleStatus.ACTIVE else "N",
    }


def _cycle_query(bundle_sn: int) -> Select[Any]:
    courses = (
        select(func.count())
        .where(
            TB_CORS.c.OPER_BNDL_SN == TB_EDU_CYCL.c.OPER_BNDL_SN,
            TB_CORS.c.EDU_CYCL_SN == TB_EDU_CYCL.c.EDU_CYCL_SN,
        )
        .correlate(TB_EDU_CYCL)
        .scalar_subquery()
    )
    return select(TB_EDU_CYCL, courses.label("COURSES")).where(TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn)


def _cycle(row: Any) -> Cycle:
    count = int(row.COURSES)
    status = CycleStatus.ACTIVE if row.USE_YN == "Y" else CycleStatus.INACTIVE if count else CycleStatus.DRAFT
    return Cycle(
        cycle_id=str(int(row.EDU_CYCL_SN)),
        name=str(row.EDU_CYCL_NM),
        year=int(row.EDU_YR),
        order=int(row.EDU_CYCL),
        reception_start=kst_today(row.RCPT_BGNG_DT),
        reception_end=kst_today(row.RCPT_END_DT - timedelta(seconds=1)),
        education_start=ymd(str(row.EDU_BGNG_YMD)),
        education_end=ymd(str(row.EDU_END_YMD)),
        status=status,
        version=int(row.RCRD_VER),
        course_count=count,
    )


def _one_cycle(db: Session, bundle_sn: int, cycle_sn: int) -> Cycle:
    row = db.execute(_cycle_query(bundle_sn).where(TB_EDU_CYCL.c.EDU_CYCL_SN == cycle_sn)).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return _cycle(row)


def list_cycles(db: Session, admin: Admin, *, now: datetime, page: int, size: int) -> CyclePage:
    _config_scope(db, admin, now)
    total = int(
        db.execute(
            select(func.count()).select_from(TB_EDU_CYCL).where(TB_EDU_CYCL.c.OPER_BNDL_SN == admin.bundle_sn)
        ).scalar_one()
    )
    rows = db.execute(
        _cycle_query(admin.bundle_sn)
        .order_by(TB_EDU_CYCL.c.EDU_YR.desc(), TB_EDU_CYCL.c.EDU_CYCL.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return CyclePage(
        items=[_cycle(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get_cycle(db: Session, admin: Admin, *, now: datetime, cycle_id: str) -> Cycle:
    _config_scope(db, admin, now)
    return _one_cycle(db, admin.bundle_sn, int(cycle_id))


def _duplicate_cycle(error: IntegrityError) -> bool:
    return (
        error.orig is not None
        and error.orig.args[0] == DUPLICATE_ENTRY
        and "UQ_EDU_CYCL_02" in str(error.orig.args[1])
    )


def create_cycle(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: CycleWrite, idem_key: str
) -> Cycle:
    _config_scope(db, admin, now)
    values = _cycle_values(body)
    # 같은 묶음의 기수 등록을 한 줄로 세운다. 멱등 표식 조회와 삽입 사이에 다른 등록이 끼지 못한다
    db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN)
        .where(TB_OPER_BNDL.c.OPER_BNDL_SN == admin.bundle_sn)
        .with_for_update()
    ).one()
    replayed = _replayed(db, admin.bundle_sn, "CYCL_CREATE", idem_key, body)
    if replayed is not None:
        return _one_cycle(db, admin.bundle_sn, replayed)
    try:
        cycle_sn = int(
            db.execute(
                insert(TB_EDU_CYCL)
                .values(OPER_BNDL_SN=admin.bundle_sn, REG_DT=now, **values)
                .returning(TB_EDU_CYCL.c.EDU_CYCL_SN)
            ).scalar_one()
        )
    except IntegrityError as error:
        if _duplicate_cycle(error):
            raise ApiError(
                ErrorCode.RULE_REJECTED, fields={"order": "같은 연도·차수의 기수가 이미 있습니다."}
            ) from None
        raise
    _audit(
        db,
        admin,
        "CYCL_CREATE",
        "TB_EDU_CYCL",
        cycle_sn,
        request_id,
        now,
        f"기수 등록 {_idem_mark(idem_key, body)}",
    )
    return _one_cycle(db, admin.bundle_sn, cycle_sn)


def update_cycle(
    db: Session, admin: Admin, *, now: datetime, request_id: str, cycle_id: str, body: CycleUpdate
) -> Cycle:
    _config_scope(db, admin, now)
    values = _cycle_values(body)
    try:
        update_versioned(
            db,
            TB_EDU_CYCL,
            {"OPER_BNDL_SN": admin.bundle_sn, "EDU_CYCL_SN": int(cycle_id)},
            body.version,
            values,
        )
    except IntegrityError as error:
        if _duplicate_cycle(error):
            raise ApiError(
                ErrorCode.RULE_REJECTED, fields={"order": "같은 연도·차수의 기수가 이미 있습니다."}
            ) from None
        raise
    _audit(db, admin, "CYCL_UPDATE", "TB_EDU_CYCL", int(cycle_id), request_id, now, "기수 수정")
    return _one_cycle(db, admin.bundle_sn, int(cycle_id))


# --- 강좌 조회 --------------------------------------------------------------------------------


def _count(statuses: tuple[str, ...]) -> Any:
    return (
        select(func.count())
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
            TB_ATNLC_APLY.c.CORS_SN == TB_CORS.c.CORS_SN,
            TB_ATNLC_APLY.c.APLY_STTS_CD.in_(statuses),
        )
        .correlate(TB_CORS)
        .scalar_subquery()
    )


def _course_query(bundle_sn: int) -> Select[Any]:
    source = (
        TB_CORS.join(
            TB_EDU_CYCL,
            and_(
                TB_EDU_CYCL.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_EDU_CYCL.c.EDU_CYCL_SN == TB_CORS.c.EDU_CYCL_SN,
            ),
        )
        .outerjoin(
            TB_CORS_CLSF,
            and_(
                TB_CORS_CLSF.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_CORS_CLSF.c.CORS_CLSF_SN == TB_CORS.c.CORS_CLSF_SN,
            ),
        )
        .outerjoin(
            TB_INSTR,
            and_(
                TB_INSTR.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN, TB_INSTR.c.INSTR_SN == TB_CORS.c.INSTR_SN
            ),
        )
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN)
    )
    return (
        select(
            TB_CORS,
            TB_EDU_CYCL.c.EDU_CYCL_NM,
            TB_EDU_CYCL.c.EDU_BGNG_YMD.label("CYCLE_BEGIN"),
            TB_EDU_CYCL.c.EDU_END_YMD.label("CYCLE_END"),
            TB_CORS_CLSF.c.CORS_CLSF_NM,
            TB_INSTR.c.INSTR_STTS_CD,
            TB_MBR.c.MBR_NM.label("INSTRUCTOR_NM"),
            _count(SEAT_STATUSES).label("OCCUPIED"),
            _count(("ES.WAIT",)).label("WAITING"),
        )
        .select_from(source)
        .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn)
    )


def _summary(row: Any, now: datetime) -> dict[str, Any]:
    code = str(row.CORS_STTS_CD)
    return {
        "course_id": str(int(row.CORS_SN)),
        "name": str(row.CORS_NM),
        "reception_start": utc(row.RCPT_BGNG_DT),
        "reception_end": utc(row.RCPT_END_DT),
        "capacity": int(row.RCRT_NOPE),
        "occupied": int(row.OCCUPIED),
        "waiting": int(row.WAITING),
        "tuition": int(row.TTCHG),
        "status": STATUS[code],
        "reception_state": reception_state(code, row.RCPT_BGNG_DT, row.RCPT_END_DT, now),
    }


def _filtered_courses(
    db: Session,
    admin: Admin,
    now: datetime,
    *,
    q: str | None,
    cycle_id: str | None,
    class_id: str | None,
    dong_id: str | None,
    status: CourseAdminStatus | None,
) -> Any:
    """목록과 내보내기가 함께 쓰는 조회. 범위 밖 강좌는 조건과 무관하게 나오지 않는다(RQ-SER-NF-009)."""
    scope = permit_any(db, admin, READ, now)
    query = scoped(_course_query(admin.bundle_sn), scope)
    if q and q.strip():
        query = query.where(TB_CORS.c.CORS_NM.contains(q.strip(), autoescape=True))
    if cycle_id:
        query = query.where(TB_CORS.c.EDU_CYCL_SN == int(cycle_id))
    if class_id:
        query = query.where(TB_CORS.c.CORS_CLSF_SN == int(class_id))
    if dong_id:
        query = query.where(TB_CORS.c.DONG_SN == int(dong_id))
    if status is not None:
        query = query.where(TB_CORS.c.CORS_STTS_CD.in_(STATUS_CODES[status]))
    return query.order_by(TB_CORS.c.RCPT_BGNG_DT.desc(), TB_CORS.c.CORS_SN.desc())


def _course_summary(r: Any, now: datetime) -> AdminCourseSummary:
    return AdminCourseSummary(
        **_summary(r, now),
        cycle_name=str(r.EDU_CYCL_NM),
        class_name=None if r.CORS_CLSF_NM is None else str(r.CORS_CLSF_NM),
        instructor_name="" if r.INSTRUCTOR_NM is None else str(r.INSTRUCTOR_NM),
    )


def export_courses_csv(db: Session, admin: Admin, *, now: datetime, request_id: str, **filters: Any) -> bytes:
    """목록과 같은 조건·범위로 만든다. 범위 밖 강좌는 담지 않는다(RQ-SER-NF-009)."""
    rows = fetch_all(db, _filtered_courses(db, admin, now, **filters))
    items = [_course_summary(r, now) for r in rows]
    audit_export(db, admin, "TB_CORS", len(items), request_id, now, filters)
    return build_csv(
        [
            "강좌",
            "기수",
            "분류",
            "강사",
            "접수 시작",
            "접수 종료",
            "정원",
            "점유",
            "대기",
            "수강료",
            "상태",
            "접수 상태",
        ],
        [
            [
                i.name,
                i.cycle_name,
                i.class_name,
                i.instructor_name,
                i.reception_start,
                i.reception_end,
                i.capacity,
                i.occupied,
                i.waiting,
                i.tuition,
                i.status.value,
                i.reception_state.value,
            ]
            for i in items
        ],
    )


def export_cycles_csv(db: Session, admin: Admin, *, now: datetime, request_id: str) -> bytes:
    """교육기수 목록 전체. 기간과 접수기간은 한국 날짜로 담는다."""
    _config_scope(db, admin, now)
    rows = fetch_all(
        db,
        _cycle_query(admin.bundle_sn).order_by(TB_EDU_CYCL.c.EDU_YR.desc(), TB_EDU_CYCL.c.EDU_CYCL.desc()),
    )
    items = [_cycle(r) for r in rows]
    audit_export(db, admin, "TB_EDU_CYCL", len(items), request_id, now, {})
    return build_csv(
        ["기수", "연도", "차수", "교육 시작", "교육 종료", "접수 시작", "접수 종료", "상태", "강좌 수"],
        [
            [
                i.name,
                i.year,
                i.order,
                i.education_start,
                i.education_end,
                i.reception_start,
                i.reception_end,
                i.status.value,
                i.course_count,
            ]
            for i in items
        ],
    )


def list_courses(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    page: int,
    size: int,
    **filters: Any,
) -> AdminCoursePage:
    query = _filtered_courses(db, admin, now, **filters)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    items = [_course_summary(r, now) for r in rows]
    return AdminCoursePage(
        items=items, page=page, size=size, total=total, criteria=PageCriteria(basis_at=utc(now))
    )


def _dong(row: Any) -> int | None:
    return None if row.DONG_SN is None else int(row.DONG_SN)


def _visible(db: Session, admin: Admin, scope: Scope, course_id: str) -> Any:
    """범위 밖이거나 없는 강좌는 같은 404다."""
    row = db.execute(_course_query(admin.bundle_sn).where(TB_CORS.c.CORS_SN == int(course_id))).first()
    if row is None or not scope.covers(_dong(row)):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _detail(db: Session, admin: Admin, now: datetime, course_sn: int) -> AdminCourse:
    row = db.execute(_course_query(admin.bundle_sn).where(TB_CORS.c.CORS_SN == course_sn)).one()
    code = str(row.CORS_STTS_CD)
    summary = _summary(row, now)
    can_write = scope_for(db, admin, AU.CORS_W, now).covers(_dong(row))
    schedules = db.execute(
        select(func.count())
        .select_from(TB_CORS_SCHDL)
        .where(TB_CORS_SCHDL.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS_SCHDL.c.CORS_SN == course_sn)
    ).scalar_one()
    begin, end = ymd(str(row.EDU_BGNG_YMD)), ymd(str(row.EDU_END_YMD))

    def number(value: Any) -> str:
        return NONE_ID if value is None else str(int(value))

    return AdminCourse(
        **summary,
        cycle_id=str(int(row.EDU_CYCL_SN)),
        dong_id=number(row.DONG_SN),
        class_id=number(row.CORS_CLSF_SN),
        instructor_id=number(row.INSTR_SN),
        wait_capacity=int(row.WTNG_NOPE),
        outside_reception_start=None if row.OTSD_RGN_RCPT_BGNG_DT is None else utc(row.OTSD_RGN_RCPT_BGNG_DT),
        education_start=begin,
        education_end=end,
        description="" if row.LCTR_CN is None else str(row.LCTR_CN),
        education_state=_education_state(kst_today(now), begin, end),
        official_capacity=None,  # 공고 모집정원을 담을 컬럼이 없다(개정 요청 R29)
        schedule_count=int(schedules),
        version=int(row.RCRD_VER),
        actions=CourseActions(
            can_edit=can_write and code in EDITABLE,
            can_publish=can_write and code == "CS.DRAFT",
            can_close_reception=can_write
            and code == "CS.OPEN"
            and summary["reception_state"].value == "OPEN",
            can_cancel=can_write and code in CANCELLABLE,
        ),
    )


def get_course(db: Session, admin: Admin, *, now: datetime, course_id: str) -> AdminCourse:
    _visible(db, admin, permit_any(db, admin, READ, now), course_id)
    return _detail(db, admin, now, int(course_id))


def get_options(db: Session, admin: Admin, *, now: datetime) -> CourseOptions:
    """등록·수정 화면과 목록 조건의 선택지. 강좌는 이 담당자의 범위 안의 것만 담는다."""
    scope = permit_any(db, admin, OPTION_READERS, now)
    bundle = admin.bundle_sn

    def options(query: Select[Any]) -> list[Option]:
        return [Option(id=str(int(r[0])), name=str(r[1])) for r in db.execute(query).all()]

    parent = TB_FCLT.alias("parent")
    courses = select(TB_CORS.c.CORS_SN, TB_CORS.c.CORS_NM).where(TB_CORS.c.OPER_BNDL_SN == bundle)
    if not scope.whole:
        courses = courses.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    rooms = db.execute(
        select(TB_FCLT.c.FCLT_SN, TB_FCLT.c.FCLT_NM, parent.c.FCLT_NM)
        .outerjoin(parent, parent.c.FCLT_SN == TB_FCLT.c.UP_FCLT_SN)
        .where(TB_FCLT.c.OPER_BNDL_SN == bundle, TB_FCLT.c.FCLT_TYPE_CD == "FT.ROOM", TB_FCLT.c.USE_YN == "Y")
        .order_by(TB_FCLT.c.FCLT_SN)
    ).all()
    return CourseOptions(
        cycles=options(
            select(TB_EDU_CYCL.c.EDU_CYCL_SN, TB_EDU_CYCL.c.EDU_CYCL_NM)
            .where(TB_EDU_CYCL.c.OPER_BNDL_SN == bundle)
            .order_by(TB_EDU_CYCL.c.EDU_YR.desc(), TB_EDU_CYCL.c.EDU_CYCL.desc())
        ),
        dongs=options(
            select(TB_DONG.c.DONG_SN, TB_DONG.c.DONG_NM)
            .where(TB_DONG.c.OPER_BNDL_SN == bundle, TB_DONG.c.USE_YN == "Y")
            .order_by(TB_DONG.c.SORT_SEQ, TB_DONG.c.DONG_SN)
        ),
        classes=options(
            select(TB_CORS_CLSF.c.CORS_CLSF_SN, TB_CORS_CLSF.c.CORS_CLSF_NM)
            .where(
                TB_CORS_CLSF.c.OPER_BNDL_SN == bundle,
                TB_CORS_CLSF.c.USE_YN == "Y",
                TB_CORS_CLSF.c.DEL_YN == "N",
            )
            .order_by(TB_CORS_CLSF.c.SORT_SEQ, TB_CORS_CLSF.c.CORS_CLSF_SN)
        ),
        instructors=options(
            select(TB_INSTR.c.INSTR_SN, TB_MBR.c.MBR_NM)
            .join(TB_MBR, TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN)
            .where(TB_INSTR.c.OPER_BNDL_SN == bundle, TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE")
            .order_by(TB_MBR.c.MBR_NM, TB_INSTR.c.INSTR_SN)
        ),
        courses=options(courses.order_by(TB_CORS.c.CORS_SN.desc())),
        rooms=[
            Option(id=str(int(r[0])), name=f"{r[2]} {r[1]}" if r[2] is not None else str(r[1])) for r in rooms
        ],
    )


# --- 강좌 등록·수정 ---------------------------------------------------------------------------


def _approved_instructor(db: Session, bundle_sn: int, instructor_sn: int) -> bool:
    status = db.execute(
        select(TB_INSTR.c.INSTR_STTS_CD).where(
            TB_INSTR.c.OPER_BNDL_SN == bundle_sn, TB_INSTR.c.INSTR_SN == instructor_sn
        )
    ).scalar_one_or_none()
    return status == "IS.APPROVE"


def _course_values(db: Session, bundle_sn: int, body: CourseWrite, occupied: int) -> dict[str, Any]:
    """입력을 검사하고 저장할 값을 만든다. 틀린 항목은 필드별 사유로 한 번에 알린다(422)."""
    fields: dict[str, str] = {}
    cycle = db.execute(
        select(TB_EDU_CYCL.c.EDU_BGNG_YMD, TB_EDU_CYCL.c.EDU_END_YMD).where(
            TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn, TB_EDU_CYCL.c.EDU_CYCL_SN == int(body.cycle_id)
        )
    ).first()
    if cycle is None:
        fields["cycleId"] = "기수를 선택해 주세요."
    dong = db.execute(
        select(TB_DONG.c.DONG_SN).where(
            TB_DONG.c.OPER_BNDL_SN == bundle_sn,
            TB_DONG.c.DONG_SN == int(body.dong_id),
            TB_DONG.c.USE_YN == "Y",
        )
    ).first()
    if dong is None:
        fields["dongId"] = "운영 동을 선택해 주세요."
    category = db.execute(
        select(TB_CORS_CLSF.c.CORS_CLSF_SN).where(
            TB_CORS_CLSF.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_CLSF.c.CORS_CLSF_SN == int(body.class_id),
            TB_CORS_CLSF.c.USE_YN == "Y",
            TB_CORS_CLSF.c.DEL_YN == "N",
        )
    ).first()
    if category is None:
        fields["classId"] = "분류를 선택해 주세요."
    if not _approved_instructor(db, bundle_sn, int(body.instructor_id)):
        fields["instructorId"] = "승인·활동 강사만 선택할 수 있습니다."
    start, end = _naive(body.reception_start), _naive(body.reception_end)
    if end <= start:
        fields["receptionEnd"] = "접수 종료는 시작 이후여야 합니다."
    outside = None if body.outside_reception_start is None else _naive(body.outside_reception_start)
    if outside is not None and (outside < start or outside >= end):
        fields["outsideReceptionStart"] = "관외 접수 시작은 접수 시작 이상, 접수 종료 미만이어야 합니다."
    if body.education_end < body.education_start:
        fields["educationEnd"] = "교육 종료일은 시작일 이후여야 합니다."
    elif cycle is not None and (
        _ymd(body.education_start) < str(cycle.EDU_BGNG_YMD)
        or _ymd(body.education_end) > str(cycle.EDU_END_YMD)
    ):
        fields["educationStart"] = "기수 교육기간 안이어야 합니다."
    if body.capacity < occupied:
        fields["capacity"] = f"현재 점유 {occupied}명보다 작게 줄일 수 없습니다."
    if fields:
        raise ApiError(ErrorCode.RULE_REJECTED, fields=fields)
    return {
        "EDU_CYCL_SN": int(body.cycle_id),
        "DONG_SN": int(body.dong_id),
        "CORS_CLSF_SN": int(body.class_id),
        "INSTR_SN": int(body.instructor_id),
        "CORS_NM": body.name.strip(),
        "RCRT_NOPE": body.capacity,
        "WTNG_NOPE": body.wait_capacity,
        "TTCHG": body.tuition,
        "RCPT_BGNG_DT": start,
        "RCPT_END_DT": end,
        "OTSD_RGN_RCPT_BGNG_DT": outside,
        "EDU_BGNG_YMD": _ymd(body.education_start),
        "EDU_END_YMD": _ymd(body.education_end),
        "LCTR_CN": body.description or None,
    }


def create_course(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: CourseWrite, idem_key: str
) -> AdminCourse:
    scope = permit(db, admin, AU.CORS_W, now)
    if not scope.covers(int(body.dong_id)):  # 자기 범위 밖의 동에는 강좌를 만들 수 없다
        raise ApiError(ErrorCode.FORBIDDEN)
    # 같은 기수의 강좌 등록을 한 줄로 세워 멱등 표식 조회와 삽입 사이의 틈을 막는다
    db.execute(
        select(TB_EDU_CYCL.c.EDU_CYCL_SN)
        .where(TB_EDU_CYCL.c.OPER_BNDL_SN == admin.bundle_sn, TB_EDU_CYCL.c.EDU_CYCL_SN == int(body.cycle_id))
        .with_for_update()
    ).first()
    replayed = _replayed(db, admin.bundle_sn, "CORS_CREATE", idem_key, body)
    if replayed is not None:
        return _detail(db, admin, now, replayed)
    values = _course_values(db, admin.bundle_sn, body, 0)
    course_sn = int(
        db.execute(
            insert(TB_CORS)
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                CORS_STTS_CD="CS.DRAFT",
                CORS_CLSF_CD=DEFAULT_CLASS_CODE,
                STLM_WTNG_MINUTE=PAYMENT_WINDOW_MINUTES,
                REG_DT=now,
                **values,
            )
            .returning(TB_CORS.c.CORS_SN)
        ).scalar_one()
    )
    _audit(
        db,
        admin,
        "CORS_CREATE",
        "TB_CORS",
        course_sn,
        request_id,
        now,
        f"강좌 등록 {_idem_mark(idem_key, body)}",
    )
    return _detail(db, admin, now, course_sn)


def _locked(db: Session, admin: Admin, scope: Scope, course_id: str) -> Any:
    """범위를 확인하고 강좌 행을 잠근다. 정원·신청 상태를 함께 바꾸는 일은 모두 이 잠금 아래에서 한다."""
    _visible(db, admin, scope, course_id)
    return lock_course(db, admin.bundle_sn, int(course_id))


def update_course(
    db: Session, admin: Admin, *, now: datetime, request_id: str, course_id: str, body: CourseUpdate
) -> AdminCourse:
    scope = permit(db, admin, AU.CORS_W, now)
    course = _locked(db, admin, scope, course_id)
    if not scope.covers(int(body.dong_id)):  # 강좌를 자기 범위 밖의 동으로 옮길 수 없다
        raise ApiError(ErrorCode.FORBIDDEN)
    if course.CORS_STTS_CD not in EDITABLE:
        raise ApiError(ErrorCode.CONFLICT_STATE)
    if int(course.RCRD_VER) != body.version:
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    course_sn = int(course.CORS_SN)
    occupied = count_by_status(db, admin.bundle_sn, course_sn, SEAT_STATUSES)  # 잠금 아래에서 센다(ADR-028)
    values = _course_values(db, admin.bundle_sn, body, occupied)
    update_versioned(
        db, TB_CORS, {"OPER_BNDL_SN": admin.bundle_sn, "CORS_SN": course_sn}, body.version, values
    )
    _audit(db, admin, "CORS_UPDATE", "TB_CORS", course_sn, request_id, now, "강좌 수정")
    return _detail(db, admin, now, course_sn)


def _set_status(db: Session, course: Any, code: str, now: datetime) -> None:
    db.execute(
        update(TB_CORS)
        .where(TB_CORS.c.CORS_SN == course.CORS_SN)
        .values(CORS_STTS_CD=code, MDFCN_DT=now, RCRD_VER=TB_CORS.c.RCRD_VER + 1)
    )


def publish(db: Session, admin: Admin, *, now: datetime, request_id: str, course_id: str) -> AdminCourse:
    """공개 요청. 승인 강사, 일정 1건 이상, 기수 안의 교육기간, 아직 끝나지 않은 접수기간을 다시 검사한다(FN-048)."""
    course = _locked(db, admin, permit(db, admin, AU.CORS_W, now), course_id)
    if course.CORS_STTS_CD != "CS.DRAFT":
        raise ApiError(ErrorCode.CONFLICT_STATE)
    course_sn = int(course.CORS_SN)
    fields: dict[str, str] = {}
    if course.INSTR_SN is None or not _approved_instructor(db, admin.bundle_sn, int(course.INSTR_SN)):
        fields["instructorId"] = "승인·활동 강사가 배정되어야 공개할 수 있습니다."
    schedules = db.execute(
        select(func.count())
        .select_from(TB_CORS_SCHDL)
        .where(TB_CORS_SCHDL.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS_SCHDL.c.CORS_SN == course_sn)
    ).scalar_one()
    if int(schedules) < 1:
        fields["schedule"] = "일정이 1건 이상 있어야 공개할 수 있습니다."
    cycle = db.execute(
        select(TB_EDU_CYCL.c.EDU_BGNG_YMD, TB_EDU_CYCL.c.EDU_END_YMD).where(
            TB_EDU_CYCL.c.EDU_CYCL_SN == course.EDU_CYCL_SN
        )
    ).one()
    if str(course.EDU_BGNG_YMD) < str(cycle.EDU_BGNG_YMD) or str(course.EDU_END_YMD) > str(cycle.EDU_END_YMD):
        fields["educationStart"] = "기수 교육기간 안이어야 합니다."
    if course.RCPT_END_DT <= course.RCPT_BGNG_DT or course.RCPT_END_DT <= now:
        fields["receptionEnd"] = "접수 종료가 접수 시작과 현재 시각 이후여야 합니다."
    if fields:
        raise ApiError(ErrorCode.RULE_REJECTED, fields=fields)
    _set_status(db, course, "CS.OPEN", now)
    _audit(db, admin, "CORS_PUBLISH", "TB_CORS", course_sn, request_id, now, "강좌 공개")
    return _detail(db, admin, now, course_sn)


def close_reception(
    db: Session, admin: Admin, *, now: datetime, request_id: str, course_id: str
) -> AdminCourse:
    course = _locked(db, admin, permit(db, admin, AU.CORS_W, now), course_id)
    state = reception_state(str(course.CORS_STTS_CD), course.RCPT_BGNG_DT, course.RCPT_END_DT, now)
    if course.CORS_STTS_CD != "CS.OPEN" or state.value != "OPEN":
        raise ApiError(ErrorCode.CONFLICT_STATE)
    _set_status(db, course, "CS.CLOSE", now)
    _audit(db, admin, "CORS_CLOSE", "TB_CORS", int(course.CORS_SN), request_id, now, "접수 마감(수동)")
    return _detail(db, admin, now, int(course.CORS_SN))


# --- 폐강 -------------------------------------------------------------------------------------


def _active_applications(db: Session, bundle_sn: int, course_sn: int) -> list[Any]:
    return list(
        db.execute(
            select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_ATNLC_APLY.c.APLY_STTS_CD)
            .where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
                TB_ATNLC_APLY.c.CORS_SN == course_sn,
                TB_ATNLC_APLY.c.APLY_STTS_CD.in_(ACTIVE),
            )
            .order_by(TB_ATNLC_APLY.c.ATNLC_APLY_SN)
        ).all()
    )


def _payments(db: Session, bundle_sn: int, application_sns: list[int], status: str) -> list[Any]:
    if not application_sns:
        return []
    return list(
        db.execute(
            select(TB_STLM.c.STLM_SN, TB_STLM.c.STLM_AMT, TB_STLM.c.ATNLC_APLY_SN)
            .where(
                TB_STLM.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM.c.ATNLC_APLY_SN.in_(application_sns),
                TB_STLM.c.STLM_STTS_CD == status,
            )
            .order_by(TB_STLM.c.STLM_SN)
        ).all()
    )


def cancel_preview(db: Session, admin: Admin, *, now: datetime, course_id: str) -> CancelPreview:
    row = _visible(db, admin, permit_any(db, admin, READ, now), course_id)
    sns = [int(a.ATNLC_APLY_SN) for a in _active_applications(db, admin.bundle_sn, int(row.CORS_SN))]
    return CancelPreview(
        application_count=len(sns), paid_count=len(_payments(db, admin.bundle_sn, sns, "PS.PAID"))
    )


def cancel_course(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    course_id: str,
    reason: str,
) -> AdminCourse:
    """폐강한다. 유효한 신청을 모두 취소하고 결제한 건마다 전액 환불 요청을 접수한다(사용자 확정).

    폐강은 환불 완료가 아니다. 환불의 승인·집행은 환불 검토에서 사람이 한다(FN-057). 결제 결과를 기다리는
    신청이 있으면 자리를 지켜야 하므로 폐강을 막는다(ADR-006). 폐강한 강좌는 승격하지 않는다.
    """
    if not reason.strip():
        raise ApiError(ErrorCode.RULE_REJECTED, fields={"reason": "폐강 사유를 입력해 주세요."})
    course = _locked(db, admin, permit(db, admin, AU.CORS_W, now), course_id)
    if course.CORS_STTS_CD not in CANCELLABLE:
        raise ApiError(ErrorCode.CONFLICT_STATE)
    bundle_sn, course_sn = admin.bundle_sn, int(course.CORS_SN)
    applications = _active_applications(db, bundle_sn, course_sn)
    sns = [int(a.ATNLC_APLY_SN) for a in applications]
    if _payments(db, bundle_sn, sns, "PS.PENDING"):
        raise ApiError(
            ErrorCode.CONFLICT_STATE, "결제 결과를 확인 중인 신청이 있습니다. 결제 대사를 먼저 끝내 주세요."
        )
    refunds = 0
    for paid in _payments(db, bundle_sn, sns, "PS.PAID"):
        stlm_sn = int(paid.STLM_SN)
        lock_payment(db, stlm_sn)  # 환불 한도는 결제 행을 잠근 상태에서 본다(R14)
        amount = int(paid.STLM_AMT) - reserved_amount(db, bundle_sn, stlm_sn)
        if amount <= 0:
            continue
        refund_sn = int(
            db.execute(
                insert(TB_RFND)
                .values(
                    OPER_BNDL_SN=bundle_sn,
                    STLM_SN=stlm_sn,
                    RFND_AMT=amount,
                    RFND_STTS_CD="RS.REQUEST",
                    RFND_RSN=f"{COURSE_CANCEL_REASON}: {reason.strip()}",
                    RFND_DMND_DT=now,
                    DMND_MNGR_SN=admin.admin_sn,
                    IDEM_KEY=f"CORS-CANCEL-{course_sn}-{stlm_sn}",
                    REG_DT=now,
                )
                .returning(TB_RFND.c.RFND_SN)
            ).scalar_one()
        )
        _audit(db, admin, "RFND_REQUEST", "TB_RFND", refund_sn, request_id, now, "폐강에 따른 전액 환불 접수")
        refunds += 1
    for sn in sns:
        cancel_ready_payments(db, bundle_sn, sn, now)
        set_status(db, sn, status="ES.CANCEL", now=now, reason=COURSE_CANCEL_REASON)
    _set_status(db, course, "CS.CANCEL", now)
    _audit(
        db,
        admin,
        "CORS_CANCEL",
        "TB_CORS",
        course_sn,
        request_id,
        now,
        f"폐강(신청 취소 {len(sns)}건, 환불 접수 {refunds}건)",
    )
    return _detail(db, admin, now, course_sn)
