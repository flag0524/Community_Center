# 워커 진입점. `python -m app.worker`로 자치회마다 하나만 띄운다(ADR-004, 단일 인스턴스)
import logging
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.adapters.pg import build_gateway
from app.adapters.sms import build_sender
from app.core.config import get_settings
from app.core.times import KST
from app.db.bundle import BundleResolver
from app.db.session import create_db_engine, open_session
from app.worker.runner import build_jobs, run_guarded


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engine = create_db_engine(settings)
    with Session(engine) as session:
        bundle_sn = BundleResolver(settings.site_id).resolve(session)
    status_file = Path(settings.worker_status_file)
    scheduler = BlockingScheduler(timezone=UTC)
    for job in build_jobs(settings, build_gateway(settings), build_sender(settings), bundle_sn, utc_now):
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
    scheduler.start()


if __name__ == "__main__":
    main()
