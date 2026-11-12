# 주기 작업을 정해진 간격으로 돌리는 실행기. 작업 하나의 오류가 다른 작업과 워커를 멈추지 않게 한다(TDD 7)
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.pg.base import PaymentGateway
from app.adapters.scan.base import FileScanner
from app.adapters.sms.base import SmsSender
from app.core.config import Settings
from app.db.session import open_session
from app.worker import consistency, jobs
from app.worker.status import record_run

log = logging.getLogger("app.worker")


@dataclass(frozen=True)
class Job:
    name: str
    seconds: int  # 주기 작업의 간격(초). 매일 정해진 시각에 도는 작업은 0이다
    run: Callable[[Session], int]
    cron: tuple[int, int] | None = None  # (시, 분) 한국 시각. 있으면 간격 대신 매일 이 시각에 돈다


def build_jobs(
    settings: Settings,
    gateway: PaymentGateway,
    sender: SmsSender,
    scanner: FileScanner,
    bundle_sn: int,
    clock: Callable[[], datetime],
) -> list[Job]:
    """TDD 7의 주기(문자 5초, 파일 검사·만료 10초, 재조회 30초, 점검 매일 03:00)를 따른다. 정리는 이어서 더한다."""
    return [
        Job(
            "sms_dispatch",
            5,
            lambda db: (
                jobs.dispatch_sms(db, settings, sender, bundle_sn, clock)
                + jobs.recheck_sms(db, sender, bundle_sn, clock)
            ),
        ),
        Job("file_scan", 10, lambda db: jobs.scan_files(db, settings, scanner, bundle_sn, clock)),
        Job("expire_payments", 10, lambda db: jobs.expire_payments(db, settings, bundle_sn, clock)),
        Job(
            "recheck_payments", 30, lambda db: jobs.recheck_payments(db, settings, gateway, bundle_sn, clock)
        ),
        Job("recheck_refunds", 30, lambda db: jobs.recheck_refunds(db, gateway, bundle_sn, clock)),
        Job(
            "consistency_check",
            0,
            lambda db: consistency.consistency_check(db, bundle_sn, clock),
            cron=(3, 0),  # TDD 7.5: 매일 03:00
        ),
    ]


def run_guarded(job: Job, engine: Engine, status_file: Path, clock: Callable[[], datetime]) -> None:
    """작업 한 번을 새 세션으로 돌린다. 오류는 기록만 하고 삼킨다(다음 주기에 다시 한다)."""
    session = open_session(engine)
    try:
        handled = job.run(session)
        record_run(status_file, job.name, ok=True, now=clock(), handled=handled)
        if handled:
            log.info("작업 %s 처리 %d건", job.name, handled)
    except Exception as error:
        session.rollback()
        log.exception("작업 %s 실패", job.name)  # 로그에는 예외 종류와 위치만 남는다(개인정보는 담지 않는다)
        record_run(status_file, job.name, ok=False, now=clock(), error=type(error).__name__)
    finally:
        session.close()
