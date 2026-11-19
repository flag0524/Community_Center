# 워커 진입점. `python -m app.worker`로 자치회마다 하나만 띄운다(ADR-004, 단일 인스턴스)
import logging
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.adapters.pg import build_gateway
from app.adapters.scan import build_scanner
from app.adapters.sms import build_sender
from app.core.config import get_settings
from app.core.times import KST
from app.db.bundle import BundleResolver
from app.db.session import create_db_engine, open_session
from app.worker.runner import build_jobs, run_guarded
from app.worker.status import initialize_status
from app.worker.systemd import notify

WATCHDOG_PING_SECONDS = 15  # 유닛의 WatchdogSec(60초)보다 충분히 짧게 보낸다


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engine = create_db_engine(settings)
    with Session(engine) as session:
        bundle_sn = BundleResolver(settings.site_id).resolve(session)
    status_file = Path(settings.worker_status_file)
    initialize_status(status_file, utc_now())
    scheduler = BlockingScheduler(timezone=UTC)
    for job in build_jobs(
        settings, build_gateway(settings), build_sender(settings), build_scanner(settings), bundle_sn, utc_now
    ):
        # 같은 작업이 겹쳐 돌지 않고(max_instances=1) 밀린 실행은 한 번으로 합친다(coalesce)
        trigger = (
            CronTrigger(hour=job.cron[0], minute=job.cron[1], timezone=KST)
            if job.cron
            else IntervalTrigger(seconds=job.seconds)
        )
        scheduler.add_job(
            run_guarded,
            trigger,
            args=[job, engine, status_file, utc_now],
            id=job.name,
            max_instances=1,
            coalesce=True,
        )
    open_session(engine).close()  # 접속을 미리 확인한다
    # 스케줄러 스레드가 살아 있는 동안만 watchdog 신호가 나가, 스케줄러가 멈추면 systemd가 다시 시작한다
    scheduler.add_job(
        notify,
        IntervalTrigger(seconds=WATCHDOG_PING_SECONDS),
        args=["WATCHDOG=1"],
        id="watchdog",
        max_instances=1,
    )
    notify("READY=1")
    scheduler.start()


if __name__ == "__main__":
    main()
