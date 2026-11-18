# 강좌 만족도 집계자료 등록·승인 API의 요청·응답 모델(개인 응답은 받지 않는다, ADR-091)
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId
from app.domain.admin.stats_input_schemas import SourceState

Score = Decimal


class ResponseType(StrEnum):
    SINGLE = "SINGLE"  # DQ.SINGLE 단일선택
    MULTI = "MULTI"  # DQ.MULTI 복수선택
    SCORE = "SCORE"  # DQ.SCORE 점수


class OptionInput(ApiModel):
    option_id: str = Field(min_length=1, max_length=40, description="원자료 선택 항목 식별자")
    name: str = Field(min_length=1, max_length=200, description="선택 항목 이름. 원자료 그대로")
    count: int = Field(ge=0, le=100_000_000, description="선택한 응답 수")
    score: Score | None = Field(
        default=None,
        max_digits=15,
        decimal_places=6,
        description="점수 문항의 실제 점수. 무응답·점수 없음은 null이고 0점과 다르다",
    )


class QuestionInput(ApiModel):
    question_id: str = Field(min_length=1, max_length=40, description="원자료 문항 식별자")
    name: str = Field(min_length=1, max_length=300)
    type: ResponseType
    respondents: int = Field(ge=0, le=100_000_000, description="문항 유효응답자 수. 전체 응답자 수 이하")
    min_score: Score | None = Field(
        default=None, max_digits=15, decimal_places=6, description="점수 문항의 최소 점수"
    )
    max_score: Score | None = Field(
        default=None, max_digits=15, decimal_places=6, description="점수 문항의 최대 점수"
    )
    criteria: str = Field(
        min_length=1, max_length=4000, description="문항 집계 기준(분모·무응답·복수선택 처리)"
    )
    options: list[OptionInput] = Field(min_length=1, max_length=50)


class SatisfactionSourceCreate(ApiModel):
    course_id: SerialId
    provider: str = Field(min_length=1, max_length=200)
    basis_id: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(
        min_length=1, max_length=128, description="같은 자료의 새 버전은 같은 계열 키로 등록한다"
    )
    period_start: date
    period_end: date
    respondents: int = Field(ge=0, le=100_000_000, description="전체 응답자 수")
    criteria: str = Field(
        min_length=1, max_length=4000, description="모집단·중복 제거·무응답·복수선택·점수 산식·원자료 범위"
    )
    questions: list[QuestionInput] = Field(min_length=1, max_length=100)


class SatisfactionSourceSummary(ApiModel):
    source_id: SerialId
    course_id: SerialId
    course_name: str
    dataset_id: str
    version: int
    provider: str
    period_start: date | None
    period_end: date | None
    respondents: int
    state: SourceState
    registered_at: AwareDatetime
    decided_at: AwareDatetime | None
    decided_by: str | None


class OptionView(ApiModel):
    option_id: str
    name: str
    count: int
    score: Score | None


class QuestionView(ApiModel):
    question_id: str
    name: str
    type: ResponseType
    respondents: int
    min_score: Score | None
    max_score: Score | None
    criteria: str
    options: list[OptionView]


class SatisfactionSourceDetail(SatisfactionSourceSummary):
    basis_id: str
    criteria: str
    questions: list[QuestionView]


class SatisfactionSourceList(ApiModel):
    items: list[SatisfactionSourceSummary]
