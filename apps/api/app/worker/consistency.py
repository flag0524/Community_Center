# 일일 정합성 점검: 오래 확정되지 않은 결제·환불·문자·파일을 원자료에서 찾아 운영 업무로 올린다(TDD 7.5, ADR-050)
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.tables import TB_FILE, TB_RFND, TB_SMS_DMND, TB_SMS_TRGT, TB_STLM

log = logging.getLogger("app.worker")

# 장기 판정 기준은 문서가 정하지 않아 보수적으로 둔 값이다(개정 요청 R30). 결제·환불은 담당자가 다음 영업일까지
# 대사해야 하므로 하루, 문자·파일은 자동 처리 주기가 짧아 한 시간이다.
PAYMENT_AGE = timedelta(hours=24)
REFUND_AGE = timedelta(hours=24)
SMS_AGE = timedelta(hours=1)
FILE_AGE = timedelta(hours=1)
PER_KIND = 200  # 종류마다 목록에 담는 최대 건수. 넘치면 건수는 정확히 세고 목록만 줄인다

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class StaleItem:
    kind: str  # PAYMENT_PENDING / REFUND_PENDING / SMS_UNKNOWN / FILE_PENDING
    key: int
    since: datetime


@dataclass(frozen=True)
class StaleReport:
    items: list[StaleItem]
    counts: dict[str, int]  # 종류별 전체 건수(목록이 잘려도 정확하다)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _collect(
    db: Session, kind: str, key_column: Any, since_column: Any, where: tuple[Any, ...]
) -> tuple[list[StaleItem], int]:
    count = int(db.execute(select(func.count()).where(*where)).scalar_one())
    rows = db.execute(
        select(key_column, since_column).where(*where).order_by(since_column).limit(PER_KIND)
    ).all()
    return [StaleItem(kind, int(r[0]), r[1]) for r in rows], count


def find_stale(db: Session, bundle_sn: int, now: datetime) -> StaleReport:
    """오래 확정되지 않은 항목. 대시보드의 확인할 업무와 일일 점검이 같은 기준을 쓴다. 조회만 하고 바꾸지 않는다."""
    since_payment = func.coalesce(TB_STLM.c.MDFCN_DT, TB_STLM.c.STLM_DMND_DT)
    kinds = [
        (
            "PAYMENT_PENDING",
            TB_STLM.c.STLM_SN,
            since_payment,
            (
                TB_STLM.c.OPER_BNDL_SN == bundle_sn,
                TB_STLM.c.STLM_STTS_CD == "PS.PENDING",
                since_payment <= now - PAYMENT_AGE,
            ),
        ),
        (
            "REFUND_PENDING",
            TB_RFND.c.RFND_SN,
            TB_RFND.c.IMPL_DMND_DT,
            (
                TB_RFND.c.OPER_BNDL_SN == bundle_sn,
                TB_RFND.c.RFND_STTS_CD == "RS.PENDING",
                TB_RFND.c.IMPL_DMND_DT <= now - REFUND_AGE,
            ),
        ),
        (
            "SMS_UNKNOWN",
            TB_SMS_TRGT.c.SMS_TRGT_SN,
            func.coalesce(TB_SMS_TRGT.c.MDFCN_DT, TB_SMS_TRGT.c.REG_DT),
            (
                TB_SMS_TRGT.c.OPER_BNDL_SN == bundle_sn,
                TB_SMS_TRGT.c.TRGT_STTS_CD == "SS.UNKNOWN",
                func.coalesce(TB_SMS_TRGT.c.MDFCN_DT, TB_SMS_TRGT.c.REG_DT) <= now - SMS_AGE,
                # OTP 문자는 사용자가 다시 요청하므로 점검 대상이 아니다
                TB_SMS_TRGT.c.SMS_DMND_SN.in_(
                    select(TB_SMS_DMND.c.SMS_DMND_SN).where(
                        TB_SMS_DMND.c.OPER_BNDL_SN == bundle_sn,
                        or_(TB_SMS_DMND.c.SRC_EVENT_ID.is_(None), ~TB_SMS_DMND.c.SRC_EVENT_ID.like("CERT:%")),
                    )
                ),
            ),
        ),
        (
            "FILE_PENDING",
            TB_FILE.c.FILE_SN,
            TB_FILE.c.REG_DT,
            (
                TB_FILE.c.OPER_BNDL_SN == bundle_sn,
                TB_FILE.c.FILE_STTS_CD == "FS.PENDING",
                TB_FILE.c.REG_DT <= now - FILE_AGE,
            ),
        ),
    ]
    items: list[StaleItem] = []
    counts: dict[str, int] = {}
    for kind, key, since, where in kinds:
        found, count = _collect(db, kind, key, since, where)
        items += found
        counts[kind] = count
    return StaleReport(items, counts)


def consistency_check(db: Session, bundle_sn: int, clock: Clock) -> int:
    """점검 결과를 로그와 상태 파일(처리 건수)에 남긴다. 로그에는 종류별 건수만 담고 개인정보는 담지 않는다."""
    report = find_stale(db, bundle_sn, clock())
    db.rollback()
    if report.total:
        log.warning("정합성 점검: 오래 확정되지 않은 항목 %s", report.counts)
    return report.total
