# DB의 시간대 없는 UTC 시각을 응답용 시간대 있는 시각으로 바꾼다
from datetime import UTC, datetime


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)
