# DB의 시간대 없는 UTC 시각을 응답용 시간대 있는 시각으로 바꾸고, 교육일자 비교용 한국 날짜를 구한다
from datetime import UTC, date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)


def kst_ymd(value: datetime) -> str:
    """DB의 UTC 시각이 한국에서 몇 월 며칠인지 YYYYMMDD로 준다. 교육일자는 운영 지역의 날짜다."""
    return utc(value).astimezone(KST).strftime("%Y%m%d")


def kst_today(value: datetime) -> date:
    """DB의 UTC 시각이 한국에서 몇 월 며칠인지."""
    return utc(value).astimezone(KST).date()
