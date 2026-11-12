# 개인식별 명단 암호화 ZIP 내보내기(AU.EXPORT, ADR-053). 실제 이름·연락처를 AES-256 ZIP으로 만든다
import hashlib
import io
import secrets
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pyzipper
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit
from app.core.errors import ApiError, ErrorCode, not_implemented
from app.db.tables import TB_JOB_HSTRY, TB_MBR, TB_MNGR
from app.domain.admin import application_service as applications
from app.domain.admin.csv_export import build_csv
from app.domain.admin.export_schemas import PiiExportRequest
from app.domain.admin.export_types import PiiExportTarget
from app.domain.admin.refund_service import scoped
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.types import ApplicationStatus
from app.domain.payment.types import PaymentStatus

MAX_ROWS = 5_000  # 개인식별 명단은 5천 행까지만 만든다(DV167). 넘으면 조건을 좁히게 한다
PASSWORD_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # 읽기 헷갈리는 글자(0 O 1 l I)를 뺀다
)
PASSWORD_LENGTH = 20
ENTRY_NAME = "applicants.csv"


@dataclass(frozen=True)
class PiiFile:
    content: bytes
    password: str
    count: int


def new_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def build_zip(entry: str, content: bytes, password: str) -> bytes:
    """AES-256(WinZip AE-2) 암호화 ZIP. 암호 없이는 목록도 내용도 읽을 수 없다."""
    out = io.BytesIO()
    with pyzipper.AESZipFile(out, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
        z.setpassword(password.encode())
        z.setencryption(pyzipper.WZ_AES, nbits=256)
        z.writestr(entry, content)
    return out.getvalue()


def _mark(idem_key: str) -> str:
    return f"[idem {hashlib.sha256(idem_key.encode()).hexdigest()[:16]}]"


def _already_made(db: Session, admin: Admin, mark: str) -> bool:
    """암호를 남기지 않아 같은 멱등키는 내용과 상관없이 다시 줄 수 없다. 표식은 작업이력 메모에 둔다(R28)."""
    return (
        db.execute(
            select(TB_JOB_HSTRY.c.JOB_HSTRY_SN).where(
                TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_JOB_HSTRY.c.MNGR_SN == admin.admin_sn,
                TB_JOB_HSTRY.c.JOB_CD == "PII_EXPORT",
                TB_JOB_HSTRY.c.CHG_CN.contains(mark, autoescape=True),
            )
        ).first()
        is not None
    )


def _enum(kind: type[Any], value: str | None) -> Any:
    try:
        return None if value is None else kind(value)
    except ValueError:
        raise ApiError(ErrorCode.VALIDATION_FAILED, "조건 값이 올바르지 않습니다.") from None


def _date(value: str | None) -> date | None:
    try:
        return None if value is None else date.fromisoformat(value)
    except ValueError:
        raise ApiError(ErrorCode.VALIDATION_FAILED, "날짜 값이 올바르지 않습니다.") from None


def export_pii(
    db: Session, admin: Admin, *, now: datetime, request_id: str, idem_key: str, body: PiiExportRequest
) -> PiiFile:
    if body.target is PiiExportTarget.MEMBERS:
        not_implemented()  # 회원 목록이 아직 없다. 목록과 같은 조건·범위로 만들 수 있을 때 연다
    export_scope = permit(db, admin, AU.EXPORT, now)  # 내보내기 권한이 먼저다. 없으면 목록 권한이 있어도 403
    # 같은 담당자의 요청을 한 줄로 세워 멱등키 조회와 기록 사이의 틈을 막는다
    db.execute(select(TB_MNGR.c.MNGR_SN).where(TB_MNGR.c.MNGR_SN == admin.admin_sn).with_for_update()).one()
    mark = _mark(idem_key)
    if _already_made(db, admin, mark):
        raise ApiError(
            ErrorCode.IDEMPOTENCY_CONFLICT,
            "같은 요청 키로 이미 파일을 만들었고 암호는 다시 줄 수 없습니다. 새로 요청해 주세요.",
        )
    query = applications._filtered(  # 목록 권한(AU.APLY_R)과 범위를 목록과 같은 곳에서 적용한다
        db,
        admin,
        now,
        q=body.q,
        cycle_id=body.cycle_id,
        course_id=body.course_id,
        status=_enum(ApplicationStatus, body.status),
        payment_status=_enum(PaymentStatus, body.payment_status),
        from_date=_date(body.from_date),
        to_date=_date(body.to_date),
    )
    rows = list(
        db.execute(scoped(query, export_scope).add_columns(TB_MBR.c.MBL_TELNO).limit(MAX_ROWS + 1)).all()
    )
    if len(rows) > MAX_ROWS:
        raise ApiError(
            ErrorCode.RULE_REJECTED, f"한 번에 최대 {MAX_ROWS:,}건까지 만들 수 있습니다. 조건을 좁혀 주세요."
        )
    items = applications._summaries(db, admin, rows, now)
    csv_bytes = build_csv(
        ["신청번호", "강좌", "신청자", "휴대전화", "신청 상태", "결제 상태", "신청일시"],
        [
            [
                i.application_no,
                i.course_name,
                str(r.MBR_NM),  # 목록과 달리 가리지 않은 실제 값이다
                None if r.MBL_TELNO is None else str(r.MBL_TELNO),
                i.status.value,
                None if i.payment_status is None else i.payment_status.value,
                i.applied_at,
            ]
            for r, i in zip(rows, items, strict=True)
        ],
    )
    password = new_password()
    zipped = build_zip(ENTRY_NAME, csv_bytes, password)
    given = ",".join(sorted(k for k, v in body.model_dump(exclude={"target"}).items() if v))
    record_job(  # 누가·무엇을·몇 건만 남긴다. 암호·내용·검색어 값은 남기지 않는다
        db,
        actor="AK.ADMIN",
        job="PII_EXPORT",
        table="TB_ATNLC_APLY",
        key=None,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"{len(items)}건 암호화 내보냄(조건: {given or '없음'}) {mark}",
    )
    return PiiFile(zipped, password, len(items))
