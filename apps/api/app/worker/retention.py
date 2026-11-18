# 매일 새벽 기간이 지난 개인정보를 자동으로 파기하는 워커 작업(탈퇴 회원 비식별, 인증번호 요청 삭제, 환불 계좌정보·문자 기록 파기, ADR-086·087)
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.tokens import new_token
from app.domain.admin import retention_service

log = logging.getLogger("app.worker")

Clock = Callable[[], datetime]


def purge_due(db: Session, bundle_sn: int, clock: Clock) -> int:
    """대상 종류마다 행을 잠그고 처리한 뒤 커밋한다. 한 종류가 실패해도 나머지는 계속하고, 실패가 있으면 마지막에 알린다."""
    total = 0
    failed: list[str] = []
    for target in retention_service.AUTO_TARGETS:
        try:
            total += retention_service.purge_target(
                db, bundle_sn, target, now=clock(), request_id=f"worker-{new_token()[:16]}"
            )
            db.commit()
        except Exception as error:
            db.rollback()
            log.warning(
                "자동 정리 실패 target=%s type=%s", target.value, type(error).__name__
            )  # 개인정보는 싣지 않는다
            failed.append(target.value)
    if failed:
        raise RuntimeError("자동 정리 실패: " + ", ".join(failed))
    return total
