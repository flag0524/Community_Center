# 관리자 강좌 일정·휴보강(조회 AU.CORS_R, 변경 AU.CORS_W). 시설 중복을 서버가 판정하고 시설별로 저장을 한 줄로 세운다(FN-049, SCH-01~03, DV107·108, ADR-061)
import hashlib
import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, and_, delete, func, select
from sqlalchemy.orm import Session, aliased

from app.audit import record_job
from app.auth.admin_access import Admin, permit, permit_any, scope_for
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_CORS, TB_CORS_ATND, TB_CORS_SCHDL, TB_CORS_SCHDL_CHG, TB_FCLT, TB_JOB_HSTRY
from app.db.versioned import update_versioned
from app.domain.admin.education_service import EDITABLE, _visible
from app.domain.admin.education_types import ScheduleChangeKind
from app.domain.admin.schedule_schemas import (
    CourseSchedules,
    Schedule,
    ScheduleChange,
    ScheduleChangeWrite,
    ScheduleUpdate,
    ScheduleWrite,
)
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.seats import lock_course
from app.domain.course.types import Weekday

WEEKDAYS = list(Weekday)
LABEL = {"MON": "월", "TUE": "화", "WED": "수", "THU": "목", "FRI": "금", "SAT": "토", "SUN": "일"}
CHANGE_CODE = {ScheduleChangeKind.CANCEL: "SC.CANCEL", ScheduleChangeKind.MAKEUP: "SC.MAKEUP"}
CODE_CHANGE = {code: kind for kind, code in CHANGE_CODE.items()}
ROOM = aliased(TB_FCLT, name="room")
CENTER = aliased(TB_FCLT, name="center")


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _date(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _tm(value: str) -> str:
    """HH:MM을 저장 형식(HHMMSS)으로."""
    return f"{value[:2]}{value[3:5]}00"


def _clock(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}"


def _day_code(weekday: date) -> str:
    return f"DW.{WEEKDAYS[weekday.weekday()].value}"


def _room_name(row: Any) -> str:
    """강의실 이름 앞에 센터를 붙인다. 센터를 알 수 없으면 강의실 이름만 쓴다."""
    return f"{row.CENTER_NM} {row.ROOM_NM}" if row.CENTER_NM else str(row.ROOM_NM)


def _marker(idem_key: str, course_id: str, body: BaseModel) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(f"{course_id}:{body.model_dump_json()}".encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def _replayed(db: Session, admin: Admin, job: str, mark: str) -> int | None:
    """같은 키로 이미 등록했으면 그 번호를 준다. 내용이 다르면 409다."""
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == job,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
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


# --- 조회 ---------------------------------------------------------------------------------------


def _schedule_query(bundle_sn: int, course_sn: int) -> Select[Any]:
    return (
        select(TB_CORS_SCHDL, ROOM.c.FCLT_NM.label("ROOM_NM"), CENTER.c.FCLT_NM.label("CENTER_NM"))
        .select_from(
            TB_CORS_SCHDL.join(
                ROOM,
                and_(
                    ROOM.c.OPER_BNDL_SN == TB_CORS_SCHDL.c.OPER_BNDL_SN,
                    ROOM.c.FCLT_SN == TB_CORS_SCHDL.c.FCLT_SN,
                ),
            ).outerjoin(CENTER, CENTER.c.FCLT_SN == ROOM.c.UP_FCLT_SN)
        )
        .where(TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn, TB_CORS_SCHDL.c.CORS_SN == course_sn)
    )


def _schedule(row: Any) -> Schedule:
    return Schedule(
        schedule_id=str(int(row.CORS_SCHDL_SN)),
        weekday=Weekday(str(row.DOW_CD).removeprefix("DW.")),
        start_time=_clock(str(row.BGNG_TM)),
        end_time=_clock(str(row.END_TM)),
        facility_id=str(int(row.FCLT_SN)),
        period_start=_date(str(row.APLCN_BGNG_YMD)),
        period_end=_date(str(row.APLCN_END_YMD)),
        facility_name=_room_name(row),
        version=int(row.RCRD_VER),
    )


def _change(row: Any) -> ScheduleChange:
    makeup = CODE_CHANGE[str(row.CHG_TYPE_CD)] is ScheduleChangeKind.MAKEUP
    original = _date(str(row.ORGNL_LCTR_YMD))
    return ScheduleChange(
        change_id=str(int(row.CORS_SCHDL_CHG_SN)),
        class_date=_date(str(row.CHG_LCTR_YMD)) if makeup else original,
        original_date=original,
        kind=CODE_CHANGE[str(row.CHG_TYPE_CD)],
        facility_id=str(int(row.CHG_FCLT_SN)) if makeup else None,
        start_time=_clock(str(row.CHG_BGNG_TM)) if makeup else None,
        end_time=_clock(str(row.CHG_END_TM)) if makeup else None,
        reason=str(row.CHG_RSN),
        facility_name=_room_name(row) if makeup else None,
    )


def _changes(db: Session, bundle_sn: int, course_sn: int) -> list[Any]:
    return list(
        db.execute(
            select(TB_CORS_SCHDL_CHG, ROOM.c.FCLT_NM.label("ROOM_NM"), CENTER.c.FCLT_NM.label("CENTER_NM"))
            .select_from(
                TB_CORS_SCHDL_CHG.outerjoin(
                    ROOM,
                    and_(
                        ROOM.c.OPER_BNDL_SN == TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN,
                        ROOM.c.FCLT_SN == TB_CORS_SCHDL_CHG.c.CHG_FCLT_SN,
                    ),
                ).outerjoin(CENTER, CENTER.c.FCLT_SN == ROOM.c.UP_FCLT_SN)
            )
            .where(TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == bundle_sn, TB_CORS_SCHDL_CHG.c.CORS_SN == course_sn)
            .order_by(TB_CORS_SCHDL_CHG.c.ORGNL_LCTR_YMD, TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN)
        ).all()
    )


def _view(db: Session, admin: Admin, now: datetime, course: Any) -> CourseSchedules:
    sn = int(course.CORS_SN)
    schedules = list(db.execute(_schedule_query(admin.bundle_sn, sn)).all())
    order = {f"DW.{d.value}": n for n, d in enumerate(WEEKDAYS)}
    schedules.sort(key=lambda r: (order[str(r.DOW_CD)], str(r.BGNG_TM), int(r.CORS_SCHDL_SN)))
    write = scope_for(db, admin, AU.CORS_W, now)
    return CourseSchedules(
        course_id=str(sn),
        course_name=str(course.CORS_NM),
        schedules=[_schedule(r) for r in schedules],
        changes=[_change(r) for r in _changes(db, admin.bundle_sn, sn)],
        can_edit=write.covers(None if course.DONG_SN is None else int(course.DONG_SN))
        and course.CORS_STTS_CD in EDITABLE,
    )


def get_schedules(db: Session, admin: Admin, *, now: datetime, course_id: str) -> CourseSchedules:
    scope = permit_any(db, admin, (AU.CORS_R, AU.CORS_W), now)
    return _view(db, admin, now, _visible(db, admin, scope, course_id))


# --- 규칙 ---------------------------------------------------------------------------------------


def _writable(db: Session, admin: Admin, now: datetime, course_id: str) -> Any:
    """범위를 확인하고 강좌 행을 잠근다. 폐강·종료한 강좌의 일정은 고치지 못한다(409)."""
    scope = permit(db, admin, AU.CORS_W, now)
    _visible(db, admin, scope, course_id)
    course = lock_course(db, admin.bundle_sn, int(course_id))
    if course.CORS_STTS_CD not in EDITABLE:
        raise ApiError(ErrorCode.CONFLICT_STATE, "폐강·종료한 강좌의 일정은 고칠 수 없습니다.")
    return course


def _room(db: Session, bundle_sn: int, facility_id: str) -> Any:
    """사용 중인 강의실만 고를 수 있다. 같은 시설의 저장을 한 줄로 세우려고 행을 잠근다(SCH-03)."""
    row = db.execute(
        select(TB_FCLT)
        .where(
            TB_FCLT.c.OPER_BNDL_SN == bundle_sn,
            TB_FCLT.c.FCLT_SN == int(facility_id),
            TB_FCLT.c.FCLT_TYPE_CD == "FT.ROOM",
            TB_FCLT.c.USE_YN == "Y",
        )
        .with_for_update()
    ).first()
    if row is None:
        raise _fail("facilityId", "사용 중인 강의실을 선택해 주세요.")
    return row


def _times(start: str, end: str) -> None:
    if _tm(start) >= _tm(end):
        raise _fail("endTime", "종료 시각은 시작 시각보다 뒤여야 합니다.")


def _inside(course: Any, start: date, end: date, field: str) -> None:
    if _ymd(start) < str(course.EDU_BGNG_YMD) or _ymd(end) > str(course.EDU_END_YMD):
        raise _fail(field, "강좌 교육기간 안이어야 합니다.")


def _overlaps(a_start: str, a_end: str, b_start: Any, b_end: Any) -> Any:
    return and_(a_start < b_end, b_start < a_end)  # 종료와 다음 시작이 같은 것은 겹치지 않는다


def _conflict_message(room: Any, day: str, start: str, end: str, course_name: Any) -> str:
    return f"{room.FCLT_NM} {day} {_clock(start)}~{_clock(end)}에 {course_name}이(가) 있습니다."


def _regular_conflict(
    db: Session,
    bundle_sn: int,
    room: Any,
    weekday: str,
    start: str,
    end: str,
    period: tuple[str, str],
    *,
    own_course: int,
    except_schedule: int | None,
) -> str | None:
    """같은 시설·요일에 시간과 기간이 겹치는 다른 강좌의 일정. 같은 강좌의 일정끼리는 거절하지 않는다(FN-049)."""
    query = (
        select(TB_CORS.c.CORS_NM, TB_CORS_SCHDL.c.BGNG_TM, TB_CORS_SCHDL.c.END_TM)
        .select_from(TB_CORS_SCHDL.join(TB_CORS, TB_CORS.c.CORS_SN == TB_CORS_SCHDL.c.CORS_SN))
        .where(
            TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL.c.FCLT_SN == room.FCLT_SN,
            TB_CORS_SCHDL.c.DOW_CD == weekday,
            TB_CORS_SCHDL.c.CORS_SN != own_course,
            _overlaps(start, end, TB_CORS_SCHDL.c.BGNG_TM, TB_CORS_SCHDL.c.END_TM),
            TB_CORS_SCHDL.c.APLCN_BGNG_YMD <= period[1],
            TB_CORS_SCHDL.c.APLCN_END_YMD >= period[0],
        )
        .limit(1)
    )
    if except_schedule is not None:
        query = query.where(TB_CORS_SCHDL.c.CORS_SCHDL_SN != except_schedule)
    found = db.execute(query).first()
    return (
        None
        if found is None
        else _conflict_message(
            room, LABEL[weekday.removeprefix("DW.")], str(found.BGNG_TM), str(found.END_TM), found.CORS_NM
        )
    )


def _makeup_conflict_in_period(
    db: Session,
    bundle_sn: int,
    room: Any,
    weekday: str,
    start: str,
    end: str,
    period: tuple[str, str],
    own_course: int,
) -> str | None:
    """다른 강좌의 보강이 이 일정의 요일·시간·기간에 걸리는가."""
    rows = db.execute(
        select(
            TB_CORS_SCHDL_CHG.c.CHG_LCTR_YMD,
            TB_CORS_SCHDL_CHG.c.CHG_BGNG_TM,
            TB_CORS_SCHDL_CHG.c.CHG_END_TM,
            TB_CORS.c.CORS_NM,
        )
        .select_from(TB_CORS_SCHDL_CHG.join(TB_CORS, TB_CORS.c.CORS_SN == TB_CORS_SCHDL_CHG.c.CORS_SN))
        .where(
            TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL_CHG.c.CHG_TYPE_CD == "SC.MAKEUP",
            TB_CORS_SCHDL_CHG.c.APLCN_YN == "Y",
            TB_CORS_SCHDL_CHG.c.CHG_FCLT_SN == room.FCLT_SN,
            TB_CORS_SCHDL_CHG.c.CORS_SN != own_course,
            _overlaps(start, end, TB_CORS_SCHDL_CHG.c.CHG_BGNG_TM, TB_CORS_SCHDL_CHG.c.CHG_END_TM),
            TB_CORS_SCHDL_CHG.c.CHG_LCTR_YMD >= period[0],
            TB_CORS_SCHDL_CHG.c.CHG_LCTR_YMD <= period[1],
        )
    ).all()
    for r in rows:
        if _day_code(_date(str(r.CHG_LCTR_YMD))) == weekday:
            return _conflict_message(
                room, LABEL[weekday.removeprefix("DW.")], str(r.CHG_BGNG_TM), str(r.CHG_END_TM), r.CORS_NM
            )
    return None


def _check_schedule(
    db: Session, admin: Admin, course: Any, room: Any, body: ScheduleWrite, *, except_schedule: int | None
) -> None:
    _times(body.start_time, body.end_time)
    if body.period_start > body.period_end:
        raise _fail("periodEnd", "적용 종료는 적용 시작보다 같거나 뒤여야 합니다.")
    _inside(course, body.period_start, body.period_end, "periodStart")
    weekday, start, end = f"DW.{body.weekday.value}", _tm(body.start_time), _tm(body.end_time)
    period = (_ymd(body.period_start), _ymd(body.period_end))
    same = select(TB_CORS_SCHDL.c.CORS_SCHDL_SN).where(
        TB_CORS_SCHDL.c.OPER_BNDL_SN == admin.bundle_sn,
        TB_CORS_SCHDL.c.CORS_SN == int(course.CORS_SN),
        TB_CORS_SCHDL.c.DOW_CD == weekday,
        TB_CORS_SCHDL.c.BGNG_TM == start,
        TB_CORS_SCHDL.c.FCLT_SN == room.FCLT_SN,
        TB_CORS_SCHDL.c.APLCN_BGNG_YMD == period[0],
    )
    if except_schedule is not None:
        same = same.where(TB_CORS_SCHDL.c.CORS_SCHDL_SN != except_schedule)
    if db.execute(same).first() is not None:
        raise _fail("weekday", "같은 시설·요일·시작 시각·적용 시작일의 일정이 이미 있습니다.")
    message = _regular_conflict(
        db,
        admin.bundle_sn,
        room,
        weekday,
        start,
        end,
        period,
        own_course=int(course.CORS_SN),
        except_schedule=except_schedule,
    ) or _makeup_conflict_in_period(
        db, admin.bundle_sn, room, weekday, start, end, period, int(course.CORS_SN)
    )
    if message is not None:
        raise _fail("facilityId", message)


# --- 일정 ---------------------------------------------------------------------------------------


def create_schedule(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    course_id: str,
    body: ScheduleWrite,
    idem_key: str,
) -> Schedule:
    course = _writable(db, admin, now, course_id)
    room = _room(db, admin.bundle_sn, body.facility_id)
    mark = _marker(idem_key, course_id, body)
    prior = _replayed(db, admin, "SCHDL_CREATE", mark)
    if prior is not None:
        return _schedule(
            db.execute(
                _schedule_query(admin.bundle_sn, int(course.CORS_SN)).where(
                    TB_CORS_SCHDL.c.CORS_SCHDL_SN == prior
                )
            ).one()
        )
    _check_schedule(db, admin, course, room, body, except_schedule=None)
    sn = int(
        db.execute(
            TB_CORS_SCHDL.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                CORS_SN=int(course.CORS_SN),
                FCLT_SN=int(room.FCLT_SN),
                DOW_CD=f"DW.{body.weekday.value}",
                BGNG_TM=_tm(body.start_time),
                END_TM=_tm(body.end_time),
                APLCN_BGNG_YMD=_ymd(body.period_start),
                APLCN_END_YMD=_ymd(body.period_end),
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_CORS_SCHDL.c.CORS_SCHDL_SN)
        ).scalar_one()
    )
    _audit(db, admin, "SCHDL_CREATE", "TB_CORS_SCHDL", sn, request_id, now, f"강좌 {course_id} {mark}")
    return _schedule(
        db.execute(
            _schedule_query(admin.bundle_sn, int(course.CORS_SN)).where(TB_CORS_SCHDL.c.CORS_SCHDL_SN == sn)
        ).one()
    )


def _own_schedule(db: Session, bundle_sn: int, course_sn: int, schedule_id: str) -> Any:
    row = db.execute(
        _schedule_query(bundle_sn, course_sn).where(TB_CORS_SCHDL.c.CORS_SCHDL_SN == int(schedule_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def update_schedule(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    course_id: str,
    schedule_id: str,
    body: ScheduleUpdate,
) -> Schedule:
    course = _writable(db, admin, now, course_id)
    current = _own_schedule(db, admin.bundle_sn, int(course.CORS_SN), schedule_id)
    room = _room(db, admin.bundle_sn, body.facility_id)
    if body.version != int(current.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    has_changes = db.execute(
        select(func.count()).where(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_SN == current.CORS_SCHDL_SN)
    ).scalar_one()
    if int(has_changes) and (
        f"DW.{body.weekday.value}" != current.DOW_CD
        or _ymd(body.period_start) != current.APLCN_BGNG_YMD
        or _ymd(body.period_end) != current.APLCN_END_YMD
    ):
        raise _fail(
            "weekday",
            "휴강·보강이 걸린 일정은 요일과 적용 기간을 바꿀 수 없습니다. 먼저 휴강·보강을 지워 주세요.",
        )
    _check_schedule(db, admin, course, room, body, except_schedule=int(current.CORS_SCHDL_SN))
    update_versioned(
        db,
        TB_CORS_SCHDL,
        {
            "OPER_BNDL_SN": admin.bundle_sn,
            "CORS_SN": int(course.CORS_SN),
            "CORS_SCHDL_SN": int(current.CORS_SCHDL_SN),
        },
        body.version,
        {
            "FCLT_SN": int(room.FCLT_SN),
            "DOW_CD": f"DW.{body.weekday.value}",
            "BGNG_TM": _tm(body.start_time),
            "END_TM": _tm(body.end_time),
            "APLCN_BGNG_YMD": _ymd(body.period_start),
            "APLCN_END_YMD": _ymd(body.period_end),
        },
    )
    _audit(
        db,
        admin,
        "SCHDL_UPDATE",
        "TB_CORS_SCHDL",
        int(current.CORS_SCHDL_SN),
        request_id,
        now,
        f"강좌 {course_id} 일정 수정",
    )
    return _schedule(_own_schedule(db, admin.bundle_sn, int(course.CORS_SN), schedule_id))


def delete_schedule(
    db: Session, admin: Admin, *, now: datetime, request_id: str, course_id: str, schedule_id: str
) -> None:
    course = _writable(db, admin, now, course_id)
    current = _own_schedule(db, admin.bundle_sn, int(course.CORS_SN), schedule_id)
    sn = int(current.CORS_SCHDL_SN)
    if int(db.execute(select(func.count()).where(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_SN == sn)).scalar_one()):
        raise ApiError(
            ErrorCode.CONFLICT_STATE, "휴강·보강이 걸려 있어 지울 수 없습니다. 먼저 휴강·보강을 지워 주세요."
        )
    if int(db.execute(select(func.count()).where(TB_CORS_ATND.c.CORS_SCHDL_SN == sn)).scalar_one()):
        raise ApiError(ErrorCode.CONFLICT_STATE, "출석 기록이 있어 지울 수 없습니다.")
    remaining = int(
        db.execute(
            select(func.count()).where(
                TB_CORS_SCHDL.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_CORS_SCHDL.c.CORS_SN == int(course.CORS_SN),
            )
        ).scalar_one()
    )
    if course.CORS_STTS_CD != "CS.DRAFT" and remaining <= 1:
        raise _fail("schedule", "공개한 강좌는 일정이 한 건 이상 있어야 합니다.")
    db.execute(delete(TB_CORS_SCHDL).where(TB_CORS_SCHDL.c.CORS_SCHDL_SN == sn))
    before = json.dumps(
        {
            "weekday": str(current.DOW_CD),
            "time": f"{_clock(str(current.BGNG_TM))}~{_clock(str(current.END_TM))}",
            "facility": int(current.FCLT_SN),
            "period": f"{current.APLCN_BGNG_YMD}~{current.APLCN_END_YMD}",
        },
        ensure_ascii=False,
    )
    _audit(
        db,
        admin,
        "SCHDL_DELETE",
        "TB_CORS_SCHDL",
        sn,
        request_id,
        now,
        f"강좌 {course_id} 일정 삭제 {before}",
    )


# --- 휴강·보강 ----------------------------------------------------------------------------------


def _session_schedule(db: Session, bundle_sn: int, course_sn: int, original: date) -> Any:
    """원수업일이 정규 일정의 요일·적용 기간에 맞는 일정(SCH-01)."""
    day = _ymd(original)
    row = db.execute(
        select(TB_CORS_SCHDL).where(
            TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL.c.CORS_SN == course_sn,
            TB_CORS_SCHDL.c.DOW_CD == _day_code(original),
            TB_CORS_SCHDL.c.APLCN_BGNG_YMD <= day,
            TB_CORS_SCHDL.c.APLCN_END_YMD >= day,
        )
    ).first()
    if row is None:
        raise _fail("originalDate", "원수업일이 이 강좌의 정규 일정(요일·적용 기간)에 맞지 않습니다.")
    return row


def _makeup_conflict(
    db: Session, bundle_sn: int, room: Any, day: date, start: str, end: str, *, replaced: int | None
) -> str | None:
    """그 날짜·시설·시간에 정규 수업이나 다른 보강이 있는가. 휴강·대체된 원수업은 점유에서 뺀다(SCH-03).

    replaced는 이 보강이 같은 날짜에 대체하는 원수업의 일정 번호다(다른 날로 옮기는 보강이면 None).
    """
    ymd = _ymd(day)
    cancelled = select(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_SN).where(
        TB_CORS_SCHDL_CHG.c.ORGNL_LCTR_YMD == ymd, TB_CORS_SCHDL_CHG.c.APLCN_YN == "Y"
    )
    query = (
        select(TB_CORS.c.CORS_NM, TB_CORS_SCHDL.c.BGNG_TM, TB_CORS_SCHDL.c.END_TM)
        .select_from(TB_CORS_SCHDL.join(TB_CORS, TB_CORS.c.CORS_SN == TB_CORS_SCHDL.c.CORS_SN))
        .where(
            TB_CORS_SCHDL.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL.c.FCLT_SN == room.FCLT_SN,
            TB_CORS_SCHDL.c.DOW_CD == _day_code(day),
            TB_CORS_SCHDL.c.APLCN_BGNG_YMD <= ymd,
            TB_CORS_SCHDL.c.APLCN_END_YMD >= ymd,
            _overlaps(start, end, TB_CORS_SCHDL.c.BGNG_TM, TB_CORS_SCHDL.c.END_TM),
            TB_CORS_SCHDL.c.CORS_SCHDL_SN.not_in(cancelled),
        )
        .limit(1)
    )
    if replaced is not None:
        query = query.where(TB_CORS_SCHDL.c.CORS_SCHDL_SN != replaced)
    regular = db.execute(query).first()
    if regular is not None:
        return f"{room.FCLT_NM} {ymd[:4]}-{ymd[4:6]}-{ymd[6:]} {_clock(str(regular.BGNG_TM))}~{_clock(str(regular.END_TM))}에 {regular.CORS_NM}이(가) 있습니다."
    other = db.execute(
        select(TB_CORS.c.CORS_NM, TB_CORS_SCHDL_CHG.c.CHG_BGNG_TM, TB_CORS_SCHDL_CHG.c.CHG_END_TM)
        .select_from(TB_CORS_SCHDL_CHG.join(TB_CORS, TB_CORS.c.CORS_SN == TB_CORS_SCHDL_CHG.c.CORS_SN))
        .where(
            TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_SCHDL_CHG.c.CHG_TYPE_CD == "SC.MAKEUP",
            TB_CORS_SCHDL_CHG.c.APLCN_YN == "Y",
            TB_CORS_SCHDL_CHG.c.CHG_FCLT_SN == room.FCLT_SN,
            TB_CORS_SCHDL_CHG.c.CHG_LCTR_YMD == ymd,
            _overlaps(start, end, TB_CORS_SCHDL_CHG.c.CHG_BGNG_TM, TB_CORS_SCHDL_CHG.c.CHG_END_TM),
        )
        .limit(1)
    ).first()
    if other is not None:
        return f"{room.FCLT_NM} {ymd[:4]}-{ymd[4:6]}-{ymd[6:]} {_clock(str(other.CHG_BGNG_TM))}~{_clock(str(other.CHG_END_TM))}에 {other.CORS_NM}의 보강이 있습니다."
    return None


def create_change(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    course_id: str,
    body: ScheduleChangeWrite,
    idem_key: str,
) -> ScheduleChange:
    course = _writable(db, admin, now, course_id)
    course_sn = int(course.CORS_SN)
    makeup = body.kind is ScheduleChangeKind.MAKEUP
    if makeup:
        missing = [
            name
            for name, value in (
                ("originalDate", body.original_date),
                ("facilityId", body.facility_id),
                ("startTime", body.start_time),
                ("endTime", body.end_time),
            )
            if value is None
        ]
        if missing:
            raise ApiError(
                ErrorCode.RULE_REJECTED,
                "보강은 원수업일·시설·시간을 모두 입력해야 합니다.",
                fields={name: "보강은 필수 항목입니다." for name in missing},
            )
        original = body.original_date
    else:
        extra = [
            name
            for name, value in (
                ("facilityId", body.facility_id),
                ("startTime", body.start_time),
                ("endTime", body.end_time),
            )
            if value is not None
        ]
        if extra or (body.original_date is not None and body.original_date != body.class_date):
            raise ApiError(
                ErrorCode.RULE_REJECTED,
                "휴강은 수업일과 사유만 입력합니다.",
                fields={name: "휴강에서는 입력하지 않습니다." for name in extra or ["originalDate"]},
            )
        original = body.class_date
    assert original is not None
    room = _room(db, admin.bundle_sn, body.facility_id) if makeup and body.facility_id else None
    mark = _marker(idem_key, course_id, body)
    prior = _replayed(db, admin, "SCHDL_CHG_CREATE", mark)
    if prior is not None:
        return _change(_one_change(db, admin.bundle_sn, prior))
    schedule = _session_schedule(db, admin.bundle_sn, course_sn, original)
    taken = db.execute(
        select(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN).where(
            TB_CORS_SCHDL_CHG.c.CORS_SCHDL_SN == schedule.CORS_SCHDL_SN,
            TB_CORS_SCHDL_CHG.c.ORGNL_LCTR_YMD == _ymd(original),
        )
    ).first()
    if taken is not None:
        raise _fail("classDate", "이 수업일에는 이미 휴강 또는 보강이 등록되어 있습니다.")
    values: dict[str, Any] = {}
    if makeup:
        assert room is not None and body.start_time and body.end_time
        _times(body.start_time, body.end_time)
        _inside(course, body.class_date, body.class_date, "classDate")
        start, end = _tm(body.start_time), _tm(body.end_time)
        replaced = int(schedule.CORS_SCHDL_SN) if body.class_date == original else None
        message = _makeup_conflict(db, admin.bundle_sn, room, body.class_date, start, end, replaced=replaced)
        if message is not None:
            raise _fail("facilityId", message)
        values = {
            "CHG_LCTR_YMD": _ymd(body.class_date),
            "CHG_BGNG_TM": start,
            "CHG_END_TM": end,
            "CHG_FCLT_SN": int(room.FCLT_SN),
        }
    sn = int(
        db.execute(
            TB_CORS_SCHDL_CHG.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                CORS_SN=course_sn,
                CORS_SCHDL_SN=int(schedule.CORS_SCHDL_SN),
                ORGNL_LCTR_YMD=_ymd(original),
                CHG_TYPE_CD=CHANGE_CODE[body.kind],
                CHG_RSN=body.reason.strip(),
                REG_MNGR_SN=admin.admin_sn,
                APLCN_YN="Y",
                REG_DT=now,
                RCRD_VER=1,
                **values,
            )
            .returning(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN)
        ).scalar_one()
    )
    _audit(
        db, admin, "SCHDL_CHG_CREATE", "TB_CORS_SCHDL_CHG", sn, request_id, now, f"{body.kind.value} {mark}"
    )
    return _change(_one_change(db, admin.bundle_sn, sn))


def _one_change(db: Session, bundle_sn: int, change_sn: int) -> Any:
    return db.execute(
        select(TB_CORS_SCHDL_CHG, ROOM.c.FCLT_NM.label("ROOM_NM"), CENTER.c.FCLT_NM.label("CENTER_NM"))
        .select_from(
            TB_CORS_SCHDL_CHG.outerjoin(
                ROOM,
                and_(
                    ROOM.c.OPER_BNDL_SN == TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN,
                    ROOM.c.FCLT_SN == TB_CORS_SCHDL_CHG.c.CHG_FCLT_SN,
                ),
            ).outerjoin(CENTER, CENTER.c.FCLT_SN == ROOM.c.UP_FCLT_SN)
        )
        .where(
            TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == bundle_sn, TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN == change_sn
        )
    ).one()


def delete_change(
    db: Session, admin: Admin, *, now: datetime, request_id: str, course_id: str, change_id: str
) -> None:
    """휴강·보강을 지운다. 지우기 전의 값은 작업이력에 보존한다(SCH-02). 출석 기록이 걸린 보강은 지울 수 없다."""
    course = _writable(db, admin, now, course_id)
    row = db.execute(
        select(TB_CORS_SCHDL_CHG).where(
            TB_CORS_SCHDL_CHG.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_CORS_SCHDL_CHG.c.CORS_SN == int(course.CORS_SN),
            TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN == int(change_id),
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    sn = int(row.CORS_SCHDL_CHG_SN)
    if int(db.execute(select(func.count()).where(TB_CORS_ATND.c.CORS_SCHDL_CHG_SN == sn)).scalar_one()):
        raise ApiError(ErrorCode.CONFLICT_STATE, "출석 기록이 있어 지울 수 없습니다.")
    db.execute(delete(TB_CORS_SCHDL_CHG).where(TB_CORS_SCHDL_CHG.c.CORS_SCHDL_CHG_SN == sn))
    before = json.dumps(
        {
            "type": str(row.CHG_TYPE_CD),
            "original": str(row.ORGNL_LCTR_YMD),
            "date": row.CHG_LCTR_YMD,
            "time": None
            if row.CHG_BGNG_TM is None
            else f"{_clock(str(row.CHG_BGNG_TM))}~{_clock(str(row.CHG_END_TM))}",
            "facility": None if row.CHG_FCLT_SN is None else int(row.CHG_FCLT_SN),
        },
        ensure_ascii=False,
    )
    _audit(
        db,
        admin,
        "SCHDL_CHG_DELETE",
        "TB_CORS_SCHDL_CHG",
        sn,
        request_id,
        now,
        f"강좌 {course_id} 삭제 {before}",
    )
