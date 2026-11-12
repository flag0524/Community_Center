# 모든 API 모델이 공유하는 camelCase 기반 클래스, 일련번호·금액 타입, 목록 응답 틀
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """요청·응답 공통 기반. JSON 필드는 camelCase이고 요청에 정의되지 않은 필드는 거절한다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# 일련번호는 NUMERIC(22,0)이라 JS Number로 줄일 수 없다. API에서는 항상 숫자 문자열이다(스키마 C05).
SerialId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{1,22}$"),
    Field(
        description="일련번호. 22자리까지의 숫자 문자열이며 산술·정렬에 쓰지 않는다.",
        json_schema_extra={"x-serial": True},
    ),
]

# 공통코드는 12자 이하 문자열이 영구 식별자다. 문의 분류(IQ)는 일련번호가 없어 코드 자체를 번호로 쓴다.
CategoryCode = Annotated[
    str,
    StringConstraints(pattern=r"^IQ\.[A-Z0-9_]{1,9}$"),
    Field(description="문의 분류 코드(IQ). 예 IQ.COURSE", json_schema_extra={"x-code": "IQ"}),
]

# 금액은 원 단위 정수이고 상한은 스키마 검증 규칙(수강료 10,000,000원)을 따른다.
Won = Annotated[int, Field(ge=0, le=10_000_000, description="원 단위 금액")]

ClockTime = Annotated[
    str,
    StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$"),
    Field(description="HH:MM 형식의 시각"),
]


class ServerTimed(ApiModel):
    """결제기한 카운트다운처럼 서버 시각 기준이 필요한 응답에 붙는다."""

    server_now: AwareDatetime = Field(description="응답을 만든 서버 시각. 화면 카운트다운의 기준이다.")


class PageCriteria(ApiModel):
    """목록에 적용된 기준 분기와 기준 시각(FN-012)."""

    basis_at: AwareDatetime
    description: str | None = None


class Page[T](ApiModel):
    items: list[T]
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    criteria: PageCriteria
