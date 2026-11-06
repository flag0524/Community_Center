# 관리자 대시보드·통계 API의 응답 모델. 수치는 원자료 집계이고 자료 없음과 0을 구분한다
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, Won
from app.domain.admin.stats_types import DashboardTaskKind
from app.domain.payment.types import PaymentMethod


class StatsBasis(ApiModel):
    """모든 통계가 함께 싣는 집계 기준."""

    basis_at: AwareDatetime = Field(description="집계한 시각")
    cycle_id: SerialId | None = Field(description="집계한 교육기수. 비우면 전체")
    from_date: date | None
    to_date: date | None


class DashboardSummary(ApiModel):
    applications: int = Field(ge=0, description="신청건")
    unique_applicants: int = Field(ge=0, description="고유 신청자")
    confirmed: int = Field(ge=0, description="등록완료")
    seats_held: int = Field(ge=0, description="좌석점유 = 등록완료 + 결제대기 + 승인확인중")
    waiting: int = Field(ge=0, description="대기")
    cancelled: int = Field(ge=0, description="취소")
    net_revenue: Won = Field(description="순수납 = 승인금액 − 완료환불액")


class DashboardTask(ApiModel):
    kind: DashboardTaskKind
    count: int = Field(ge=0)


class DashboardDemand(ApiModel):
    course_id: SerialId
    course_name: str
    effective_demand: int = Field(ge=0, description="좌석점유 + 대기")
    capacity: int = Field(ge=0)


class DashboardRecent(ApiModel):
    at: AwareDatetime
    actor: str = Field(description="처리한 담당자. 자동 처리는 SYSTEM")
    action: str
    target: str


class Dashboard(ApiModel):
    basis: StatsBasis
    summary: DashboardSummary | None = Field(description="신청 자료가 없으면 null이다. 0과 구분한다.")
    tasks: list[DashboardTask]
    demand: list[DashboardDemand]
    recent: list[DashboardRecent]


class DemandRow(ApiModel):
    course_id: SerialId
    course_name: str
    category_name: str = Field(description="분야. 분류가 없는 강좌는 미분류")
    capacity: int = Field(ge=0)
    applications: int = Field(ge=0)
    unique_applicants: int = Field(ge=0)
    confirmed: int = Field(ge=0)
    hold: int = Field(ge=0, description="결제대기")
    payment_unknown: int = Field(ge=0, description="승인확인중")
    waiting: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    seats_held: int = Field(ge=0)
    effective_demand: int = Field(ge=0)
    demand_ratio: float | None = Field(description="유효수요 ÷ 정원. 정원이 0이면 null")


class DemandStats(ApiModel):
    basis: StatsBasis
    rows: list[DemandRow]


class MethodSettlement(ApiModel):
    method: PaymentMethod
    approved: Won
    refunded: Won
    net: Won


class SettlementStats(ApiModel):
    basis: StatsBasis
    approved_amount: Won
    refunded_amount: Won = Field(description="완료된 환불액")
    net_revenue: Won
    unknown_amount: Won = Field(description="결과 확인 중인 금액. 순수납에 넣지 않고 따로 보인다.")
    by_method: list[MethodSettlement]


class AttendanceStatsRow(ApiModel):
    course_id: SerialId
    course_name: str
    instructor_name: str
    present: int = Field(ge=0)
    absent: int = Field(ge=0)
    rate: float | None = Field(description="출석 ÷ (출석 + 결석) × 100. 체크한 건이 없으면 null")


class AttendanceStatsReport(ApiModel):
    basis: StatsBasis
    rows: list[AttendanceStatsRow]


class StatsSource(ApiModel):
    """기관이 제공한 집계자료의 승인 버전. 다른 버전은 합산하지 않는다 (STAT-03)."""

    version: str
    provider: str
    period: str
    basis_date: date | None


class AgeGenderRow(ApiModel):
    band: str = Field(description="자료가 정한 연령 구간 그대로")
    male: int = Field(ge=0)
    female: int = Field(ge=0)
    unknown: int = Field(ge=0, description="성별 미상")


class AgeGenderStats(ApiModel):
    basis: StatsBasis
    source: StatsSource | None = Field(description="승인된 자료가 없으면 null이고 화면은 미제공으로 보인다.")
    rows: list[AgeGenderRow]


class SatisfactionOption(ApiModel):
    label: str
    count: int = Field(ge=0)


class SatisfactionItem(ApiModel):
    question: str
    answered: int = Field(ge=0)
    average: float | None = Field(description="점수 문항의 평균. 분모가 0이면 null")
    options: list[SatisfactionOption]


class SatisfactionStats(ApiModel):
    basis: StatsBasis
    source: StatsSource | None
    respondents: int | None = Field(ge=0, description="응답자 수. 자료가 없으면 null")
    items: list[SatisfactionItem]
