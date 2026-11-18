# 문자 발송 결과가 확정되는 순간 문안과 수신번호를 파기하는 공용 함수(기관 확정 2026-11-17, ADR-087)
from datetime import datetime

from sqlalchemy import ColumnElement, and_, exists, or_, update
from sqlalchemy.orm import Session

from app.db.tables import TB_SMS_DMND, TB_SMS_TRGT

# 파기한 자리에 채우는 값. 두 컬럼 모두 NOT NULL이라 행과 상태·건수·실패 사유는 두고 값만 바꾼다
PURGED_TEXT = "(파기됨)"
PURGED_PHONE = "PURGED"
# 결과가 더 바뀌지 않는 수신 상태. SS.SENDING·SS.UNKNOWN은 조회로 확인될 때까지 확정이 아니다
FINAL_STATES = ("SS.SENT", "SS.FAIL", "SS.SKIP")


def _final() -> ColumnElement[bool]:
    return TB_SMS_TRGT.c.TRGT_STTS_CD.in_(FINAL_STATES)


def _of_request() -> ColumnElement[bool]:
    return TB_SMS_TRGT.c.SMS_DMND_SN == TB_SMS_DMND.c.SMS_DMND_SN


def pending_conditions(bundle: int) -> list[ColumnElement[bool]]:
    """아직 파기하지 못한 문자 요청. 수신 대상이 모두 확정됐는데 문안이 남았거나 확정된 수신번호가 남았다."""
    has_target = exists().where(_of_request())
    has_open = exists().where(_of_request(), ~_final())
    has_phone = exists().where(_of_request(), _final(), TB_SMS_TRGT.c.RCPTN_TELNO_ENCPT_VL != PURGED_PHONE)
    return [
        TB_SMS_DMND.c.OPER_BNDL_SN == bundle,
        or_(and_(has_target, ~has_open, TB_SMS_DMND.c.SMS_CN != PURGED_TEXT), has_phone),
    ]


def purge_request(db: Session, request_sn: int, *, now: datetime) -> None:
    """확정된 수신번호를 파기하고 수신 대상이 모두 확정됐으면 문안도 파기한다. 호출한 트랜잭션 안에서 한다."""
    db.execute(
        update(TB_SMS_TRGT)
        .where(
            TB_SMS_TRGT.c.SMS_DMND_SN == request_sn,
            _final(),
            TB_SMS_TRGT.c.RCPTN_TELNO_ENCPT_VL != PURGED_PHONE,
        )
        .values(RCPTN_TELNO_ENCPT_VL=PURGED_PHONE, MDFCN_DT=now, RCRD_VER=TB_SMS_TRGT.c.RCRD_VER + 1)
    )
    all_final = exists().where(TB_SMS_TRGT.c.SMS_DMND_SN == request_sn)
    has_open = exists().where(TB_SMS_TRGT.c.SMS_DMND_SN == request_sn, ~_final())
    db.execute(
        update(TB_SMS_DMND)
        .where(
            TB_SMS_DMND.c.SMS_DMND_SN == request_sn, all_final, ~has_open, TB_SMS_DMND.c.SMS_CN != PURGED_TEXT
        )
        .values(SMS_CN=PURGED_TEXT)
    )


def purge_sent_now(db: Session, request_sn: int, target_sn: int, *, now: datetime) -> None:
    """인증 문자는 워커가 다시 확인하지 않아 확정되지 않으므로 보낸 직후 수신번호와 문안을 파기한다."""
    db.execute(
        update(TB_SMS_TRGT)
        .where(TB_SMS_TRGT.c.SMS_TRGT_SN == target_sn)
        .values(RCPTN_TELNO_ENCPT_VL=PURGED_PHONE, MDFCN_DT=now, RCRD_VER=TB_SMS_TRGT.c.RCRD_VER + 1)
    )
    db.execute(update(TB_SMS_DMND).where(TB_SMS_DMND.c.SMS_DMND_SN == request_sn).values(SMS_CN=PURGED_TEXT))
