# 주기 작업을 정해진 간격으로 돌리는 실행기. 작업 하나의 오류가 다른 작업과 워커를 멈추지 않게 한다(TDD 7)
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.pg.base import PaymentGateway
from app.core.config import Settings
from app.db.session import open_session
from app.worker import jobs
from app.worker.status import record_run

log = logging.getLogger("app.worker")


@dataclass(frozen=True)
class Job:
    name: str
    seconds: int
    run: Callable[[Session], int]


def build_jobs(
    settings: Settings, gateway: PaymentGateway, bundle_sn: int, clock: Callable[[], datetime]
) -> list[Job]:
    """TDD 7의 주기(만료 10초, 재조회 30초)를 따른다. 문자 발송 등은 이어서 더한다."""
    return [
        Job("expire_payments", 10, lambda db: jobs.expire_payments(db, settings, bundle_sn, clock)),
        Job(
            "recheck_payments", 30, lambda db: jobs.recheck_payments(db, settings, gateway, bundle_sn, clock)
        ),
        Job("recheck_refunds", 30, lambda db: jobs.recheck_refunds(db, gateway, bundle_sn, clock)),
    ]


def run_guarded(job: Job, engine: Engine, status_file: Path, clock: Callable[[], datetime]) -> None:
    """작업 한 번을 새 세션으로 돌린다. 오류는 기록만 하고 삼킨다(다음 주기에 다시 한다)."""
    session = open_session(engine)
    try:
        handled = job.run(session)
        record_run(status_file, job.name, ok=True, now=clock())
        if handled:
            log.info("작업 %s 처리 %d건", job.name, handled)
    except Exception as error:
        session.rollback()
        log.exception("작업 %s 실패", job.name)  # 로그에는 예외 종류와 위치만 남는다(개인정보는 담지 않는다)
        record_run(status_file, job.name, ok=False, now=clock(), error=type(error).__name__)
    finally:
        session.close()
