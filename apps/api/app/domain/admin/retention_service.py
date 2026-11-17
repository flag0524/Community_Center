# 관리자 보존·파기 검토의 목록·상세와 실행(탈퇴 회원 비식별, 인증번호 요청 삭제). 보존기간은 TRD 5.1을 따르고 정해지지 않은 자료는 값을 가정하지 않는다(NF-006, ADR-074·078)
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Column, ColumnElement, and_, delete, exists, func, not_, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit, scope_for
from app.core.errors import ApiError, ErrorCode
from app.core.times import kst_today, utc
from app.db.tables import (
    TB_CERT_DMND,
    TB_JOB_HSTRY,
    TB_MBR,
    TB_MNGR,
    TB_RFND,
    TB_SMS_DMND,
    TB_SMS_TRGT,
)
from app.domain.admin.retention_schemas import (
    RetentionDetail,
    RetentionExclusion,
    RetentionExecution,
    RetentionItem,
    RetentionList,
)
from app.domain.admin.retention_types import RetentionState, RetentionTarget
from app.domain.admin.types import AdminAuthority as AU

OTP_DAYS = 30  # 가정값(PRD Q30 확정 전)
WITHDRAWN_DAYS = 30
AUDIT_YEARS = 3
ANON_NAME = (
    "탈퇴회원"  # 비식별한 회원의 이름. 이름이 이 값이고 전화번호가 없으면 이미 처리한 회원이다(ADR-078)
)
EXECUTE_JOB = "RETENTION_EXECUTE"
# 이 화면에서 실행할 수 있는 대상. 감사이력은 검토만 하고 환불계좌·문자기록은 보존기간이 정해지지 않았다
EXECUTABLE = (RetentionTarget.WITHDRAWN_MEMBER, RetentionTarget.AUTH_RECORDS)

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


def _member_conditions(bundle: int) -> list[ColumnElement[bool]]:
    """비식별 대상 후보. 탈퇴한 회원 중 이미 비식별한 회원은 뺀다."""
    return [
        TB_MBR.c.OPER_BNDL_SN == bundle,
        TB_MBR.c.MBR_STTS_CD == "MS.WITHDRAW",
        TB_MBR.c.WHDWL_DT.is_not(None),
        not_(and_(TB_MBR.c.MBR_NM == ANON_NAME, TB_MBR.c.MBL_TELNO.is_(None))),
    ]


def _otp_conditions(bundle: int) -> list[ColumnElement[bool]]:
    """삭제 대상 후보. 문자 기록이 가리키는 인증 요청은 문자 기록의 보존기간이 정해질 때까지 지우지 않는다."""
    return [
        TB_CERT_DMND.c.OPER_BNDL_SN == bundle,
        ~exists().where(
            TB_SMS_TRGT.c.OPER_BNDL_SN == TB_CERT_DMND.c.OPER_BNDL_SN,
            TB_SMS_TRGT.c.CERT_DMND_SN == TB_CERT_DMND.c.CERT_DMND_SN,
        ),
    ]


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
            *_member_conditions(bundle),
            due_before=now - timedelta(days=WITHDRAWN_DAYS),
        )
        period = (WITHDRAWN_DAYS, "d")
    elif target is RetentionTarget.AUTH_RECORDS:
        count, oldest = _count_and_oldest(
            db,
            TB_CERT_DMND.c.REG_DT,
            *_otp_conditions(bundle),
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


def _executions(db: Session, bundle: int, index: int) -> list[RetentionExecution]:
    """이 항목의 실행 기록. 최근 것이 먼저이고 20건까지 준다."""
    rows = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.CHG_CN, TB_MNGR.c.MNGR_NM)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle,
            TB_JOB_HSTRY.c.JOB_CD == EXECUTE_JOB,
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(index),
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.SUCCESS",
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT.desc(), TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
        .limit(20)
    ).all()
    out = []
    for row in rows:
        found = re.match(r"처리 (\d+)건", str(row.CHG_CN or ""))
        out.append(
            RetentionExecution(
                at=utc(row.REG_DT),
                by=str(row.MNGR_NM or "SYSTEM"),
                processed=int(found.group(1)) if found else 0,
            )
        )
    return out


def _detail(db: Session, admin: Admin, now: datetime, index: int) -> RetentionDetail:
    item = _item(db, admin, now, index)
    rule = _ORDER[index - 1]
    allowed = scope_for(db, admin, AU.GRANT_W, now).whole
    return RetentionDetail(
        **item.model_dump(),
        rule=rule.rule,
        fields=list(rule.fields),
        executions=_executions(db, admin.bundle_sn, index),
        can_execute=allowed
        and rule.target in EXECUTABLE
        and item.state is RetentionState.DUE
        and item.count > 0,
    )


def _index(item_id: str) -> int:
    index = int(item_id)
    if not 1 <= index <= len(_ORDER):
        raise ApiError(ErrorCode.NOT_FOUND)
    return index


def get_retention(db: Session, admin: Admin, *, now: datetime, item_id: str) -> RetentionDetail:
    _whole(db, admin, now)
    return _detail(db, admin, now, _index(item_id))


def _mark(idem_key: str, index: int, expected: int) -> str:
    """파기 요청의 멱등 표식. 대상 테이블에 멱등키 컬럼이 없어 작업이력 메모에 키와 내용 해시를 남긴다(개정 요청 R28)."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    body = hashlib.sha256(f"{index}:{expected}".encode()).hexdigest()[:16]
    return f"[idem {key}:{body}]"


def _replayed(db: Session, bundle: int, mark: str) -> bool:
    """같은 키로 이미 실행했으면 True다. 내용이 다르면 409(IDEMPOTENCY_CONFLICT)다."""
    prefix = mark.split(":")[0] + ":"
    found = db.execute(
        select(TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle,
            TB_JOB_HSTRY.c.JOB_CD == EXECUTE_JOB,
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if found is None:
        return False
    if mark not in str(found.CHG_CN):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return True


def _anonymize(db: Session, bundle: int, member_sns: list[int], now: datetime) -> None:
    """이름·전화번호·이메일을 지우고 로그인 아이디를 회원 번호로 바꾼다. 같은 아이디가 이미 있으면 해시 아이디를 쓴다."""
    wanted = {sn: f"withdrawn-{sn}" for sn in member_sns}
    taken = {
        str(r.LGN_ID)
        for r in db.execute(
            select(TB_MBR.c.LGN_ID).where(
                TB_MBR.c.OPER_BNDL_SN == bundle, TB_MBR.c.LGN_ID.in_(list(wanted.values()))
            )
        )
    }
    for sn, login in wanted.items():
        if login in taken or len(login) > 20:
            login = "w-" + hashlib.sha256(f"{bundle}:{sn}".encode()).hexdigest()[:18]
        db.execute(
            update(TB_MBR)
            .where(TB_MBR.c.OPER_BNDL_SN == bundle, TB_MBR.c.MBR_SN == sn)
            .values(
                MBR_NM=ANON_NAME,
                MBL_TELNO=None,
                EML_ADDR=None,
                LGN_ID=login,
                RCRD_VER=TB_MBR.c.RCRD_VER + 1,
                MDFCN_DT=now,
            )
        )


def execute_retention(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    item_id: str,
    expected_count: int,
    idem_key: str,
) -> RetentionDetail:
    """확인한 건수와 다시 센 건수가 같을 때만 처리한다(되돌릴 수 없다). 대상 행을 잠근 뒤에 세고 처리한다."""
    if not scope_for(db, admin, AU.GRANT_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    index = _index(item_id)
    target = _ORDER[index - 1].target
    if target not in EXECUTABLE:
        message = (
            "업무 감사이력은 검토만 하고 이 화면에서 처리하지 않습니다."
            if target is RetentionTarget.AUDIT_HISTORY
            else "보존기간이 정해지지 않은 자료라 처리할 수 없습니다."
        )
        raise ApiError(ErrorCode.RULE_REJECTED, message)
    bundle = admin.bundle_sn
    if target is RetentionTarget.WITHDRAWN_MEMBER:
        keys = [
            int(sn)
            for sn in db.execute(
                select(TB_MBR.c.MBR_SN)
                .where(*_member_conditions(bundle), TB_MBR.c.WHDWL_DT <= now - timedelta(days=WITHDRAWN_DAYS))
                .order_by(TB_MBR.c.MBR_SN)
                .with_for_update()
            ).scalars()
        ]
        table = "TB_MBR"
    else:
        keys = [
            int(sn)
            for sn in db.execute(
                select(TB_CERT_DMND.c.CERT_DMND_SN)
                .where(*_otp_conditions(bundle), TB_CERT_DMND.c.REG_DT <= now - timedelta(days=OTP_DAYS))
                .order_by(TB_CERT_DMND.c.CERT_DMND_SN)
                .with_for_update()
            ).scalars()
        ]
        table = "TB_CERT_DMND"
    mark = _mark(idem_key, index, expected_count)
    if _replayed(db, bundle, mark):  # 잠금을 기다린 사이 같은 요청이 끝났을 수 있어 잠근 뒤에 본다
        return _detail(db, admin, now, index)
    if len(keys) != expected_count:
        raise ApiError(
            ErrorCode.CONFLICT_STATE,
            f"처리 대상이 {len(keys)}건으로 바뀌었습니다. 목록을 새로 확인해 주세요.",
        )
    if target is RetentionTarget.WITHDRAWN_MEMBER:
        _anonymize(db, bundle, keys, now)
    else:
        db.execute(delete(TB_CERT_DMND).where(TB_CERT_DMND.c.CERT_DMND_SN.in_(keys)))
    record_job(
        db,
        actor="AK.ADMIN",
        job=EXECUTE_JOB,
        table=table,
        key=index,
        request_id=request_id,
        now=now,
        bundle_sn=bundle,
        admin_sn=admin.admin_sn,
        change=f"처리 {len(keys)}건 {mark}",
    )
    return _detail(db, admin, now, index)
