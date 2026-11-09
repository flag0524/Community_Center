# 강좌 분야·목록·상세·강의계획 공개 조회. 접수·교육 상태는 서버가 판정한다(FN-012~015, RQ-QUR-NF-008)
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_CORS_CLSF,
    TB_CORS_SCHDL,
    TB_EDU_CYCL,
    TB_FCLT,
    TB_FILE,
    TB_INSTR,
    TB_MBR,
)
from app.domain.course.schemas import (
    CategoryList,
    CategoryRef,
    CourseDetail,
    CourseListCriteria,
    CoursePage,
    CoursePlan,
    CourseSummary,
    CycleInfo,
    FileRef,
    ScheduleSlot,
)
from app.domain.course.types import EducationState, ReceptionState, Weekday

KST = timezone(timedelta(hours=9))
OPEN = "CS.OPEN"
# 주민에게 보이는 강좌 상태. 작성중·종료·폐강은 공개 조회에서 없는 강좌다(ADR-035)
VISIBLE_STATUSES = (OPEN, "CS.CLOSE", "CS.RUN")
SEAT_STATUSES = ("ES.HOLD", "ES.CONFIRM")  # 정원을 차지하는 신청 상태(ADR-028)
WEEKDAYS = list(Weekday)


def reception_state(course_status: str, begin: datetime, end: datetime, now: datetime) -> ReceptionState:
    """접수 상태. 공개(CS.OPEN)이고 시작 이상·종료 미만일 때만 접수중이다. 신청 생성도 같은 규칙을 쓴다(TDD 5.2)."""
    if course_status == OPEN and now < begin:
        return ReceptionState.UPCOMING
    if course_status == OPEN and now < end:
        return ReceptionState.OPEN
    return ReceptionState.CLOSED


def _education_state(today: date, begin: date, end: date) -> EducationState:
    if today < begin:
        return EducationState.UPCOMING
    return EducationState.ONGOING if today <= end else EducationState.ENDED


def ymd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)


def _today(now: datetime) -> date:
    return _utc(now).astimezone(KST).date()


def _clock(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}"


def _status_condition(state: ReceptionState, now: datetime) -> ColumnElement[bool]:
    """reception_state()와 같은 판정을 SQL로 쓴다. 쪽 나누기가 판정 뒤의 건수와 맞아야 해서다."""
    upcoming = and_(TB_CORS.c.CORS_STTS_CD == OPEN, TB_CORS.c.RCPT_BGNG_DT > now)
    receiving = and_(
        TB_CORS.c.CORS_STTS_CD == OPEN, TB_CORS.c.RCPT_BGNG_DT <= now, TB_CORS.c.RCPT_END_DT > now
    )
    if state is ReceptionState.UPCOMING:
        return upcoming
    if state is ReceptionState.OPEN:
        return receiving
    return not_(or_(upcoming, receiving))


def _usable_category() -> ColumnElement[bool]:
    return and_(TB_CORS_CLSF.c.USE_YN == "Y", TB_CORS_CLSF.c.DEL_YN == "N")


def list_categories(db: Session, bundle_sn: int) -> CategoryList:
    rows = db.execute(
        select(TB_CORS_CLSF.c.CORS_CLSF_SN, TB_CORS_CLSF.c.CORS_CLSF_NM)
        .where(TB_CORS_CLSF.c.OPER_BNDL_SN == bundle_sn, _usable_category())
        .order_by(TB_CORS_CLSF.c.SORT_SEQ, TB_CORS_CLSF.c.CORS_CLSF_SN)
    ).all()
    return CategoryList(items=[CategoryRef(category_id=str(int(r[0])), name=str(r[1])) for r in rows])


def cycle_info(row: Any, now: datetime) -> CycleInfo:
    return CycleInfo(
        name=str(row.EDU_CYCL_NM),
        education_start=ymd(row.EDU_BGNG_YMD),
        education_end=ymd(row.EDU_END_YMD),
        reception_start=_utc(row.RCPT_BGNG_DT),
        reception_end=_utc(row.RCPT_END_DT),
        reception_state=reception_state(OPEN, row.RCPT_BGNG_DT, row.RCPT_END_DT, now),
    )


def current_cycle(db: Session, bundle_sn: int, now: datetime) -> Any:
    """기준 기수. 교육이 끝나지 않은 기수 중 교육 시작이 가장 이른 것, 없으면 가장 최근에 끝난 기수다."""
    today = _today(now).strftime("%Y%m%d")
    base = select(TB_EDU_CYCL).where(TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn, TB_EDU_CYCL.c.USE_YN == "Y")
    row = db.execute(
        base.where(TB_EDU_CYCL.c.EDU_END_YMD >= today)
        .order_by(TB_EDU_CYCL.c.EDU_BGNG_YMD, TB_EDU_CYCL.c.EDU_CYCL_SN)
        .limit(1)
    ).first()
    if row is None:
        row = db.execute(
            base.order_by(TB_EDU_CYCL.c.EDU_END_YMD.desc(), TB_EDU_CYCL.c.EDU_CYCL_SN.desc()).limit(1)
        ).first()
    return row


def _occupied_seats() -> Any:
    return (
        select(func.count())
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
            TB_ATNLC_APLY.c.CORS_SN == TB_CORS.c.CORS_SN,
            TB_ATNLC_APLY.c.APLY_STTS_CD.in_(SEAT_STATUSES),
        )
        .scalar_subquery()
    )


def _waiting() -> Any:
    return (
        select(func.count())
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
            TB_ATNLC_APLY.c.CORS_SN == TB_CORS.c.CORS_SN,
            TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT",
        )
        .scalar_subquery()
    )


def course_query() -> Any:
    """공개 범위 조건이 없는 기본 조회다. 호출하는 쪽이 보일 상태를 정한다. 강좌 한 행에 분류명·공개 강사명·점유·대기 수를 붙인 조회. 강사는 승인되고 공개로 둔 사람만 이름이 나간다."""
    instructor_name = (
        select(TB_MBR.c.MBR_NM)
        .join(
            TB_INSTR,
            and_(TB_INSTR.c.OPER_BNDL_SN == TB_MBR.c.OPER_BNDL_SN, TB_INSTR.c.MBR_SN == TB_MBR.c.MBR_SN),
        )
        .where(
            TB_INSTR.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
            TB_INSTR.c.INSTR_SN == TB_CORS.c.INSTR_SN,
            TB_INSTR.c.RLS_YN == "Y",
            TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE",
        )
        .scalar_subquery()
    )
    return (
        select(
            TB_CORS,
            TB_CORS_CLSF.c.CORS_CLSF_NM.label("CLSF_NM"),
            instructor_name.label("INSTR_NM"),
            TB_EDU_CYCL.c.EDU_CYCL_NM.label("CYCL_NM"),
            _occupied_seats().label("OCCUPIED"),
            _waiting().label("WAITING"),
        )
        .join(
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
                _usable_category(),
            ),
        )
    )


def _schedules(
    db: Session, bundle_sn: int, course_sns: list[int], now: datetime
) -> tuple[dict[int, list[ScheduleSlot]], dict[int, str]]:
    """강좌별 정규 일정(같은 시간대의 요일을 한 줄로 묶음)과 강의실 이름. 적용 기간이 끝난 행은 뺀다."""
    if not course_sns:
        return {}, {}
    rows = db.execute(
        select(
            TB_CORS_SCHDL.c.CORS_SN,
            TB_CORS_SCHDL.c.DOW_CD,
            TB_CORS_SCHDL.c.BGNG_TM,
            TB_CORS_SCHDL.c.END_TM,
            TB_FCLT.c.FCLT_NM,
        )
        .join(
            TB_FCLT,
            and_(
                TB_FCLT.c.OPER_BNDL_SN == TB_CORS_SCHDL.c.OPER_BNDL_SN,
                TB_FCLT.c.FCLT_SN == TB_CORS_SCHDL.c.FCLT_SN,
            ),
        )
        .where(
            TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL.c.CORS_SN.in_(course_sns),
            TB_CORS_SCHDL.c.APLCN_END_YMD >= _today(now).strftime("%Y%m%d"),
        )
        .order_by(TB_CORS_SCHDL.c.CORS_SCHDL_SN)
    ).all()
    grouped: dict[int, dict[tuple[str, str], set[Weekday]]] = defaultdict(lambda: defaultdict(set))
    rooms: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        course = int(row.CORS_SN)
        grouped[course][(str(row.BGNG_TM), str(row.END_TM))].add(Weekday(str(row.DOW_CD).removeprefix("DW.")))
        if str(row.FCLT_NM) not in rooms[course]:
            rooms[course].append(str(row.FCLT_NM))
    slots = {
        course: [
            ScheduleSlot(
                days=[d for d in WEEKDAYS if d in days], start_time=_clock(start), end_time=_clock(end)
            )
            for (start, end), days in sorted(times.items())
        ]
        for course, times in grouped.items()
    }
    return slots, {course: ", ".join(names) for course, names in rooms.items()}


def summaries(db: Session, bundle_sn: int, rows: list[Any], now: datetime) -> list[CourseSummary]:
    slots, rooms = _schedules(db, bundle_sn, [int(r.CORS_SN) for r in rows], now)
    today = _today(now)
    result = []
    for row in rows:
        course = int(row.CORS_SN)
        category = (
            None
            if row.CORS_CLSF_SN is None or row.CLSF_NM is None
            else CategoryRef(category_id=str(int(row.CORS_CLSF_SN)), name=str(row.CLSF_NM))
        )
        begin, end = ymd(row.EDU_BGNG_YMD), ymd(row.EDU_END_YMD)
        result.append(
            CourseSummary(
                course_id=str(course),
                name=str(row.CORS_NM),
                category=category,
                instructor_name=None if row.INSTR_NM is None else str(row.INSTR_NM),
                schedules=slots.get(course, []),
                room=rooms.get(course),
                education_start=begin,
                education_end=end,
                reception_start=_utc(row.RCPT_BGNG_DT),
                reception_end=_utc(row.RCPT_END_DT),
                reception_state=reception_state(
                    str(row.CORS_STTS_CD), row.RCPT_BGNG_DT, row.RCPT_END_DT, now
                ),
                education_state=_education_state(today, begin, end),
                fee=int(row.TTCHG),
                capacity=int(row.RCRT_NOPE),
                remaining_seats=max(int(row.RCRT_NOPE) - int(row.OCCUPIED), 0),
                waiting_count=int(row.WAITING),
            )
        )
    return result


def list_courses(
    db: Session,
    bundle_sn: int,
    now: datetime,
    *,
    q: str | None,
    category_id: str | None,
    day: Weekday | None,
    status: ReceptionState | None,
    page: int,
    size: int,
) -> CoursePage:
    cycle = current_cycle(db, bundle_sn, now)
    conditions: list[ColumnElement[bool]] = [TB_CORS.c.OPER_BNDL_SN == bundle_sn]
    if cycle is None:
        conditions.append(TB_CORS.c.CORS_SN.is_(None))  # 기수가 없으면 보여 줄 강좌가 없다
    else:
        conditions.append(TB_CORS.c.EDU_CYCL_SN == cycle.EDU_CYCL_SN)
    if q and q.strip():
        needle = q.strip()
        instructor_match = exists().where(
            TB_INSTR.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
            TB_INSTR.c.INSTR_SN == TB_CORS.c.INSTR_SN,
            TB_INSTR.c.RLS_YN == "Y",
            TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE",
            exists().where(
                TB_MBR.c.OPER_BNDL_SN == TB_INSTR.c.OPER_BNDL_SN,
                TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN,
                TB_MBR.c.MBR_NM.contains(needle, autoescape=True),
            ),
        )
        conditions.append(or_(TB_CORS.c.CORS_NM.contains(needle, autoescape=True), instructor_match))
    if category_id is not None:
        conditions.append(TB_CORS.c.CORS_CLSF_SN == int(category_id))
    if day is not None:
        conditions.append(
            exists().where(
                TB_CORS_SCHDL.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_CORS_SCHDL.c.CORS_SN == TB_CORS.c.CORS_SN,
                TB_CORS_SCHDL.c.DOW_CD == f"DW.{day.value}",
                TB_CORS_SCHDL.c.APLCN_END_YMD >= _today(now).strftime("%Y%m%d"),
            )
        )
    if status is not None:
        conditions.append(_status_condition(status, now))
    conditions.append(TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_STATUSES))
    query = course_query().where(*conditions)
    total = int(db.execute(select(func.count()).select_from(TB_CORS).where(*conditions)).scalar_one())
    rows = db.execute(query.order_by(TB_CORS.c.CORS_SN).limit(size).offset((page - 1) * size)).all()
    return CoursePage(
        items=summaries(db, bundle_sn, list(rows), now),
        page=page,
        size=size,
        total=total,
        criteria=CourseListCriteria(
            basis_at=_utc(now), cycle=None if cycle is None else cycle_info(cycle, now)
        ),
    )


def visible_course(db: Session, bundle_sn: int, course_id: str) -> Any:
    row = db.execute(
        course_query().where(
            TB_CORS.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS.c.CORS_SN == int(course_id),
            TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_STATUSES),
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _plan_file(db: Session, bundle_sn: int, course_sn: int) -> Any:
    return db.execute(
        select(TB_FILE.c.FILE_SN, TB_FILE.c.FILE_NM, TB_FILE.c.FILE_SZ)
        .where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.CORS_SN == course_sn,
            TB_FILE.c.FILE_USE_CD == "FP.PLAN",
            TB_FILE.c.FILE_STTS_CD == "FS.SAFE",
        )
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
        .limit(1)
    ).first()


def get_course(db: Session, bundle_sn: int, course_id: str, now: datetime) -> CourseDetail:
    row = visible_course(db, bundle_sn, course_id)
    summary = summaries(db, bundle_sn, [row], now)[0]
    has_plan = (
        bool(row.LCTR_PLAN_CN and str(row.LCTR_PLAN_CN).strip())
        or _plan_file(db, bundle_sn, int(row.CORS_SN)) is not None
    )
    return CourseDetail(
        **summary.model_dump(),
        server_now=_utc(now),
        cycle_name=str(row.CYCL_NM),
        wait_capacity=int(row.WTNG_NOPE),
        out_of_area_reception_start=None
        if row.OTSD_RGN_RCPT_BGNG_DT is None
        else _utc(row.OTSD_RGN_RCPT_BGNG_DT),
        description=None if row.LCTR_CN is None else str(row.LCTR_CN),
        has_plan=has_plan,
    )


def get_plan(db: Session, bundle_sn: int, course_id: str) -> CoursePlan:
    row = visible_course(db, bundle_sn, course_id)
    file = _plan_file(db, bundle_sn, int(row.CORS_SN))
    return CoursePlan(
        course_id=str(int(row.CORS_SN)),
        plan_text=None if row.LCTR_PLAN_CN is None else str(row.LCTR_PLAN_CN),
        plan_file=None
        if file is None
        else FileRef(file_id=str(int(file.FILE_SN)), name=str(file.FILE_NM), size_bytes=int(file.FILE_SZ)),
    )
