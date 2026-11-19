# 워커 실행기와 건강 확인이 함께 사용하는 작업 주기와 다음 일일 실행 시각을 정의한다
from datetime import UTC, datetime, timedelta

from app.core.times import KST

INTERVAL_SECONDS = {
    "sms_dispatch": 5,
    "file_scan": 10,
    "expire_payments": 10,
    "recheck_payments": 30,
    "retry_webhooks": 30,
    "recheck_refunds": 30,
}
DAILY_HOURS = {"consistency_check": 3, "retention": 4}


def next_daily_run(now: datetime, hour: int) -> datetime:
    local = now.replace(tzinfo=UTC).astimezone(KST)
    due = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if due <= local:
        due += timedelta(days=1)
    return due.astimezone(UTC)
