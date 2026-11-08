# 관리자 대시보드·통계 라우터. 모두 AU.STAT_R이고 조회 전용이며 CSV 내보내기는 첨부 설계 뒤에 더한다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.stats_schemas import (
    AgeGenderStats,
    AttendanceStatsReport,
    Dashboard,
    DemandStats,
    SatisfactionStats,
    SettlementStats,
)
from app.routers.deps import CSV_RESPONSE, MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(tags=["admin-stats"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

CycleParam = Annotated[str | None, Query(alias="cycleId", pattern=r"^[0-9]{1,22}$")]
FromParam = Annotated[date | None, Query(alias="from")]
ToParam = Annotated[date | None, Query(alias="to")]


@router.get("/dashboard")
def get_dashboard(cycle_id: CycleParam = None) -> Dashboard:
    """기수 하나의 접수 현황, 확인할 업무, 강좌별 수요, 최근 작업. 확인할 업무는 권한이 있는 종류만 나온다."""
    not_implemented()


@router.get("/stats/demand")
def get_demand_stats(
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
    category_id: Annotated[str | None, Query(alias="categoryId", pattern=r"^[0-9]{1,22}$")] = None,
) -> DemandStats:
    not_implemented()


@router.get("/stats/settlement")
def get_settlement_stats(
    cycle_id: CycleParam = None, from_date: FromParam = None, to_date: ToParam = None
) -> SettlementStats:
    not_implemented()


@router.get("/stats/attendance")
def get_attendance_stats(
    cycle_id: CycleParam = None, from_date: FromParam = None, to_date: ToParam = None
) -> AttendanceStatsReport:
    """출석 통계는 CSV로 내보내지 않는다 (FN-068)."""
    not_implemented()


@router.get("/stats/age-gender")
def get_age_gender_stats() -> AgeGenderStats:
    """기관이 제공해 승인된 집계자료의 최신 버전만 보인다."""
    not_implemented()


@router.get("/stats/satisfaction")
def get_satisfaction_stats() -> SatisfactionStats:
    """주민 응답은 받지 않고 내보내기도 없다."""
    not_implemented()


CSV_ERRORS = {**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE}


@router.get("/stats/demand/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_demand_stats_csv(
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
    category_id: Annotated[str | None, Query(alias="categoryId", pattern=r"^[0-9]{1,22}$")] = None,
) -> Response:
    """첫 줄에 집계 조건(기간·기수·분야·집계 기준·생성 시각)을 주석 행으로 넣는다."""
    not_implemented()


@router.get("/stats/settlement/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_settlement_stats_csv(
    cycle_id: CycleParam = None, from_date: FromParam = None, to_date: ToParam = None
) -> Response:
    """결제수단별 정산. 확인 중 금액은 순수납과 따로 열을 둔다."""
    not_implemented()


@router.get("/stats/age-gender/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_age_gender_stats_csv() -> Response:
    """승인된 집계자료의 자료 버전·기준일을 주석 행에 넣고 구간·성별을 그대로 담는다."""
    not_implemented()
