# 관리자 보존·파기 검토의 목록·상세(조회 전용). 보존기간은 TRD 5.1을 따르고 정해지지 않은 자료는 값을 가정하지 않는다(NF-006, ADR-074)
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Column, ColumnElement, func, select
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, permit
from app.core.errors import ApiError, ErrorCode
from app.core.times import kst_today
from app.db.tables import TB_CERT_DMND, TB_JOB_HSTRY, TB_MBR, TB_RFND, TB_SMS_DMND
from app.domain.admin.retention_schemas import (
    RetentionDetail,
    RetentionExclusion,
    RetentionItem,
    RetentionList,
)
from app.domain.admin.retention_types import RetentionState, RetentionTarget
from app.domain.admin.types import AdminAuthority as AU

OTP_DAYS = 30  # 가정값(PRD Q30 확정 전)
WITHDRAWN_DAYS = 30
AUDIT_YEARS = 3

EXCLUSIONS = [
    RetentionExclusion(
        label="정산자료(결제·환불 원장)", reason="법정 보존 5년 대상이며 탈퇴와 무관해 이 목록에서 제외한다."
    ),
    RetentionExclusion(
        label="보안 접속로그", reason="인프라(Nginx·OS) 로그로 1년 보관하며 이 시스템에서 처리하지 않는다."
    ),
]


@dataclass(frozen=True)
class _Rule:
    target: RetentionTarget
    rule: str
    fields: tuple[str, ...]


# 항목 번호는 대상 종류마다 고정이다(보존 항목을 담는 테이블이 없다)
_ORDER = (
    _Rule(
        RetentionTarget.WITHDRAWN_MEMBER,
        "탈퇴한 회원의 일반 개인정보는 탈퇴 후 30일이 지나면 파기하거나 비식별 처리한다. 결제·환불 원장은 5년 보존이라 건드리지 않는다.",
        ("이름", "휴대전화", "이메일"),
    ),
    _Rule(
        RetentionTarget.AUTH_RECORDS,
        "인증번호 요청은 30일이 지나면 정리한다(가정값, PRD Q30 확정 전). 세션과 로그인 실패 이력의 기간은 정해지지 않아 세지 않는다.",
        ("인증번호 요청 기록",),
    ),
    _Rule(
        RetentionTarget.AUDIT_HISTORY,
        "업무 감사이력은 3년 보존하고 이 화면에서는 검토만 한다. 실행하지 않는다.",
        ("작업 이력",),
    ),
    _Rule(
        RetentionTarget.REFUND_ACCOUNT,
        "수동환불 계좌정보의 보존기간은 정해지지 않았다(TBD). 기관이 정하기 전에는 예정일을 계산하지 않는다.",
        ("은행", "계좌번호", "예금주"),
    ),
    _Rule(
        RetentionTarget.SMS_RECORDS,
        "문자 문안·수신명단의 보존기간은 정해지지 않았다(TBD). 기관이 정하기 전에는 예정일을 계산하지 않는다.",
        ("문안", "수신번호"),
    ),
)


def _years_before(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:  # 2월 29일
        return value.replace(year=value.year - years, day=28)


def _years_after(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _whole(db: Session, admin: Admin, now: datetime) -> None:
    """보존·파기는 묶음 공통이라 묶음 전체 범위의 담당자만 본다(PRD Q21 후보 AU.LOG_R)."""
    if not permit(db, admin, AU.LOG_R, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _count_and_oldest(
    db: Session, column: Column[Any], *conditions: ColumnElement[bool], due_before: datetime | None
) -> tuple[int, datetime | None]:
    """조건에 맞는 전체의 가장 오래된 시각과 건수를 구한다. 기준 시각을 주면 그 이전인 건수만 센다."""
    oldest = db.execute(select(func.min(column)).where(*conditions)).scalar()
    counted = conditions if due_before is None else (*conditions, column <= due_before)
    total = db.execute(select(func.count()).select_from(column.table).where(*counted)).scalar()
    return int(total or 0), oldest


def _item(db: Session, admin: Admin, now: datetime, index: int) -> RetentionItem:
    target = _ORDER[index - 1].target
    bundle = admin.bundle_sn
    today = kst_today(now)
    period: tuple[int, str] | None = None  # (기간, 단위)
    if target is RetentionTarget.WITHDRAWN_MEMBER:
        count, oldest = _count_and_oldest(
            db,
            TB_MBR.c.WHDWL_DT,
            TB_MBR.c.OPER_BNDL_SN == bundle,
            TB_MBR.c.MBR_STTS_CD == "MS.WITHDRAW",
            TB_MBR.c.WHDWL_DT.is_not(None),
            due_before=now - timedelta(days=WITHDRAWN_DAYS),
        )
        period = (WITHDRAWN_DAYS, "d")
    elif target is RetentionTarget.AUTH_RECORDS:
        count, oldest = _count_and_oldest(
            db,
            TB_CERT_DMND.c.REG_DT,
            TB_CERT_DMND.c.OPER_BNDL_SN == bundle,
            due_before=now - timedelta(days=OTP_DAYS),
        )
        period = (OTP_DAYS, "d")
    elif target is RetentionTarget.AUDIT_HISTORY:
        count, oldest = _count_and_oldest(
            db,
            TB_JOB_HSTRY.c.REG_DT,
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle,
            due_before=_years_before(now, AUDIT_YEARS),
        )
        period = (AUDIT_YEARS, "y")
    elif target is RetentionTarget.REFUND_ACCOUNT:
        count, oldest = _count_and_oldest(
            db,
            TB_RFND.c.RFND_DT,
            TB_RFND.c.OPER_BNDL_SN == bundle,
            TB_RFND.c.RFND_ACTNO_ENCPT_VL.is_not(None),
            TB_RFND.c.RFND_DT.is_not(None),
            due_before=None,
        )
    else:
        count, oldest = _count_and_oldest(
            db, TB_SMS_DMND.c.REG_DT, TB_SMS_DMND.c.OPER_BNDL_SN == bundle, due_before=None
        )
    base_date = None if oldest is None else kst_today(oldest)
    due_on: date | None = None
    if period is not None and base_date is not None:
        due_on = (
            base_date + timedelta(days=period[0]) if period[1] == "d" else _years_after(base_date, period[0])
        )
    if target is RetentionTarget.AUDIT_HISTORY:
        state = RetentionState.REVIEW_ONLY
    elif period is None:
        state = RetentionState.PERIOD_TBD
    else:
        state = (
            RetentionState.DUE
            if count > 0 and due_on is not None and due_on <= today
            else RetentionState.WAITING
        )
    return RetentionItem(
        item_id=str(index), target=target, count=count, base_date=base_date, due_on=due_on, state=state
    )


def list_retention(db: Session, admin: Admin, *, now: datetime) -> RetentionList:
    _whole(db, admin, now)
    return RetentionList(
        items=[_item(db, admin, now, i) for i in range(1, len(_ORDER) + 1)], exclusions=EXCLUSIONS
    )


def get_retention(db: Session, admin: Admin, *, now: datetime, item_id: str) -> RetentionDetail:
    _whole(db, admin, now)
    index = int(item_id)
    if not 1 <= index <= len(_ORDER):
        raise ApiError(ErrorCode.NOT_FOUND)
    item = _item(db, admin, now, index)
    rule = _ORDER[index - 1]
    return RetentionDetail(
        **item.model_dump(), rule=rule.rule, fields=list(rule.fields), executions=[], can_execute=False
    )
