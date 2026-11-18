# 연령·성별 집계자료 등록·승인 API의 요청·응답 모델(개인별 행은 받지 않는다, ADR-089)
from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId


class SourceState(StrEnum):
    WAIT = "WAIT"  # SA.WAIT 검토대기
    APPROVED = "APPROVED"  # SA.APPROVE 승인
    REJECTED = "REJECTED"  # SA.REJECT 반려


class SourceRowInput(ApiModel):
    """연령구간과 성별 분류 한 칸의 집계 인원. 분류 이름은 원자료 그대로 쓰고 합계 분류도 그대로 둔다."""

    age_group_id: str = Field(min_length=1, max_length=40, description="연령구간 식별자")
    age_group_name: str = Field(min_length=1, max_length=100, description="연령구간 이름. 원자료 그대로")
    lower_age: int | None = Field(default=None, ge=0, le=150, description="하한 연령. 미상·개방구간은 null")
    upper_age: int | None = Field(default=None, ge=0, le=150, description="상한 연령. 미상·개방구간은 null")
    gender_id: str = Field(min_length=1, max_length=40, description="원자료 성별 분류 식별자")
    gender_name: str = Field(
        min_length=1, max_length=100, description="원자료 성별 분류 이름. 예 남·여·미상·합계"
    )
    count: int = Field(ge=0, le=100_000_000, description="집계 인원. 실제 0명은 0이다")


class SourceCreate(ApiModel):
    provider: str = Field(min_length=1, max_length=200, description="자료를 제공한 기관 이름")
    basis_id: str = Field(min_length=1, max_length=200, description="출처 근거 식별자(문서번호 등)")
    dataset_id: str = Field(
        min_length=1, max_length=128, description="같은 계열의 자료를 묶는 키. 버전은 서버가 정한다"
    )
    period_start: date
    period_end: date
    age_basis_date: date = Field(description="연령을 계산한 기준일")
    dedupe_note: str = Field(min_length=1, max_length=4000, description="모집단과 연령 중복 처리 기준")
    rows: list[SourceRowInput] = Field(min_length=1, max_length=400)


class SourceSummary(ApiModel):
    source_id: SerialId
    dataset_id: str
    version: int
    provider: str
    period_start: date | None
    period_end: date | None
    age_basis_date: date | None
    state: SourceState
    registered_at: AwareDatetime
    decided_at: AwareDatetime | None = Field(description="승인 또는 반려한 시각")
    decided_by: str | None = Field(description="승인 또는 반려한 담당자 이름")


class SourceRowView(ApiModel):
    age_group_id: str
    age_group_name: str
    lower_age: int | None
    upper_age: int | None
    gender_id: str
    gender_name: str
    count: int


class SourceDetail(SourceSummary):
    basis_id: str
    dedupe_note: str
    rows: list[SourceRowView]


class SourceList(ApiModel):
    items: list[SourceSummary]
