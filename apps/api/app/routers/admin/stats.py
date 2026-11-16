# 관리자 대시보드·통계 라우터. 모두 AU.STAT_R이고 조회 전용이며 CSV는 수요·정산·연령성별만 내보낸다
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import stats_service as service
from app.domain.admin import stats_source_service as source_service
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
CategoryParam = Annotated[str | None, Query(alias="categoryId", pattern=r"^[0-9]{1,22}$")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/dashboard")
def get_dashboard(db: Db, admin: Me, clock: Now, cycle_id: CycleParam = None) -> Dashboard:
    """기수 하나의 접수 현황, 확인할 업무, 강좌별 수요, 최근 작업. 확인할 업무는 권한이 있는 종류만 나온다."""
    return service.get_dashboard(db, admin, now=clock(), cycle_id=cycle_id)


@router.get("/stats/demand", responses=error_responses(ErrorCode.RULE_REJECTED))
def get_demand_stats(
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
    category_id: CategoryParam = None,
) -> DemandStats:
    return service.get_demand(
        db,
        admin,
        now=clock(),
        cycle_id=cycle_id,
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
    )


@router.get("/stats/settlement", responses=error_responses(ErrorCode.RULE_REJECTED))
def get_settlement_stats(
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
) -> SettlementStats:
    return service.get_settlement(
        db, admin, now=clock(), cycle_id=cycle_id, from_date=from_date, to_date=to_date
    )


@router.get("/stats/attendance", responses=error_responses(ErrorCode.RULE_REJECTED))
def get_attendance_stats(
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
) -> AttendanceStatsReport:
    """출석 통계는 CSV로 내보내지 않는다 (FN-068)."""
    return service.get_attendance(
        db, admin, now=clock(), cycle_id=cycle_id, from_date=from_date, to_date=to_date
    )


@router.get("/stats/age-gender")
def get_age_gender_stats(db: Db, admin: Me, clock: Now) -> AgeGenderStats:
    """기관이 제공해 승인된 집계자료의 최신 버전만 보인다."""
    return source_service.get_age_gender(db, admin, now=clock())


@router.get("/stats/satisfaction")
def get_satisfaction_stats(db: Db, admin: Me, clock: Now) -> SatisfactionStats:
    """주민 응답은 받지 않고 내보내기도 없다."""
    return source_service.get_satisfaction(db, admin, now=clock())


CSV_ERRORS = {**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE}


@router.get("/stats/demand/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_demand_stats_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
    category_id: CategoryParam = None,
) -> Response:
    """첫 줄에 집계 조건(기간·기수·분야·집계 기준·생성 시각)을 주석 행으로 넣는다."""
    return service.export_demand_csv(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        cycle_id=cycle_id,
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
    )


@router.get("/stats/settlement/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_settlement_stats_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    cycle_id: CycleParam = None,
    from_date: FromParam = None,
    to_date: ToParam = None,
) -> Response:
    """결제수단별 정산. 확인 중 금액은 순수납과 따로 열을 둔다."""
    return service.export_settlement_csv(
        db,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        cycle_id=cycle_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/stats/age-gender/export.csv", response_class=Response, responses=CSV_ERRORS)
def export_age_gender_stats_csv(request: Request, db: Db, admin: Me, clock: Now) -> Response:
    """승인된 집계자료의 자료 버전·기준일을 주석 행에 넣고 구간·성별을 그대로 담는다."""
    return source_service.export_age_gender_csv(db, admin, now=clock(), request_id=request_id_of(request))
