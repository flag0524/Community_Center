# 관리자 알림 이력과 문자 발송(AU.SMS_SEND). 대상 산정·미리보기·발송 요청을 서버가 하고 발송은 요청·수신명단을 저장한 뒤 워커가 한다(FN-059, SMS-01~06, ADR-070)
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.auth.crypto import DecryptError, decrypt, encrypt
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.idempotent import insert_idempotent
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_MBR,
    TB_MNGR,
    TB_OPER_BNDL,
    TB_SMS_DMND,
    TB_SMS_DMND_CORS,
    TB_SMS_SNDNG_HSTRY,
    TB_SMS_TRGT,
)
from app.domain.admin.member_service import mask_phone
from app.domain.admin.refund_service import mask_name
from app.domain.admin.sms_purge import PURGED_PHONE, PURGED_TEXT
from app.domain.admin.sms_schemas import (
    SMS_MAX_BYTES,
    SmsAudience,
    SmsPreview,
    SmsRecipient,
    SmsRequestDetail,
    SmsRequestPage,
    SmsRequestSummary,
    SmsSendRequest,
    SmsTargetRow,
)
from app.domain.admin.sms_types import SmsAudienceStatus, SmsKind, SmsScope, SmsTargetState
from app.domain.admin.types import AdminAuthority as AU

KIND_CODE = {SmsKind.AUTO: "SM.AUTO", SmsKind.MANUAL: "SM.MANUAL"}
SCOPE_CODE = {SmsScope.CENTER: "SG.CENTER", SmsScope.COURSE: "SG.COURSE", SmsScope.EVENT: "SG.EVENT"}
CODE_SCOPE = {code: scope for scope, code in SCOPE_CODE.items()}
CODE_KIND = {code: kind for kind, code in KIND_CODE.items()}
STATE = {
    "SS.WAIT": SmsTargetState.WAIT,
    "SS.SENDING": SmsTargetState.SENDING,
    "SS.SENT": SmsTargetState.SENT,
    "SS.FAIL": SmsTargetState.FAIL,
    "SS.UNKNOWN": SmsTargetState.UNKNOWN,
    "SS.SKIP": SmsTargetState.SKIP,
}
STATUS_CODE = {
    SmsAudienceStatus.CONFIRMED: "ES.CONFIRM",
    SmsAudienceStatus.PAYMENT_PENDING: "ES.HOLD",
    SmsAudienceStatus.WAITING: "ES.WAIT",
}
PREVIEW_RECIPIENTS = 50
DETAIL_TARGETS = 200
SUMMARY_CHARS = 30
NOT_OTP = or_(TB_SMS_DMND.c.SRC_EVENT_ID.is_(None), ~TB_SMS_DMND.c.SRC_EVENT_ID.like("CERT:%"))


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


# --- 대상 산정 ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Audience:
    course_ids: list[int]
    recipients: list[tuple[int, str, str]]  # (회원 번호, 이름, 휴대전화)
    pairs: int  # 중복을 빼기 전의 (회원, 강좌) 수
    course_count: int
    byte_length: int


def _bytes(content: str) -> int:
    """문자 공급자가 세는 길이(한글 2바이트). 표현할 수 없는 글자가 있으면 거절한다."""
    try:
        return len(content.encode("cp949"))
    except UnicodeEncodeError:
        raise _fail("content", "문자로 보낼 수 없는 글자가 있습니다.") from None


def _audience(db: Session, admin: Admin, scope: Scope, body: SmsAudience) -> Audience:
    if body.scope is SmsScope.EVENT:
        raise _fail("scope", "센터 전체 또는 선택 강좌만 고를 수 있습니다.")
    content = body.content.strip()
    if not content:
        raise _fail("content", "문안을 입력해 주세요.")
    size = _bytes(content)
    if size > SMS_MAX_BYTES:
        raise _fail(
            "content",
            f"문안은 {SMS_MAX_BYTES}바이트(한글 {SMS_MAX_BYTES // 2}자)까지입니다. 지금 {size}바이트입니다.",
        )
    query = (
        select(TB_ATNLC_APLY.c.MBR_SN, TB_ATNLC_APLY.c.CORS_SN, TB_MBR.c.MBR_NM, TB_MBR.c.MBL_TELNO)
        .select_from(TB_ATNLC_APLY)
        .join(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_MBR.c.MBR_SN == TB_ATNLC_APLY.c.MBR_SN),
        )
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN)
            & (TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN),
        )
        .where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_ATNLC_APLY.c.APLY_STTS_CD.in_([STATUS_CODE[s] for s in set(body.statuses)]),
            TB_MBR.c.MBR_STTS_CD == "MS.ACTIVE",
            TB_MBR.c.MBL_TELNO.is_not(None),
        )
        .order_by(TB_ATNLC_APLY.c.MBR_SN, TB_ATNLC_APLY.c.CORS_SN)
    )
    if body.scope is SmsScope.CENTER:
        if body.course_ids:
            raise _fail("courseIds", "센터 전체에는 강좌를 고르지 않습니다.")
        if not scope.whole:
            raise ApiError(ErrorCode.FORBIDDEN)  # 센터 전체는 센터 전체 범위 권한이 필요하다(SMS-01)
        course_ids: list[int] = []
    else:
        course_ids = sorted({int(c) for c in body.course_ids})
        if not course_ids:
            raise _fail("courseIds", "강좌를 하나 이상 골라 주세요.")
        found = db.execute(
            select(TB_CORS.c.CORS_SN, TB_CORS.c.DONG_SN).where(
                TB_CORS.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS.c.CORS_SN.in_(course_ids)
            )
        ).all()
        usable = {
            int(c.CORS_SN) for c in found if scope.covers(None if c.DONG_SN is None else int(c.DONG_SN))
        }
        if usable != set(course_ids):
            raise _fail("courseIds", "선택한 강좌를 찾을 수 없습니다.")
        query = query.where(TB_ATNLC_APLY.c.CORS_SN.in_(course_ids))
    rows = db.execute(query).all()
    members: dict[int, tuple[str, str]] = {}
    for row in rows:
        members.setdefault(int(row.MBR_SN), (str(row.MBR_NM), str(row.MBL_TELNO)))
    return Audience(
        course_ids=course_ids,
        recipients=[(sn, name, phone) for sn, (name, phone) in members.items()],
        pairs=len(rows),
        course_count=len({int(r.CORS_SN) for r in rows}),
        byte_length=size,
    )


def preview(db: Session, admin: Admin, *, now: datetime, body: SmsAudience) -> SmsPreview:
    """대상을 산정해 수신자 수를 알려 준다. 저장하지 않는다. 회원 한 명은 한 번만 센다."""
    scope = permit(db, admin, AU.SMS_SEND, now)
    audience = _audience(db, admin, scope, body)
    center = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_NM).where(TB_OPER_BNDL.c.OPER_BNDL_SN == admin.bundle_sn)
    ).scalar_one()
    return SmsPreview(
        recipient_count=len(audience.recipients),
        duplicate_removed=audience.pairs - len(audience.recipients),
        course_count=audience.course_count,
        center_name=str(center),
        byte_length=audience.byte_length,
        recipients=[
            SmsRecipient(name=mask_name(name), phone=mask_phone(phone))
            for _, name, phone in audience.recipients[:PREVIEW_RECIPIENTS]
        ],
    )


# --- 발송 요청 ----------------------------------------------------------------------------------


def _hash(body: SmsAudience) -> str:
    material = {
        "scope": body.scope.value,
        "courses": sorted({int(c) for c in body.course_ids}),
        "statuses": sorted({s.value for s in body.statuses}),
        "content": body.content.strip(),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def send(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    body: SmsSendRequest,
    idem_key: str,
) -> SmsRequestDetail:
    """대상을 다시 산정해 요청·강좌 연결·수신명단을 한 트랜잭션으로 저장한다. 문안과 명단은 저장한 뒤 고치지 않는다(SMS-02)."""
    scope = permit(db, admin, AU.SMS_SEND, now)
    key = f"a{admin.admin_sn}-{idem_key}"
    digest = _hash(body)
    prior = db.execute(
        select(TB_SMS_DMND.c.SMS_DMND_SN, TB_SMS_DMND.c.DMND_HASH_VL).where(
            TB_SMS_DMND.c.OPER_BNDL_SN == admin.bundle_sn, TB_SMS_DMND.c.IDEM_KEY == key
        )
    ).first()
    if prior is not None:
        if prior.DMND_HASH_VL != digest:
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return get(db, settings, admin, now=now, sms_id=str(int(prior.SMS_DMND_SN)))
    audience = _audience(db, admin, scope, body)
    if not body.confirmed:
        raise _fail("confirmed", "수신 대상과 문안을 최종 확인해야 발송할 수 있습니다.")
    if not audience.recipients:
        raise _fail("scope", "수신 대상이 없습니다.")
    if len(audience.recipients) != body.expected_recipient_count:
        raise ApiError(
            ErrorCode.CONFLICT_STATE,
            f"수신 대상이 바뀌었습니다. 지금은 {len(audience.recipients)}명입니다. 미리보기를 다시 확인해 주세요.",
        )
    created, replayed = insert_idempotent(
        db,
        TB_SMS_DMND,
        {
            "OPER_BNDL_SN": admin.bundle_sn,
            "DMND_TYPE_CD": KIND_CODE[SmsKind.MANUAL],
            "DMND_MNGR_SN": admin.admin_sn,
            "TRGT_TYPE_CD": SCOPE_CODE[body.scope],
            "DSPTCH_TELNO": settings.sms_sender_number,
            "SMS_CN": body.content.strip(),
            "IDEM_KEY": key,
            "DMND_HASH_VL": digest,
            "REG_DT": now,
        },
        lambda existing: existing["DMND_HASH_VL"] == digest,
    )
    sn = int(created["SMS_DMND_SN"])
    if not replayed:
        if audience.course_ids:
            db.execute(
                TB_SMS_DMND_CORS.insert(),
                [
                    {"OPER_BNDL_SN": admin.bundle_sn, "SMS_DMND_SN": sn, "CORS_SN": c, "REG_DT": now}
                    for c in audience.course_ids
                ],
            )
        db.execute(
            TB_SMS_TRGT.insert(),
            [
                {
                    "OPER_BNDL_SN": admin.bundle_sn,
                    "SMS_DMND_SN": sn,
                    "MBR_SN": member,
                    "RCPTN_TELNO_ENCPT_VL": encrypt(settings.secret_key, phone),
                    "TRGT_STTS_CD": "SS.WAIT",
                    "REG_DT": now,
                    "RCRD_VER": 1,
                }
                for member, _, phone in audience.recipients
            ],
        )
        record_job(
            db,
            actor="AK.ADMIN",
            job="SMS_SEND",
            table="TB_SMS_DMND",
            key=sn,
            request_id=request_id,
            now=now,
            bundle_sn=admin.bundle_sn,
            admin_sn=admin.admin_sn,
            change=json.dumps(
                {
                    "scope": body.scope.value,
                    "courses": len(audience.course_ids),
                    "recipients": len(audience.recipients),
                }
            ),
        )
    return get(db, settings, admin, now=now, sms_id=str(sn))


# --- 이력 ---------------------------------------------------------------------------------------


def _visible(query: Select[Any], admin: Admin, scope: Scope) -> Select[Any]:
    """묶음 전체 담당자는 모든 요청을, 동 담당자는 자기가 보낸 관리자 문자만 본다."""
    if scope.whole:
        return query
    return query.where(
        TB_SMS_DMND.c.DMND_TYPE_CD == KIND_CODE[SmsKind.MANUAL], TB_SMS_DMND.c.DMND_MNGR_SN == admin.admin_sn
    )


def _counts() -> list[Any]:
    def n(*states: str) -> Any:
        return func.coalesce(func.sum(case((TB_SMS_TRGT.c.TRGT_STTS_CD.in_(states), 1), else_=0)), 0)

    return [
        func.count(TB_SMS_TRGT.c.SMS_TRGT_SN).label("TOTAL"),
        n("SS.SENT").label("SENT"),
        n("SS.FAIL").label("FAILED"),
        n("SS.SENDING", "SS.UNKNOWN").label("UNKNOWN"),
    ]


def _summary(row: Any) -> SmsRequestSummary:
    return SmsRequestSummary(
        sms_id=str(int(row.SMS_DMND_SN)),
        requested_at=utc(row.REG_DT),
        kind=CODE_KIND[str(row.DMND_TYPE_CD).strip()],
        scope=CODE_SCOPE[str(row.TRGT_TYPE_CD).strip()],
        summary=str(row.SMS_CN)[:SUMMARY_CHARS],
        target_count=int(row.TOTAL),
        sent=int(row.SENT),
        failed=int(row.FAILED),
        unknown=int(row.UNKNOWN),
        requested_by=str(row.MNGR_NM) if row.MNGR_NM is not None else "SYSTEM",
    )


def _base() -> Select[Any]:
    return (
        select(TB_SMS_DMND, TB_MNGR.c.MNGR_NM, *_counts())
        .select_from(TB_SMS_DMND)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_SMS_DMND.c.DMND_MNGR_SN)
        .outerjoin(
            TB_SMS_TRGT,
            (TB_SMS_TRGT.c.OPER_BNDL_SN == TB_SMS_DMND.c.OPER_BNDL_SN)
            & (TB_SMS_TRGT.c.SMS_DMND_SN == TB_SMS_DMND.c.SMS_DMND_SN),
        )
        .group_by(TB_SMS_DMND.c.SMS_DMND_SN, TB_MNGR.c.MNGR_NM)
    )


def list_requests(
    db: Session, admin: Admin, *, now: datetime, kind: SmsKind, page: int, size: int
) -> SmsRequestPage:
    """자동 알림과 관리자 발송 이력. 인증번호 문자는 업무 알림이 아니라 뺀다."""
    scope = permit(db, admin, AU.SMS_SEND, now)
    query = _visible(
        _base().where(
            TB_SMS_DMND.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_SMS_DMND.c.DMND_TYPE_CD == KIND_CODE[kind],
            NOT_OTP,
        ),
        admin,
        scope,
    ).order_by(TB_SMS_DMND.c.REG_DT.desc(), TB_SMS_DMND.c.SMS_DMND_SN.desc())
    total = int(
        db.execute(
            _visible(
                select(func.count()).where(
                    TB_SMS_DMND.c.OPER_BNDL_SN == admin.bundle_sn,
                    TB_SMS_DMND.c.DMND_TYPE_CD == KIND_CODE[kind],
                    NOT_OTP,
                ),
                admin,
                scope,
            )
        ).scalar_one()
    )
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return SmsRequestPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def get(db: Session, settings: Settings, admin: Admin, *, now: datetime, sms_id: str) -> SmsRequestDetail:
    """건별 결과와 실패 사유. 수신번호와 이름은 가려서 준다. 처음 200건만 담는다."""
    scope = permit(db, admin, AU.SMS_SEND, now)
    row = db.execute(
        _visible(
            _base().where(
                TB_SMS_DMND.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_SMS_DMND.c.SMS_DMND_SN == int(sms_id),
                NOT_OTP,
            ),
            admin,
            scope,
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    sn = int(row.SMS_DMND_SN)
    courses = [
        str(r.CORS_NM)
        for r in db.execute(
            select(TB_CORS.c.CORS_NM)
            .join(
                TB_SMS_DMND_CORS,
                (TB_SMS_DMND_CORS.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN)
                & (TB_SMS_DMND_CORS.c.CORS_SN == TB_CORS.c.CORS_SN),
            )
            .where(TB_SMS_DMND_CORS.c.SMS_DMND_SN == sn)
            .order_by(TB_CORS.c.CORS_NM, TB_CORS.c.CORS_SN)
        )
    ]
    latest = (
        select(func.max(TB_SMS_SNDNG_HSTRY.c.SNDNG_SEQ))
        .where(TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == TB_SMS_TRGT.c.SMS_TRGT_SN)
        .correlate(TB_SMS_TRGT)
        .scalar_subquery()
    )
    attempts = (
        select(func.count())
        .where(TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == TB_SMS_TRGT.c.SMS_TRGT_SN)
        .correlate(TB_SMS_TRGT)
        .scalar_subquery()
    )
    targets = db.execute(
        select(
            TB_SMS_TRGT.c.SMS_TRGT_SN,
            TB_SMS_TRGT.c.TRGT_STTS_CD,
            TB_SMS_TRGT.c.RCPTN_TELNO_ENCPT_VL,
            TB_MBR.c.MBR_NM,
            attempts.label("ATTEMPTS"),
            TB_SMS_SNDNG_HSTRY.c.FAIL_CD,
            TB_SMS_SNDNG_HSTRY.c.FAIL_RSN,
        )
        .select_from(TB_SMS_TRGT)
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_SMS_TRGT.c.MBR_SN)
        .outerjoin(
            TB_SMS_SNDNG_HSTRY,
            and_(
                TB_SMS_SNDNG_HSTRY.c.SMS_TRGT_SN == TB_SMS_TRGT.c.SMS_TRGT_SN,
                TB_SMS_SNDNG_HSTRY.c.SNDNG_SEQ == latest,
            ),
        )
        .where(TB_SMS_TRGT.c.OPER_BNDL_SN == admin.bundle_sn, TB_SMS_TRGT.c.SMS_DMND_SN == sn)
        .order_by(TB_SMS_TRGT.c.SMS_TRGT_SN)
        .limit(DETAIL_TARGETS + 1)
    ).all()
    return SmsRequestDetail(
        **_summary(row).model_dump(),
        content=str(row.SMS_CN),
        course_names=courses,
        targets=[_target(t, settings.secret_key) for t in targets[:DETAIL_TARGETS]],
        targets_truncated=len(targets) > DETAIL_TARGETS,
    )


def _target(row: Any, secret: str) -> SmsTargetRow:
    try:
        phone = (
            PURGED_TEXT
            if str(row.RCPTN_TELNO_ENCPT_VL) == PURGED_PHONE
            else mask_phone(decrypt(secret, str(row.RCPTN_TELNO_ENCPT_VL)))
        )
    except DecryptError:
        phone = "****"
    return SmsTargetRow(
        target_id=str(int(row.SMS_TRGT_SN)),
        name=mask_name(str(row.MBR_NM)) if row.MBR_NM is not None else "",
        phone=phone,
        state=STATE[str(row.TRGT_STTS_CD).strip()],
        attempts=int(row.ATTEMPTS),
        fail_code=None if row.FAIL_CD is None else str(row.FAIL_CD),
        fail_reason=None if row.FAIL_RSN is None else str(row.FAIL_RSN),
    )
