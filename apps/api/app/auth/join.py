# 회원 가입. 인증(OTP) 소비·회원 생성·약관 동의 이력·감사 기록을 한 트랜잭션으로 확정한다(TDD 8.1, R17·R22)
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.crypto import DecryptError, decrypt
from app.auth.otp import consume_otp, mark_used
from app.auth.passwords import hash_password
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_MBR, TB_MBR_AGRE_HSTRY, TB_SITE_CONTS
from app.domain.member.schemas import AgreementItem
from app.domain.member.types import OtpPurpose, TermType

DUPLICATE_ENTRY = 1062
# 가입에서 다루는 동의문 유형. 어떤 문안이 필수인지는 문안마다 ESNTL_YN이 정한다(스키마 4.16)
TERM_CONTENT_TYPES = {
    TermType.TERMS_OF_USE: "CT.TERMS",
    TermType.PRIVACY_CONSENT: "CT.PRIVACY",
    TermType.MARKETING_CONSENT: "CT.MARKET",
}


@dataclass(frozen=True)
class Joined:
    member_sn: int
    name: str
    login_id: str


@dataclass(frozen=True)
class Published:
    site_conts_sn: int
    version: str
    body: str
    content_hash: str | None
    essential: bool


def _published(db: Session, bundle_sn: int, content_type: str, now: datetime) -> list[Published]:
    """같은 묶음에서 지금 게시 중인 문안. 게시 여부와 게시 기간을 모두 본다."""
    rows = db.execute(
        select(
            TB_SITE_CONTS.c.SITE_CONTS_SN,
            TB_SITE_CONTS.c.VER_NM,
            TB_SITE_CONTS.c.CONTS_CN,
            TB_SITE_CONTS.c.CONTS_HASH_VL,
            TB_SITE_CONTS.c.ESNTL_YN,
        ).where(
            TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn,
            TB_SITE_CONTS.c.CONTS_TYPE_CD == content_type,
            TB_SITE_CONTS.c.PSTG_YN == "Y",
            (TB_SITE_CONTS.c.PSTG_BGNG_DT.is_(None)) | (TB_SITE_CONTS.c.PSTG_BGNG_DT <= now),
            (TB_SITE_CONTS.c.PSTG_END_DT.is_(None)) | (TB_SITE_CONTS.c.PSTG_END_DT > now),
        )
    ).all()
    return [Published(int(r[0]), str(r[1]), str(r[2]), r[3], r[4] == "Y") for r in rows]


def _check_agreements(
    db: Session, bundle_sn: int, items: list[AgreementItem], now: datetime
) -> list[tuple[int, str]]:
    """동의할 (문안 번호, 해시)를 돌려준다. 필수 유형은 동의해야 하고 미게시·해시 불일치는 거절한다."""
    given = {item.term_type: item for item in items}
    if len(given) != len(items):
        raise ApiError(ErrorCode.VALIDATION_FAILED, fields={"agreements": "같은 약관이 두 번 들어 있습니다."})
    documents = {t: _published(db, bundle_sn, code, now) for t, code in TERM_CONTENT_TYPES.items()}
    if not any(doc.essential for docs in documents.values() for doc in docs):
        # 문서에 없는 보수적 규칙이다. 필수 문안이 하나도 없으면 약관 동의 없이 가입이 되므로 막는다(ADR-033).
        raise ApiError(ErrorCode.RULE_REJECTED, "가입에 필요한 약관이 게시되어 있지 않습니다.")
    accepted: list[tuple[int, str]] = []
    for term_type, published in documents.items():
        item = given.get(term_type)
        if item is None or not item.agreed:
            if any(
                doc.essential for doc in published
            ):  # 이 유형에 필수 문안이 게시돼 있으면 동의가 있어야 한다
                raise ApiError(ErrorCode.RULE_REJECTED, fields={"agreements": "필수 약관에 동의해 주세요."})
            continue
        match = next((doc for doc in published if doc.version == item.version), None)
        if match is None:
            raise ApiError(ErrorCode.RULE_REJECTED, fields={"agreements": "게시 중인 약관 버전이 아닙니다."})
        recomputed = hashlib.sha256(match.body.encode("utf-8")).hexdigest()
        if recomputed != match.content_hash:
            raise ApiError(ErrorCode.INTERNAL_ERROR)  # 고정된 문안이 바뀌었다(R17). 동의를 받으면 안 된다
        accepted.append((match.site_conts_sn, recomputed))
    return accepted


def join_member(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    cert_sn: int,
    code: str,
    login_id: str,
    password: str,
    email: str,
    agreements: list[AgreementItem],
    request_id: str,
    now: datetime,
) -> Joined:
    row = consume_otp(
        db, settings, cert_sn=cert_sn, code=code, purpose=OtpPurpose.JOIN, bundle_sn=bundle_sn, now=now
    )
    try:
        payload = json.loads(decrypt(settings.secret_key, str(row.TELNO_ENCPT_VL)))
    except (DecryptError, ValueError):
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
    name = payload.get("n")
    phone = payload.get("p")
    if not name or not phone:
        raise ApiError(ErrorCode.INTERNAL_ERROR)
    accepted = _check_agreements(db, bundle_sn, agreements, now)
    try:
        # 아이디가 겹치면 이 삽입 문장만 실패한다(InnoDB). 인증 행의 잠금은 그대로라 저장점이 필요 없다.
        member_sn = int(
            db.execute(
                insert(TB_MBR)
                .values(
                    OPER_BNDL_SN=bundle_sn,
                    LGN_ID=login_id,
                    PSWD_HASH_VL=hash_password(password, settings.pbkdf2_iterations),
                    MBR_NM=name,
                    MBL_TELNO=phone,
                    EML_ADDR=email,
                    MBR_JOIN_DT=now,
                )
                .returning(TB_MBR.c.MBR_SN)
            ).scalar_one()
        )
    except IntegrityError as error:
        if error.orig is not None and error.orig.args[0] == DUPLICATE_ENTRY:
            raise ApiError(ErrorCode.JOIN_LOGIN_ID_TAKEN) from None
        raise
    for site_conts_sn, content_hash in accepted:
        db.execute(
            insert(TB_MBR_AGRE_HSTRY).values(
                OPER_BNDL_SN=bundle_sn,
                MBR_SN=member_sn,
                SITE_CONTS_SN=site_conts_sn,
                AGRE_ACT_CD="AA.AGREE",
                AGRE_DT=now,
                CONTS_HASH_VL=content_hash,
                IDEM_KEY=f"join-{cert_sn}-{site_conts_sn}",
            )
        )
    mark_used(db, cert_sn, now)  # 가입 확정과 같은 트랜잭션에서 사용 완료로 표시한다
    record_job(
        db,
        actor="AK.MEMBER",
        job="MEMBER_JOIN",
        table="TB_MBR",
        key=member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="회원 가입(약관 동의 포함)",
    )
    return Joined(member_sn, str(name), login_id)
