# 강사의 출석 입력. 지난 수업 회차를 계산하고 저장 직전에 배정·명단·버전을 다시 확인한다(FN-064, ADR-128)
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, insert, or_, select, update
from sqlalchemy.orm import Session

from app.auth.deps import Member
from app.core.errors import ApiError, ErrorCode
from app.core.masking import mask_name
from app.core.times import kst_today
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_CORS_ATND,
    TB_CORS_ATND_DTL,
    TB_CORS_ATND_HSTRY,
    TB_CORS_SCHDL,
    TB_CORS_SCHDL_CHG,
    TB_INSTR,
    TB_MBR,
)
from app.domain.application.seats import lock_course
from app.domain.attendance.schemas import (
    TeachingAttendanceCreate,
    TeachingAttendanceUpdate,
    TeachingCourse,
    TeachingCourseList,
    TeachingMark,
    TeachingRosterEntry,
    TeachingSession,
    TeachingSheet,
)
from app.domain.attendance.types import (
    CODE_BY_MARK,
    MARK_BY_CODE,
    AttendanceMark,
    TeachingSessionStatus,
)
from app.domain.course.types import Weekday

INPUT_STATUSES = ("CS.OPEN", "CS.CLOSE", "CS.RUN", "CS.END")  # 작성중·폐강한 강좌는 입력하지 않는다
ROSTER_STATUSES = ("ES.CONFIRM", "ES.COMPLETE")
ROSTER_CHANGED = "명단이 변경되었습니다. 다시 불러온 뒤 저장하세요."
ALREADY_SAVED = "이미 입력한 출석부가 있습니다. 다시 불러온 뒤 저장하세요."
WEEKDAY_ORDER = [f"DW.{day.value}" for day in Weekday]  # date.weekday()와 같은 순서(월요일이 0)


@dataclass(frozen=True)
class Lesson:
    """일정에서 계산한 수업 회차. 저장하지 않으며 출석부는 (일정, 수업일, 보강)으로 이어진다."""

    day: str  # YYYYMMDD
    schedule_sn: int
    change_sn: int | None
    start: str  # HHMMSS
    end: str
    order: int = 1  # 같은 날의 수업을 시작 시각 순으로 센 번호

    @property
    def key(self) -> tuple[str, int, int | None]:
        return self.day, self.schedule_sn, self.change_sn


def _sheet_key(row: Any) -> tuple[str, int, int | None]:
    change = None if row.CORS_SCHDL_CHG_SN is None else int(row.CORS_SCHDL_CHG_SN)
    return str(row.LCTR_YMD), int(row.CORS_SCHDL_SN), change


def _day(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _clock(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}"


# --- 담당과 회차 --------------------------------------------------------------------------------


def _instructor(db: Session, member: Member, *, lock: bool = False) -> int | None:
    """로그인한 회원에게 연결된 승인 상태의 강사. 없으면 None이다."""
    query = select(TB_INSTR.c.INSTR_SN).where(
        TB_INSTR.c.OPER_BNDL_SN == member.bundle_sn,
        TB_INSTR.c.MBR_SN == member.member_sn,
        TB_INSTR.c.INSTR_STTS_CD == "IS.APPROVE",
    )
    if lock:
        query = query.with_for_update(read=True)  # 저장하는 동안 활동중지가 끼어들지 않게 한다
    found = db.execute(query).scalar_one_or_none()
    return None if found is None else int(found)


def _course(db: Session, member: Member, course_sn: int) -> Any:
    return db.execute(
        select(TB_CORS).where(TB_CORS.c.OPER_BNDL_SN == member.bundle_sn, TB_CORS.c.CORS_SN == course_sn)
    ).first()


def _mine(db: Session, member: Member, course_sn: int, *, lock: bool = False) -> tuple[Any, int]:
    """(강좌, 강사 번호). 지금 담당하는 강좌가 아니면 404, 입력할 수 없는 상태면 409다.

    lock이면 강좌 행을 잠근 뒤 다시 확인한다. 신청 상태와 일정을 바꾸는 쪽이 같은 잠금을 쓰므로
    저장하는 동안 명단과 회차가 바뀌지 않는다.
    """
    instructor = _instructor(db, member)
    course = None if instructor is None else _course(db, member, course_sn)
    if course is None or course.INSTR_SN != instructor:
        raise ApiError(ErrorCode.NOT_FOUND)
    if lock:
        course = lock_course(db, member.bundle_sn, course_sn)
        instructor = _instructor(db, member, lock=True)
        if instructor is None or course.INSTR_SN != instructor:
            raise ApiError(ErrorCode.NOT_FOUND)
    assert instructor is not None
    if course.CORS_STTS_CD not in INPUT_STATUSES:
        raise ApiError(ErrorCode.CONFLICT_STATE, "작성중이거나 폐강한 강좌의 출석은 입력할 수 없습니다.")
    return course, instructor


def _lessons(db: Session, bundle_sn: int, course_sn: int, today: date) -> list[Lesson]:
    """오늘까지의 수업. 휴강·보강으로 대체한 원수업일은 빼고 보강일을 더한다(ATND-01). 최근 날짜가 먼저다."""
    schedules = db.execute(
        select(TB_CORS_SCHDL).where(
            TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn, TB_CORS_SCHDL.c.CORS_SN == course_sn
        )
    ).all()
    changes = db.execute(
        select(TB_CORS_SCHDL_CHG).where(
            TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL_CHG.c.CORS_SN == course_sn,
            TB_CORS_SCHDL_CHG.c.APLCN_YN == "Y",
        )
    ).all()
    replaced = {(int(c.CORS_SCHDL_SN), str(c.ORGNL_LCTR_YMD)) for c in changes}
    found: list[Lesson] = []
    for s in schedules:
        sn = int(s.CORS_SCHDL_SN)
        day = _day(str(s.APLCN_BGNG_YMD))
        day += timedelta(days=(WEEKDAY_ORDER.index(str(s.DOW_CD).strip()) - day.weekday()) % 7)
        last = min(_day(str(s.APLCN_END_YMD)), today)
        while day <= last:
            if (sn, _ymd(day)) not in replaced:
                found.append(Lesson(_ymd(day), sn, None, str(s.BGNG_TM), str(s.END_TM)))
            day += timedelta(days=7)
    for c in changes:
        if str(c.CHG_TYPE_CD).strip() == "SC.MAKEUP" and str(c.CHG_LCTR_YMD) <= _ymd(today):
            found.append(
                Lesson(
                    str(c.CHG_LCTR_YMD),
                    int(c.CORS_SCHDL_SN),
                    int(c.CORS_SCHDL_CHG_SN),
                    str(c.CHG_BGNG_TM),
                    str(c.CHG_END_TM),
                )
            )
    found.sort(key=lambda x: (x.day, x.start, x.schedule_sn, x.change_sn or 0))
    counted: dict[str, int] = {}
    numbered = []
    for x in found:
        counted[x.day] = counted.get(x.day, 0) + 1
        numbered.append(Lesson(x.day, x.schedule_sn, x.change_sn, x.start, x.end, counted[x.day]))
    return sorted(numbered, key=lambda x: (-int(x.day), x.order))


def _sheets(db: Session, bundle_sn: int, course_sn: int) -> list[Any]:
    """지운 출석부도 담는다. 같은 회차와 회차 번호는 다시 쓸 수 없기 때문이다."""
    return list(
        db.execute(
            select(TB_CORS_ATND).where(
                TB_CORS_ATND.c.OPER_BNDL_SN == bundle_sn, TB_CORS_ATND.c.CORS_SN == course_sn
            )
        ).all()
    )


def _number(lesson: Lesson, sheets: Sequence[Any]) -> int:
    """출석부가 있으면 저장한 회차, 없으면 같은 날에서 쓰지 않은 번호다."""
    same_day = [s for s in sheets if str(s.LCTR_YMD) == lesson.day]
    for sheet in same_day:
        if _sheet_key(sheet) == lesson.key:
            return int(sheet.LCTR_SEQ)
    used = {int(s.LCTR_SEQ) for s in same_day}
    number = lesson.order
    while number in used:
        number += 1
    return number


def _session(lesson: Lesson, sheets: Sequence[Any]) -> TeachingSession:
    sheet = next((s for s in sheets if _sheet_key(s) == lesson.key and s.DEL_YN == "N"), None)
    if sheet is None:
        status = TeachingSessionStatus.NOT_STARTED
    else:
        status = TeachingSessionStatus.DONE if sheet.CMPTN_YN == "Y" else TeachingSessionStatus.IN_PROGRESS
    return TeachingSession(
        class_date=_day(lesson.day),
        schedule_id=str(lesson.schedule_sn),
        change_id=None if lesson.change_sn is None else str(lesson.change_sn),
        session=_number(lesson, sheets),
        start_time=_clock(lesson.start),
        end_time=_clock(lesson.end),
        makeup=lesson.change_sn is not None,
        status=status,
        attendance_id=None if sheet is None else str(int(sheet.ATND_SN)),
    )


def list_courses(db: Session, member: Member, *, now: datetime) -> TeachingCourseList:
    """내가 지금 담당하는 강좌와 오늘까지의 수업 회차. 강사가 아니면 빈 목록이다."""
    instructor = _instructor(db, member)
    if instructor is None:
        return TeachingCourseList(items=[])
    courses = db.execute(
        select(TB_CORS.c.CORS_SN, TB_CORS.c.CORS_NM)
        .where(
            TB_CORS.c.OPER_BNDL_SN == member.bundle_sn,
            TB_CORS.c.INSTR_SN == instructor,
            TB_CORS.c.CORS_STTS_CD.in_(INPUT_STATUSES),
        )
        .order_by(TB_CORS.c.EDU_BGNG_YMD.desc(), TB_CORS.c.CORS_NM, TB_CORS.c.CORS_SN)
    ).all()
    items = []
    for course in courses:
        sn = int(course.CORS_SN)
        sheets = _sheets(db, member.bundle_sn, sn)
        lessons = _lessons(db, member.bundle_sn, sn, kst_today(now))
        items.append(
            TeachingCourse(
                course_id=str(sn),
                course_name=str(course.CORS_NM),
                sessions=[_session(x, sheets) for x in lessons],
            )
        )
    return TeachingCourseList(items=items)


# --- 명단과 보기 --------------------------------------------------------------------------------


def _details(db: Session, bundle_sn: int, attendance_sn: int | None) -> dict[int, Any]:
    if attendance_sn is None:
        return {}
    rows = db.execute(
        select(TB_CORS_ATND_DTL).where(
            TB_CORS_ATND_DTL.c.OPER_BNDL_SN == bundle_sn, TB_CORS_ATND_DTL.c.ATND_SN == attendance_sn
        )
    ).all()
    return {int(r.ATNLC_APLY_SN): r for r in rows}


def _roster(db: Session, bundle_sn: int, course_sn: int, details: dict[int, Any]) -> list[Any]:
    """수강확정·수강종료인 신청과, 이미 출석부에 있는 신청(뒤에 취소해도 기록을 남긴다). 이름 순이다."""
    eligible: ColumnElement[bool] = TB_ATNLC_APLY.c.APLY_STTS_CD.in_(ROSTER_STATUSES)
    if details:
        eligible = or_(eligible, TB_ATNLC_APLY.c.ATNLC_APLY_SN.in_(list(details)))
    return list(
        db.execute(
            select(TB_ATNLC_APLY.c.ATNLC_APLY_SN, TB_MBR.c.MBR_NM)
            .select_from(
                TB_ATNLC_APLY.join(
                    TB_MBR,
                    (TB_MBR.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
                    & (TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN),
                )
            )
            .where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
                TB_ATNLC_APLY.c.CORS_SN == course_sn,
                eligible,
            )
            .order_by(TB_MBR.c.MBR_NM, TB_ATNLC_APLY.c.ATNLC_APLY_SN)
        ).all()
    )


def _view(db: Session, member: Member, course: Any, lesson: Lesson) -> TeachingSheet:
    sn = int(course.CORS_SN)
    sheets = _sheets(db, member.bundle_sn, sn)
    session = _session(lesson, sheets)
    saved = next((s for s in sheets if _sheet_key(s) == lesson.key and s.DEL_YN == "N"), None)
    details = _details(db, member.bundle_sn, None if saved is None else int(saved.ATND_SN))
    roster = []
    for person in _roster(db, member.bundle_sn, sn, details):
        detail = details.get(int(person.ATNLC_APLY_SN))
        code = "AR.UNCHECKED" if detail is None else str(detail.ATND_RSLT_CD).strip()
        roster.append(
            TeachingRosterEntry(
                application_id=str(int(person.ATNLC_APLY_SN)),
                name=mask_name(str(person.MBR_NM)),
                mark=MARK_BY_CODE[code],
            )
        )
    counts = {mark: sum(1 for r in roster if r.mark is mark) for mark in AttendanceMark}
    return TeachingSheet(
        **session.model_dump(),
        course_id=str(sn),
        course_name=str(course.CORS_NM),
        version=None if saved is None else int(saved.RCRD_VER),
        roster=roster,
        present=counts[AttendanceMark.PRESENT],
        absent=counts[AttendanceMark.ABSENT],
        unchecked=counts[AttendanceMark.UNCHECKED],
    )


def _find(lessons: Sequence[Lesson], key: tuple[str, int, int | None]) -> Lesson:
    found = next((x for x in lessons if x.key == key), None)
    if found is None:
        message = "이 강좌의 지난 수업 회차가 아닙니다. 휴강·보강과 수업일을 확인해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"classDate": message})
    return found


def get_sheet(
    db: Session,
    member: Member,
    *,
    now: datetime,
    course_id: str,
    class_date: date,
    schedule_id: str,
    change_id: str | None,
) -> TeachingSheet:
    course, _ = _mine(db, member, int(course_id))
    lessons = _lessons(db, member.bundle_sn, int(course_id), kst_today(now))
    key = (_ymd(class_date), int(schedule_id), None if change_id is None else int(change_id))
    return _view(db, member, course, _find(lessons, key))


# --- 저장 ---------------------------------------------------------------------------------------


def _confirmed(confirmed: bool) -> None:
    if not confirmed:
        message = "입력 내용을 확인해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"confirmed": message})


def _checked_codes(roster: Sequence[Any], marks: Sequence[TeachingMark]) -> dict[int, str]:
    """화면이 본 명단과 지금 명단이 같아야 한다. 신청번호 순서대로 저장할 코드를 준다."""
    if not roster:
        message = "수강생이 없어 저장할 수 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"marks": message})
    sent = {int(m.application_id): CODE_BY_MARK[m.mark] for m in marks}
    if set(sent) != {int(r.ATNLC_APLY_SN) for r in roster}:
        raise ApiError(ErrorCode.CONFLICT_STATE, ROSTER_CHANGED)
    return {sn: sent[sn] for sn in sorted(sent)}


def _totals(codes: dict[int, str]) -> dict[str, Any]:
    present = sum(1 for c in codes.values() if c == "AR.PRESENT")
    absent = sum(1 for c in codes.values() if c == "AR.ABSENT")
    unchecked = len(codes) - present - absent
    return {
        "ATND_NOPE": present,
        "ABSNC_NOPE": absent,
        "UNCHCK_NOPE": unchecked,
        "CMPTN_YN": "Y" if unchecked == 0 else "N",
    }


def _history(
    db: Session,
    member: Member,
    instructor: int,
    *,
    attendance_sn: int,
    detail_sn: int | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    version: int,
    request_id: str,
    now: datetime,
) -> None:
    """변경 전후·행위 강사·요청 ID를 쌓는다. 이름·연락처는 담지 않는다."""
    db.execute(
        insert(TB_CORS_ATND_HSTRY).values(
            OPER_BNDL_SN=member.bundle_sn,
            ATND_SN=attendance_sn,
            ATND_DTL_SN=detail_sn,
            ACTR_INSTR_SN=instructor,
            ACTN_CD=action,
            BFR_VL_CN=None if before is None else json.dumps(before, ensure_ascii=False),
            AFTR_VL_CN=json.dumps(after, ensure_ascii=False),
            TRGT_RCRD_VER=version,
            DMND_ID=request_id,
            REG_DT=now,
        )
    )


def _add_detail(
    db: Session,
    member: Member,
    instructor: int,
    attendance_sn: int,
    application_sn: int,
    code: str,
    request_id: str,
    now: datetime,
) -> None:
    sn = int(
        db.execute(
            insert(TB_CORS_ATND_DTL)
            .values(
                OPER_BNDL_SN=member.bundle_sn,
                ATND_SN=attendance_sn,
                ATNLC_APLY_SN=application_sn,
                ATND_RSLT_CD=code,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_CORS_ATND_DTL.c.ATND_DTL_SN)
        ).scalar_one()
    )
    _history(
        db,
        member,
        instructor,
        attendance_sn=attendance_sn,
        detail_sn=sn,
        action="AH.CREATE",
        before=None,
        after={"mark": code},
        version=1,
        request_id=request_id,
        now=now,
    )


def _digest(body: TeachingAttendanceCreate) -> str:
    content = [
        body.course_id,
        body.schedule_id,
        body.change_id,
        body.class_date.isoformat(),
        sorted((int(m.application_id), m.mark.value) for m in body.marks),
    ]
    return hashlib.sha256(json.dumps(content).encode()).hexdigest()


def _replayed(db: Session, member: Member, key: str, digest: str) -> Any | None:
    """같은 멱등키로 이미 만든 출석부. 만들 때의 내용과 다르면 409다."""
    sheet = db.execute(
        select(TB_CORS_ATND).where(
            TB_CORS_ATND.c.OPER_BNDL_SN == member.bundle_sn, TB_CORS_ATND.c.IDEM_KEY == key
        )
    ).first()
    if sheet is None:
        return None
    created = db.execute(
        select(TB_CORS_ATND_HSTRY.c.AFTR_VL_CN).where(
            TB_CORS_ATND_HSTRY.c.OPER_BNDL_SN == member.bundle_sn,
            TB_CORS_ATND_HSTRY.c.ATND_SN == sheet.ATND_SN,
            TB_CORS_ATND_HSTRY.c.ATND_DTL_SN.is_(None),
            TB_CORS_ATND_HSTRY.c.ACTN_CD == "AH.CREATE",
        )
    ).scalar_one()
    if json.loads(str(created)).get("request") != digest:
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return sheet


def create_sheet(
    db: Session,
    member: Member,
    body: TeachingAttendanceCreate,
    *,
    idem_key: str,
    now: datetime,
    request_id: str,
) -> TeachingSheet:
    course_sn = int(body.course_id)
    course, instructor = _mine(db, member, course_sn, lock=True)
    _confirmed(body.confirmed)
    key = f"t{instructor}-{idem_key}"  # 강사마다 키 공간을 나눈다
    digest = _digest(body)
    lessons = _lessons(db, member.bundle_sn, course_sn, kst_today(now))
    prior = _replayed(db, member, key, digest)
    if prior is not None:
        return _view(db, member, course, _find(lessons, _sheet_key(prior)))
    change = None if body.change_id is None else int(body.change_id)
    lesson = _find(lessons, (_ymd(body.class_date), int(body.schedule_id), change))
    sheets = _sheets(db, member.bundle_sn, course_sn)
    if any(_sheet_key(s) == lesson.key for s in sheets):
        raise ApiError(ErrorCode.CONFLICT_STATE, ALREADY_SAVED)
    codes = _checked_codes(_roster(db, member.bundle_sn, course_sn, {}), body.marks)
    totals = _totals(codes)
    sn = int(
        db.execute(
            insert(TB_CORS_ATND)
            .values(
                OPER_BNDL_SN=member.bundle_sn,
                CORS_SN=course_sn,
                CORS_SCHDL_SN=lesson.schedule_sn,
                CORS_SCHDL_CHG_SN=lesson.change_sn,
                INSTR_SN=instructor,
                LCTR_YMD=lesson.day,
                LCTR_SEQ=_number(lesson, sheets),
                IDEM_KEY=key,
                DEL_YN="N",
                REG_DT=now,
                RCRD_VER=1,
                **totals,
            )
            .returning(TB_CORS_ATND.c.ATND_SN)
        ).scalar_one()
    )
    _history(
        db,
        member,
        instructor,
        attendance_sn=sn,
        detail_sn=None,
        action="AH.CREATE",
        before=None,
        after={**totals, "request": digest},
        version=1,
        request_id=request_id,
        now=now,
    )
    for application_sn, code in codes.items():
        _add_detail(db, member, instructor, sn, application_sn, code, request_id, now)
    return _view(db, member, course, lesson)


def update_sheet(
    db: Session,
    member: Member,
    attendance_id: str,
    body: TeachingAttendanceUpdate,
    *,
    now: datetime,
    request_id: str,
) -> TeachingSheet:
    query = select(TB_CORS_ATND).where(
        TB_CORS_ATND.c.OPER_BNDL_SN == member.bundle_sn,
        TB_CORS_ATND.c.ATND_SN == int(attendance_id),
        TB_CORS_ATND.c.DEL_YN == "N",
    )
    found = db.execute(query).first()
    if found is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    course_sn = int(found.CORS_SN)
    course, instructor = _mine(db, member, course_sn, lock=True)
    sheet = db.execute(query.with_for_update()).one()  # 잠근 뒤의 값으로 버전을 확인한다
    _confirmed(body.confirmed)
    if int(sheet.RCRD_VER) != body.version:
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    sn = int(sheet.ATND_SN)
    lesson = _find(_lessons(db, member.bundle_sn, course_sn, kst_today(now)), _sheet_key(sheet))
    details = _details(db, member.bundle_sn, sn)
    codes = _checked_codes(_roster(db, member.bundle_sn, course_sn, details), body.marks)
    for application_sn, code in codes.items():
        detail = details.get(application_sn)
        if detail is None:
            _add_detail(db, member, instructor, sn, application_sn, code, request_id, now)
            continue
        old = str(detail.ATND_RSLT_CD).strip()
        if old == code:
            continue
        version = int(detail.RCRD_VER) + 1
        db.execute(
            update(TB_CORS_ATND_DTL)
            .where(TB_CORS_ATND_DTL.c.ATND_DTL_SN == detail.ATND_DTL_SN)
            .values(ATND_RSLT_CD=code, RCRD_VER=version, MDFCN_DT=now)
        )
        _history(
            db,
            member,
            instructor,
            attendance_sn=sn,
            detail_sn=int(detail.ATND_DTL_SN),
            action="AH.UPDATE",
            before={"mark": old},
            after={"mark": code},
            version=version,
            request_id=request_id,
            now=now,
        )
    totals = _totals(codes)
    db.execute(
        update(TB_CORS_ATND)
        .where(TB_CORS_ATND.c.ATND_SN == sn)
        .values(**totals, RCRD_VER=body.version + 1, MDFCN_DT=now)
    )
    _history(
        db,
        member,
        instructor,
        attendance_sn=sn,
        detail_sn=None,
        action="AH.UPDATE",
        before={name: _plain(getattr(sheet, name)) for name in totals},
        after=totals,
        version=body.version + 1,
        request_id=request_id,
        now=now,
    )
    return _view(db, member, course, lesson)


def _plain(value: Any) -> Any:
    """DB의 숫자(Decimal)와 문자를 JSON에 담을 값으로."""
    return value.strip() if isinstance(value, str) else int(value)
