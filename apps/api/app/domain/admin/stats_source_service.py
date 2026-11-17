# 연령·성별과 만족도 통계. 기관이 제공해 승인된 집계자료의 최신 버전만 그대로 보이고 다른 버전은 합산하지 않으며 자료가 없으면 0이 아니라 미제공이다(FN-060, FN-067, STAT-01~04, DGSTFN-01~03, ADR-072)
from datetime import date, datetime
from typing import Any

from fastapi import Response
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import (
    TB_CORS,
    TB_CORS_DGSTFN_QITEM,
    TB_CORS_DGSTFN_SRC,
    TB_CORS_DGSTFN_TOT,
    TB_MBR_STATS_SRC,
    TB_MBR_STATS_TOT,
)
from app.domain.admin.csv_export import audit_export, build_csv, csv_response
from app.domain.admin.stats_schemas import (
    AgeGenderRow,
    AgeGenderStats,
    SatisfactionItem,
    SatisfactionOption,
    SatisfactionStats,
    StatsBasis,
    StatsSource,
)
from app.domain.admin.stats_service import with_note
from app.domain.admin.types import AdminAuthority as AU

AGE_APPROVED = "SA.APPROVE"  # 연령·성별 자료의 승인(자료 승인 상태 코드집합)
SATISFACTION_APPROVED = "SA.APPROVED"  # 만족도 자료의 승인
SCORE_TYPE = "DQ.SCORE"
# 원자료의 성별 분류 이름을 계약의 세 열로 옮긴다. 합계·전체 분류는 열에 넣지 않고 합산도 하지 않는다(STAT-01)
MALE = frozenset({"남", "남성", "남자", "M", "MALE"})
FEMALE = frozenset({"여", "여성", "여자", "F", "FEMALE"})
TOTALS = frozenset({"합계", "전체", "계", "소계", "TOTAL", "ALL"})


def _ymd(value: Any) -> date | None:
    text = None if value is None else str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _period(src: Any) -> str:
    begin, end = _ymd(src.BGNG_YMD), _ymd(src.END_YMD)
    return f"{begin.isoformat() if begin else ''}~{end.isoformat() if end else ''}"


def _source(src: Any, basis_date: date | None) -> StatsSource:
    return StatsSource(
        version=str(src.SRC_VER), provider=str(src.SRC_NM), period=_period(src), basis_date=basis_date
    )


def _basis(now: datetime, src: Any | None) -> StatsBasis:
    return StatsBasis(
        basis_at=utc(now),
        cycle_id=None,
        from_date=None if src is None else _ymd(src.BGNG_YMD),
        to_date=None if src is None else _ymd(src.END_YMD),
    )


# --- 연령·성별 ----------------------------------------------------------------------------------


def _latest_age_source(db: Session, bundle_sn: int, scope: Scope) -> Any | None:
    """내 범위가 다루는 승인된 자료 중 가장 나중에 승인한 한 버전. 동이 정해진 자료는 그 동을 다루는 담당자만 본다."""
    query: Select[Any] = select(TB_MBR_STATS_SRC).where(
        TB_MBR_STATS_SRC.c.OPER_BNDL_SN == bundle_sn,
        TB_MBR_STATS_SRC.c.APRV_STTS_CD == AGE_APPROVED,
        TB_MBR_STATS_SRC.c.APRV_MNGR_SN.is_not(None),
        TB_MBR_STATS_SRC.c.APRV_DT.is_not(None),
    )
    if not scope.whole:
        query = query.where(TB_MBR_STATS_SRC.c.DONG_SN.in_(scope.dongs))
    return db.execute(
        query.order_by(TB_MBR_STATS_SRC.c.APRV_DT.desc(), TB_MBR_STATS_SRC.c.MBR_STATS_SRC_SN.desc()).limit(1)
    ).first()


def _age_rows(db: Session, src: Any) -> list[AgeGenderRow]:
    bands: dict[str, dict[str, int]] = {}
    for row in db.execute(
        select(TB_MBR_STATS_TOT)
        .where(TB_MBR_STATS_TOT.c.MBR_STATS_SRC_SN == src.MBR_STATS_SRC_SN)
        .order_by(TB_MBR_STATS_TOT.c.SORT_SEQ, TB_MBR_STATS_TOT.c.MBR_STATS_TOT_SN)
    ):
        name = str(row.GNDR_CLSF_NM or row.GNDR_CLSF_ID).strip()
        key = name.upper()
        if key in TOTALS:
            continue
        column = "male" if key in MALE else "female" if key in FEMALE else "unknown"
        slot = bands.setdefault(str(row.AGE_GROUP_NM), {"male": 0, "female": 0, "unknown": 0})
        slot[column] += int(row.TOT_NOPE)
    return [AgeGenderRow(band=band, **counts) for band, counts in bands.items()]


def get_age_gender(db: Session, admin: Admin, *, now: datetime) -> AgeGenderStats:
    """승인된 최신 자료의 구간·성별을 그대로 준다. 자료가 없으면 source가 null이고 0명으로 대신하지 않는다."""
    scope = permit(db, admin, AU.STAT_R, now)
    src = _latest_age_source(db, admin.bundle_sn, scope)
    if src is None:
        return AgeGenderStats(basis=_basis(now, None), source=None, rows=[])
    return AgeGenderStats(
        basis=_basis(now, src), source=_source(src, _ymd(src.CRTR_YMD)), rows=_age_rows(db, src)
    )


def export_age_gender_csv(db: Session, admin: Admin, *, now: datetime, request_id: str) -> Response:
    """승인된 자료의 버전·기준일을 첫 줄에 넣고 구간·성별을 그대로 담는다. 자료가 없으면 만들지 않는다."""
    stats = get_age_gender(db, admin, now=now)
    if stats.source is None:
        raise ApiError(ErrorCode.RULE_REJECTED, "내려받을 승인된 연령·성별 자료가 없습니다.")
    note = (
        f"# 자료 버전 {stats.source.version}, 출처 {stats.source.provider}, 집계 기간 {stats.source.period}, "
        f"연령 기준일 {stats.source.basis_date or '미상'}, 생성 {utc(now).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    data = with_note(
        note,
        build_csv(
            ["연령구간", "남", "여", "미상"], [[r.band, r.male, r.female, r.unknown] for r in stats.rows]
        ),
    )
    audit_export(
        db, admin, "STATS_AGE_GENDER", len(stats.rows), request_id, now, {"version": stats.source.version}
    )
    return csv_response("연령성별통계.csv", data)


# --- 만족도 -------------------------------------------------------------------------------------


def _latest_satisfaction_source(db: Session, bundle_sn: int, scope: Scope) -> Any | None:
    query: Select[Any] = (
        select(TB_CORS_DGSTFN_SRC)
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_CORS_DGSTFN_SRC.c.CORS_SN),
        )
        .where(
            TB_CORS_DGSTFN_SRC.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS_DGSTFN_SRC.c.APRV_STTS_CD == SATISFACTION_APPROVED,
            TB_CORS_DGSTFN_SRC.c.APRV_MNGR_SN.is_not(None),
            TB_CORS_DGSTFN_SRC.c.APRV_DT.is_not(None),
        )
    )
    if not scope.whole:
        query = query.where(TB_CORS.c.DONG_SN.in_(scope.dongs))
    return db.execute(
        query.order_by(
            TB_CORS_DGSTFN_SRC.c.APRV_DT.desc(), TB_CORS_DGSTFN_SRC.c.CORS_DGSTFN_SRC_SN.desc()
        ).limit(1)
    ).first()


def _items(db: Session, src: Any) -> list[SatisfactionItem]:
    items: list[SatisfactionItem] = []
    questions = db.execute(
        select(TB_CORS_DGSTFN_QITEM)
        .where(TB_CORS_DGSTFN_QITEM.c.CORS_DGSTFN_SRC_SN == src.CORS_DGSTFN_SRC_SN)
        .order_by(TB_CORS_DGSTFN_QITEM.c.SORT_SEQ, TB_CORS_DGSTFN_QITEM.c.CORS_DGSTFN_QITEM_SN)
    ).all()
    for question in questions:
        choices = db.execute(
            select(TB_CORS_DGSTFN_TOT)
            .where(TB_CORS_DGSTFN_TOT.c.CORS_DGSTFN_QITEM_SN == question.CORS_DGSTFN_QITEM_SN)
            .order_by(TB_CORS_DGSTFN_TOT.c.SORT_SEQ, TB_CORS_DGSTFN_TOT.c.CORS_DGSTFN_TOT_SN)
        ).all()
        scored = (
            [c for c in choices if c.SCR is not None]
            if str(question.RSPNS_TYPE_CD).strip() == SCORE_TYPE
            else []
        )
        weight = sum(int(c.RSPNS_NOPE) for c in scored)
        average = (
            None if weight == 0 else round(sum(float(c.SCR) * int(c.RSPNS_NOPE) for c in scored) / weight, 2)
        )
        items.append(
            SatisfactionItem(
                question=str(question.QITEM_NM),
                answered=int(question.RSPNS_NOPE),
                average=average,
                options=[SatisfactionOption(label=str(c.ARTCL_NM), count=int(c.RSPNS_NOPE)) for c in choices],
            )
        )
    return items


def get_satisfaction(db: Session, admin: Admin, *, now: datetime) -> SatisfactionStats:
    """승인된 최신 자료의 문항별 응답 수·분포·평균. 평균은 점수 있는 응답만 분모로 하고 분모가 0이면 산출하지 않는다."""
    scope = permit(db, admin, AU.STAT_R, now)
    row = _latest_satisfaction_source(db, admin.bundle_sn, scope)
    if row is None:
        return SatisfactionStats(basis=_basis(now, None), source=None, respondents=None, items=[])
    return SatisfactionStats(
        basis=_basis(now, row),
        source=_source(row, None),
        respondents=None if row.RSPNS_NOPE is None else int(row.RSPNS_NOPE),
        items=_items(db, row),
    )
