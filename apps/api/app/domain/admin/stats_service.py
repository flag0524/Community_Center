# 관리자 대시보드와 수요·정산·출석 통계(AU.STAT_R, 강좌의 운영 동 범위)와 수요·정산 CSV. 원자료에서 그때그때 집계하고 자료 없음과 0을 구분한다(FN-066~068, ADR-069)
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import Response
from sqlalchemy import Select, and_, case, distinct, exists, func, select
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, Scope, permit, scope_for
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_BBS,
    TB_CORS,
    TB_CORS_ATND,
    TB_CORS_ATND_DTL,
    TB_CORS_CLSF,
    TB_EDU_CYCL,
    TB_INSTR,
    TB_INSTR_APLY,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_MNGR,
    TB_PST,
    TB_RFND,
    TB_SMS_TRGT,
    TB_STLM,
)
from app.domain.admin.csv_export import audit_export, build_csv, cell, csv_response
from app.domain.admin.refund_service import kst_start
from app.domain.admin.stats_schemas import (
    AttendanceStatsReport,
    AttendanceStatsRow,
    Dashboard,
    DashboardDemand,
    DashboardRecent,
    DashboardSummary,
    DashboardTask,
    DemandRow,
    DemandStats,
    MethodSettlement,
    SettlementStats,
    StatsBasis,
)
from app.domain.admin.stats_types import DashboardTaskKind
from app.domain.admin.types import AdminAuthority as AU
from app.domain.payment.types import PaymentMethod

UNCATEGORIZED = "미분류"
METHOD_CODE = {PaymentMethod.CARD: "PM.CARD", PaymentMethod.TRANSFER: "PM.TRANSFER"}
DEMAND_TOP = 10  # 대시보드에 보이는 강좌별 수요 개수
RECENT = 10
CONFIRMED = ("ES.CONFIRM", "ES.COMPLETE")


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


@dataclass(frozen=True)
class Filter:
    cycle: int | None
    start: date | None
    end: date | None
    category: int | None = None


def _filter(
    cycle_id: str | None, from_date: date | None, to_date: date | None, category_id: str | None = None
) -> Filter:
    if from_date is not None and to_date is not None and to_date < from_date:
        raise _fail("to", "종료일은 시작일 이후여야 합니다.")
    return Filter(
        None if cycle_id is None else int(cycle_id),
        from_date,
        to_date,
        None if category_id is None else int(category_id),
    )


def _basis(now: datetime, flt: Filter) -> StatsBasis:
    return StatsBasis(
        basis_at=utc(now),
        cycle_id=None if flt.cycle is None else str(flt.cycle),
        from_date=flt.start,
        to_date=flt.end,
    )


def _in_range(column: Any, flt: Filter) -> list[Any]:
    """한국 날짜 구간을 DB의 UTC 시각 구간으로 바꾼 조건. 끝 날짜는 그날 끝까지 포함한다."""
    conditions: list[Any] = []
    if flt.start is not None:
        conditions.append(column >= kst_start(flt.start))
    if flt.end is not None:
        conditions.append(column < kst_start(flt.end + timedelta(days=1)))
    return conditions


def _courses(bundle_sn: int, scope: Scope, flt: Filter) -> Select[Any]:
    """통계에 드는 강좌. 범위 밖 동의 강좌와, 동 범위일 때 동이 없는 강좌는 없다."""
    query = (
        select(
            TB_CORS.c.CORS_SN,
            TB_CORS.c.CORS_NM,
            TB_CORS.c.RCRT_NOPE,
            func.coalesce(TB_CORS_CLSF.c.CORS_CLSF_NM, UNCATEGORIZED).label("CATEGORY_NM"),
        )
        .select_from(TB_CORS)
        .outerjoin(
            TB_CORS_CLSF,
            (TB_CORS_CLSF.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN)
            & (TB_CORS_CLSF.c.CORS_CLSF_SN == TB_CORS.c.CORS_CLSF_SN),
        )
        .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn)
    )
    if not scope.whole:
        query = query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    if flt.cycle is not None:
        query = query.where(TB_CORS.c.EDU_CYCL_SN == flt.cycle)
    if flt.category is not None:
        query = query.where(TB_CORS.c.CORS_CLSF_SN == flt.category)
    return query


def _count(*conditions: Any) -> Any:
    return func.coalesce(func.sum(case((and_(*conditions), 1), else_=0)), 0)


def _unknown() -> Any:
    """결과를 알 수 없는 결제(승인확인중)가 걸린 신청."""
    return exists().where(
        TB_STLM.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
        TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        TB_STLM.c.STLM_STTS_CD == "PS.PENDING",
    )


def _application_counts(db: Session, course_sns: list[int], flt: Filter) -> dict[int, dict[str, int]]:
    if not course_sns:
        return {}
    state = TB_ATNLC_APLY.c.APLY_STTS_CD
    rows = db.execute(
        select(
            TB_ATNLC_APLY.c.CORS_SN,
            func.count().label("applications"),
            func.count(distinct(TB_ATNLC_APLY.c.MBR_SN)).label("unique_applicants"),
            _count(state.in_(CONFIRMED)).label("confirmed"),
            _count(state == "ES.HOLD", ~_unknown()).label("hold"),
            _count(state == "ES.HOLD", _unknown()).label("payment_unknown"),
            _count(state == "ES.WAIT").label("waiting"),
            _count(state.in_(("ES.CANCEL", "ES.EXPIRE"))).label("cancelled"),
        )
        .where(TB_ATNLC_APLY.c.CORS_SN.in_(course_sns), *_in_range(TB_ATNLC_APLY.c.APLY_DT, flt))
        .group_by(TB_ATNLC_APLY.c.CORS_SN)
    ).all()
    return {int(r.CORS_SN): {k: int(getattr(r, k)) for k in r._fields if k != "CORS_SN"} for r in rows}


def _row(course: Any, counts: dict[str, int] | None) -> DemandRow:
    c = counts or {}
    confirmed, hold, unknown, waiting = (
        c.get("confirmed", 0),
        c.get("hold", 0),
        c.get("payment_unknown", 0),
        c.get("waiting", 0),
    )
    capacity = 0 if course.RCRT_NOPE is None else int(course.RCRT_NOPE)
    seats = confirmed + hold + unknown
    effective = seats + waiting
    return DemandRow(
        course_id=str(int(course.CORS_SN)),
        course_name=str(course.CORS_NM),
        category_name=str(course.CATEGORY_NM),
        capacity=capacity,
        applications=c.get("applications", 0),
        unique_applicants=c.get("unique_applicants", 0),
        confirmed=confirmed,
        hold=hold,
        payment_unknown=unknown,
        waiting=waiting,
        cancelled=c.get("cancelled", 0),
        seats_held=seats,
        effective_demand=effective,
        demand_ratio=None if capacity == 0 else round(effective / capacity, 4),
    )


def _demand_rows(db: Session, bundle_sn: int, scope: Scope, flt: Filter) -> list[DemandRow]:
    courses = db.execute(_courses(bundle_sn, scope, flt)).all()
    counts = _application_counts(db, [int(c.CORS_SN) for c in courses], flt)
    rows = [_row(c, counts.get(int(c.CORS_SN))) for c in courses]
    return sorted(rows, key=lambda r: (-r.effective_demand, r.course_name, r.course_id))


def get_demand(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    cycle_id: str | None,
    from_date: date | None,
    to_date: date | None,
    category_id: str | None,
) -> DemandStats:
    scope = permit(db, admin, AU.STAT_R, now)
    flt = _filter(cycle_id, from_date, to_date, category_id)
    return DemandStats(basis=_basis(now, flt), rows=_demand_rows(db, admin.bundle_sn, scope, flt))


# --- 정산 ---------------------------------------------------------------------------------------


def _settlement(db: Session, bundle_sn: int, scope: Scope, flt: Filter) -> dict[str, Any]:
    """승인 금액, 완료된 환불액, 확인 중인 금액을 수단별로 집계한다. 확인 중인 금액은 순수납에 넣지 않는다."""

    def scoped(query: Select[Any]) -> Select[Any]:
        query = query.join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN),
        ).join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
        query = query.where(TB_STLM.c.OPER_BNDL_SN == bundle_sn)
        if not scope.whole:
            query = query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
        if flt.cycle is not None:
            query = query.where(TB_CORS.c.EDU_CYCL_SN == flt.cycle)
        return query

    approved = db.execute(
        scoped(
            select(
                TB_STLM.c.STLM_MNS_CD, func.coalesce(func.sum(TB_STLM.c.STLM_AMT), 0).label("amount")
            ).where(TB_STLM.c.STLM_STTS_CD == "PS.PAID", *_in_range(TB_STLM.c.STLM_APRV_DT, flt))
        ).group_by(TB_STLM.c.STLM_MNS_CD)
    ).all()
    refunded = db.execute(
        scoped(
            select(TB_STLM.c.STLM_MNS_CD, func.coalesce(func.sum(TB_RFND.c.RFND_AMT), 0).label("amount"))
            .select_from(TB_RFND)
            .join(
                TB_STLM,
                (TB_STLM.c.OPER_BNDL_SN == TB_RFND.c.OPER_BNDL_SN) & (TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN),
            )
            .where(TB_RFND.c.RFND_STTS_CD == "RS.DONE", *_in_range(TB_RFND.c.RFND_DT, flt))
        ).group_by(TB_STLM.c.STLM_MNS_CD)
    ).all()
    unknown = db.execute(
        scoped(
            select(func.coalesce(func.sum(TB_STLM.c.STLM_AMT), 0)).where(
                TB_STLM.c.STLM_STTS_CD == "PS.PENDING", *_in_range(TB_STLM.c.STLM_DMND_DT, flt)
            )
        )
    ).scalar_one()
    paid = {str(r.STLM_MNS_CD).strip(): int(r.amount) for r in approved}
    back = {str(r.STLM_MNS_CD).strip(): int(r.amount) for r in refunded}
    return {"approved": paid, "refunded": back, "unknown": int(unknown)}


def get_settlement(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    cycle_id: str | None,
    from_date: date | None,
    to_date: date | None,
) -> SettlementStats:
    scope = permit(db, admin, AU.STAT_R, now)
    flt = _filter(cycle_id, from_date, to_date)
    data = _settlement(db, admin.bundle_sn, scope, flt)
    methods = [
        MethodSettlement(
            method=method,
            approved=data["approved"].get(code, 0),
            refunded=data["refunded"].get(code, 0),
            net=data["approved"].get(code, 0) - data["refunded"].get(code, 0),
        )
        for method, code in METHOD_CODE.items()
    ]
    approved_total = sum(m.approved for m in methods)
    refunded_total = sum(m.refunded for m in methods)
    return SettlementStats(
        basis=_basis(now, flt),
        approved_amount=approved_total,
        refunded_amount=refunded_total,
        net_revenue=approved_total - refunded_total,
        unknown_amount=data["unknown"],
        by_method=methods,
    )


# --- 출석 ---------------------------------------------------------------------------------------


def get_attendance(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    cycle_id: str | None,
    from_date: date | None,
    to_date: date | None,
) -> AttendanceStatsReport:
    """체크한 건만 센다. 미체크는 출석률의 분모에 넣지 않는다(FN-067)."""
    scope = permit(db, admin, AU.STAT_R, now)
    flt = _filter(cycle_id, from_date, to_date)
    sheet = [TB_CORS_ATND.c.DEL_YN == "N"]
    if flt.start is not None:
        sheet.append(TB_CORS_ATND.c.LCTR_YMD >= flt.start.strftime("%Y%m%d"))
    if flt.end is not None:
        sheet.append(TB_CORS_ATND.c.LCTR_YMD <= flt.end.strftime("%Y%m%d"))
    counts = {
        int(r.CORS_SN): (int(r.present), int(r.absent))
        for r in db.execute(
            select(
                TB_CORS_ATND.c.CORS_SN,
                _count(TB_CORS_ATND_DTL.c.ATND_RSLT_CD == "AR.PRESENT").label("present"),
                _count(TB_CORS_ATND_DTL.c.ATND_RSLT_CD == "AR.ABSENT").label("absent"),
            )
            .select_from(TB_CORS_ATND)
            .join(TB_CORS_ATND_DTL, TB_CORS_ATND_DTL.c.ATND_SN == TB_CORS_ATND.c.ATND_SN)
            .where(TB_CORS_ATND.c.OPER_BNDL_SN == admin.bundle_sn, *sheet)
            .group_by(TB_CORS_ATND.c.CORS_SN)
        )
    }
    teaching = (
        select(TB_CORS.c.CORS_SN, TB_CORS.c.CORS_NM, TB_MBR.c.MBR_NM)
        .select_from(TB_CORS)
        .outerjoin(
            TB_INSTR,
            (TB_INSTR.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN) & (TB_INSTR.c.INSTR_SN == TB_CORS.c.INSTR_SN),
        )
        .outerjoin(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_INSTR.c.OPER_BNDL_SN) & (TB_MBR.c.MBR_SN == TB_INSTR.c.MBR_SN),
        )
        .where(TB_CORS.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS.c.CORS_SN.in_(list(counts) or [-1]))
    )
    if not scope.whole:
        teaching = teaching.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    if flt.cycle is not None:
        teaching = teaching.where(TB_CORS.c.EDU_CYCL_SN == flt.cycle)
    rows = []
    for course in db.execute(teaching.order_by(TB_CORS.c.CORS_NM, TB_CORS.c.CORS_SN)):
        present, absent = counts[int(course.CORS_SN)]
        checked = present + absent
        rows.append(
            AttendanceStatsRow(
                course_id=str(int(course.CORS_SN)),
                course_name=str(course.CORS_NM),
                instructor_name="" if course.MBR_NM is None else str(course.MBR_NM),
                present=present,
                absent=absent,
                rate=None if checked == 0 else round(present / checked * 100, 1),
            )
        )
    return AttendanceStatsReport(basis=_basis(now, flt), rows=rows)


# --- 대시보드 -----------------------------------------------------------------------------------


def _latest_cycle(db: Session, bundle_sn: int) -> int | None:
    found = db.execute(
        select(TB_EDU_CYCL.c.EDU_CYCL_SN)
        .where(TB_EDU_CYCL.c.OPER_BNDL_SN == bundle_sn, TB_EDU_CYCL.c.USE_YN == "Y")
        .order_by(
            TB_EDU_CYCL.c.EDU_YR.desc(), TB_EDU_CYCL.c.EDU_CYCL.desc(), TB_EDU_CYCL.c.EDU_CYCL_SN.desc()
        )
        .limit(1)
    ).scalar()
    return None if found is None else int(found)


def get_dashboard(db: Session, admin: Admin, *, now: datetime, cycle_id: str | None) -> Dashboard:
    """기수를 주지 않으면 사용 중인 가장 최근 기수를 본다."""
    scope = permit(db, admin, AU.STAT_R, now)
    flt = _filter(cycle_id, None, None)
    if flt.cycle is None:
        flt = Filter(_latest_cycle(db, admin.bundle_sn), None, None)
    courses = db.execute(_courses(admin.bundle_sn, scope, flt)).all() if flt.cycle is not None else []
    counts = _application_counts(db, [int(c.CORS_SN) for c in courses], flt)
    rows = sorted(
        (_row(c, counts.get(int(c.CORS_SN))) for c in courses),
        key=lambda r: (-r.effective_demand, r.course_name, r.course_id),
    )
    course_sns = [int(c.CORS_SN) for c in courses]
    summary: DashboardSummary | None = None
    if counts:
        state = TB_ATNLC_APLY.c.APLY_STTS_CD
        agg = db.execute(
            select(
                func.count().label("applications"),
                func.count(distinct(TB_ATNLC_APLY.c.MBR_SN)).label("unique"),
                _count(state.in_(CONFIRMED)).label("confirmed"),
                _count(state == "ES.HOLD").label("hold"),
                _count(state == "ES.WAIT").label("waiting"),
                _count(state.in_(("ES.CANCEL", "ES.EXPIRE"))).label("cancelled"),
            ).where(TB_ATNLC_APLY.c.CORS_SN.in_(course_sns))
        ).one()
        money = _settlement(db, admin.bundle_sn, scope, flt)
        net = sum(money["approved"].values()) - sum(money["refunded"].values())
        summary = DashboardSummary(
            applications=int(agg.applications),
            unique_applicants=int(agg.unique),
            confirmed=int(agg.confirmed),
            seats_held=int(agg.confirmed) + int(agg.hold),
            waiting=int(agg.waiting),
            cancelled=int(agg.cancelled),
            net_revenue=net,
        )
    return Dashboard(
        basis=_basis(now, flt),
        summary=summary,
        tasks=_tasks(db, admin, now),
        demand=[
            DashboardDemand(
                course_id=r.course_id,
                course_name=r.course_name,
                effective_demand=r.effective_demand,
                capacity=r.capacity,
            )
            for r in rows[:DEMAND_TOP]
        ],
        recent=_recent(db, admin, now),
    )


def _tasks(db: Session, admin: Admin, now: datetime) -> list[DashboardTask]:
    """담당자가 볼 권한이 있는 종류만이다. 개수는 그 권한의 범위 안에서 센다."""
    out: list[DashboardTask] = []

    def scoped_course(query: Select[Any], authority: AU) -> Select[Any] | None:
        scope = scope_for(db, admin, authority, now)
        if scope.empty():
            return None
        return query if scope.whole else query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))

    def course_join(query: Select[Any], key: Any) -> Select[Any]:
        return query.join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == key.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == key.c.ATNLC_APLY_SN),
        ).join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )

    unknown = scoped_course(
        course_join(
            select(func.count())
            .select_from(TB_STLM)
            .where(TB_STLM.c.OPER_BNDL_SN == admin.bundle_sn, TB_STLM.c.STLM_STTS_CD == "PS.PENDING"),
            TB_STLM,
        ),
        AU.STLM_W,
    )
    if unknown is not None:
        out.append(
            DashboardTask(kind=DashboardTaskKind.PAYMENT_UNKNOWN, count=int(db.execute(unknown).scalar_one()))
        )
    refunds = scoped_course(
        select(func.count())
        .select_from(TB_RFND)
        .join(
            TB_STLM,
            (TB_STLM.c.OPER_BNDL_SN == TB_RFND.c.OPER_BNDL_SN) & (TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN),
        )
        .join(
            TB_ATNLC_APLY,
            (TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_STLM.c.OPER_BNDL_SN)
            & (TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN),
        )
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
        .where(
            TB_RFND.c.OPER_BNDL_SN == admin.bundle_sn, TB_RFND.c.RFND_STTS_CD.in_(("RS.REQUEST", "RS.HOLD"))
        ),
        AU.RFND_A,
    )
    if refunds is not None:
        out.append(
            DashboardTask(kind=DashboardTaskKind.REFUND_REVIEW, count=int(db.execute(refunds).scalar_one()))
        )
    if scope_for(db, admin, AU.INSTR_W, now).whole:
        waiting = db.execute(
            select(func.count()).where(
                TB_INSTR_APLY.c.OPER_BNDL_SN == admin.bundle_sn, TB_INSTR_APLY.c.SRNG_STTS_CD == "IA.WAIT"
            )
        ).scalar_one()
        out.append(DashboardTask(kind=DashboardTaskKind.INSTRUCTOR_REVIEW, count=int(waiting)))
    post_scope = scope_for(db, admin, AU.POST_W, now)
    if not post_scope.empty():
        reply = TB_PST.alias("reply")
        question = (
            select(func.count())
            .select_from(TB_PST)
            .join(
                TB_BBS,
                (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN),
            )
            .where(
                TB_PST.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_BBS.c.BBS_ID == "qna",
                TB_PST.c.DEL_YN == "N",
                TB_PST.c.UP_PST_SN.is_(None),
                ~exists().where(
                    reply.c.UP_PST_SN == TB_PST.c.PST_SN,
                    reply.c.DEL_YN == "N",
                    reply.c.PST_TYPE_CD == "PT.REPLY",
                ),
            )
        )
        if not post_scope.whole:
            question = question.where(TB_PST.c.DONG_SN.in_(post_scope.dongs))
        out.append(
            DashboardTask(kind=DashboardTaskKind.INQUIRY_ANSWER, count=int(db.execute(question).scalar_one()))
        )
    if scope_for(db, admin, AU.SMS_SEND, now).whole:
        failed = db.execute(
            select(func.count()).where(
                TB_SMS_TRGT.c.OPER_BNDL_SN == admin.bundle_sn, TB_SMS_TRGT.c.TRGT_STTS_CD == "SS.FAIL"
            )
        ).scalar_one()
        out.append(DashboardTask(kind=DashboardTaskKind.SMS_FAILED, count=int(failed)))
    return out


def _recent(db: Session, admin: Admin, now: datetime) -> list[DashboardRecent]:
    """작업이력은 묶음 전체 범위의 작업이력 조회 권한(AU.LOG_R)이 있을 때만 보인다."""
    if not scope_for(db, admin, AU.LOG_R, now).whole:
        return []
    rows = db.execute(
        select(
            TB_JOB_HSTRY.c.REG_DT,
            TB_JOB_HSTRY.c.ACTR_TYPE_CD,
            TB_MNGR.c.MNGR_NM,
            TB_JOB_HSTRY.c.JOB_CD,
            TB_JOB_HSTRY.c.TRGT_TBL_NM,
            TB_JOB_HSTRY.c.TRGT_KEY_VL,
        )
        .select_from(TB_JOB_HSTRY)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.ACTR_TYPE_CD.in_(("AK.ADMIN", "AK.SYSTEM")),
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT.desc(), TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
        .limit(RECENT)
    ).all()
    return [
        DashboardRecent(
            at=utc(r.REG_DT),
            actor=str(r.MNGR_NM) if r.ACTR_TYPE_CD == "AK.ADMIN" and r.MNGR_NM else "SYSTEM",
            action=str(r.JOB_CD),
            target=str(r.TRGT_TBL_NM) if r.TRGT_KEY_VL is None else f"{r.TRGT_TBL_NM} {r.TRGT_KEY_VL}",
        )
        for r in rows
    ]


# --- CSV ----------------------------------------------------------------------------------------


def _note(now: datetime, flt: Filter, extra: str = "") -> str:
    period = f"{flt.start or '처음'}~{flt.end or '지금'}"
    cycle = "전체" if flt.cycle is None else str(flt.cycle)
    stamp = utc(now).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"# 집계 조건: 기간 {period}, 기수 {cycle}{extra}, 집계 기준 원자료, 생성 {stamp}"


def with_note(note: str, data: bytes) -> bytes:
    """첫 줄에 집계 조건 주석 행을 넣는다. BOM 바로 뒤에 둔다."""
    line = io.StringIO()
    csv.writer(line, lineterminator="\r\n").writerow([cell(note)])
    return data[:3] + line.getvalue().encode("utf-8") + data[3:]


def export_demand_csv(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    cycle_id: str | None,
    from_date: date | None,
    to_date: date | None,
    category_id: str | None,
) -> Response:
    scope = permit(db, admin, AU.STAT_R, now)
    flt = _filter(cycle_id, from_date, to_date, category_id)
    rows = _demand_rows(db, admin.bundle_sn, scope, flt)
    header = [
        "강좌",
        "분야",
        "정원",
        "신청건",
        "고유 신청자",
        "등록완료",
        "결제대기",
        "승인확인중",
        "대기",
        "취소",
        "좌석점유",
        "유효수요",
        "수요율",
    ]
    body = [
        [
            r.course_name,
            r.category_name,
            r.capacity,
            r.applications,
            r.unique_applicants,
            r.confirmed,
            r.hold,
            r.payment_unknown,
            r.waiting,
            r.cancelled,
            r.seats_held,
            r.effective_demand,
            r.demand_ratio,
        ]
        for r in rows
    ]
    data = with_note(_note(now, flt, f", 분야 {flt.category or '전체'}"), build_csv(header, body))
    audit_export(
        db,
        admin,
        "STATS_DEMAND",
        len(rows),
        request_id,
        now,
        {"cycle": flt.cycle, "from": flt.start, "to": flt.end, "category": flt.category},
    )
    return csv_response("수요통계.csv", data)


def export_settlement_csv(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    cycle_id: str | None,
    from_date: date | None,
    to_date: date | None,
) -> Response:
    """결제수단별 정산. 확인 중인 금액은 순수납과 따로 열을 둔다."""
    stats = get_settlement(db, admin, now=now, cycle_id=cycle_id, from_date=from_date, to_date=to_date)
    flt = _filter(cycle_id, from_date, to_date)
    header = ["결제수단", "승인금액", "완료 환불액", "순수납", "확인 중 금액"]
    body = [[m.method.value, m.approved, m.refunded, m.net, ""] for m in stats.by_method]
    body.append(
        ["합계", stats.approved_amount, stats.refunded_amount, stats.net_revenue, stats.unknown_amount]
    )
    data = with_note(_note(now, flt), build_csv(header, body))
    audit_export(
        db,
        admin,
        "STATS_SETTLEMENT",
        len(body),
        request_id,
        now,
        {"cycle": flt.cycle, "from": flt.start, "to": flt.end},
    )
    return csv_response("정산통계.csv", data)
