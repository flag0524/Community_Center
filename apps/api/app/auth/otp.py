# 본인확인 OTP 발급·확인(TB_CERT_DMND). 인증번호 원문은 DB·로그에 두지 않고 검증값(HMAC)만 둔다(AUTH-02·03)
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.adapters.sms.base import SendOutcome, SmsSender
from app.auth.crypto import encrypt
from app.auth.tokens import derived_key, same
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_CERT_DMND, TB_MBR, TB_OPER_BNDL, TB_SMS_DMND, TB_SMS_SNDNG_HSTRY, TB_SMS_TRGT
from app.domain.member.types import OtpPurpose

OTP_VALID = timedelta(minutes=5)  # 유효 5분(AUTH-02)
RESEND_INTERVAL = timedelta(seconds=60)  # 재전송 60초
MAX_FAILURES = 5  # 입력 오류 5회 무효
KEY_VERSION = "v1"  # 검증값을 만든 비밀키의 버전. 키를 바꿀 때 옛 검증값을 구별한다
PURPOSE_CODES = {
    OtpPurpose.JOIN: "AP.JOIN",
    OtpPurpose.ID_FIND: "AP.ID_FIND",
    OtpPurpose.PASSWORD_RESET: "AP.PSWD",
}
MESSAGE_TEMPLATE = (
    "[{center}] 인증번호는 {{code}}입니다. 5분 안에 입력해 주세요."  # 코드 자리는 비워 둔다(OTP-SMS-01)
)
GATE_COOKIE = "jori_otp_gate"


@dataclass(frozen=True)
class Issued:
    cert_sn: int
    expires_at: datetime
    resend_available_at: datetime


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def code_hash(secret: str, cert_id: str, code: str) -> str:
    """인증번호 검증값. 요청 번호를 섞어 같은 코드도 요청마다 다른 값이 된다."""
    return hmac.new(derived_key(secret, "otp"), f"{cert_id}:{code}".encode(), hashlib.sha256).hexdigest()


# --- 재전송 제한용 서명 쿠키 ---------------------------------------------------------


def _epoch(moment: datetime) -> int:
    return int((moment - datetime(1970, 1, 1)).total_seconds())


def make_gate(secret: str, now: datetime) -> str:
    """직전 발급 시각을 서명해 쿠키에 둔다. 회원이 없는 가입 요청도 이 값으로 60초 제한을 건다(TDD 8.1)."""
    stamp = str(_epoch(now))
    signature = hmac.new(derived_key(secret, "otp-gate"), stamp.encode(), hashlib.sha256).hexdigest()
    return f"{stamp}.{signature}"


def gate_blocks(secret: str, value: str | None, now: datetime) -> bool:
    if not value or "." not in value:
        return False
    stamp, signature = value.split(".", 1)
    expected = hmac.new(derived_key(secret, "otp-gate"), stamp.encode(), hashlib.sha256).hexdigest()
    if not same(signature, expected) or not stamp.isdigit():
        return False  # 위조·손상된 값은 무시한다(제한을 우회하는 값이 아니라 아무것도 아닌 값)
    return _epoch(now) - int(stamp) < int(RESEND_INTERVAL.total_seconds())


# --- 대상 찾기 -----------------------------------------------------------------------


def _find_member(
    db: Session, bundle_sn: int, purpose: OtpPurpose, phone: str, name: str | None, login_id: str | None
) -> int | None:
    """아이디 찾기·비밀번호 재설정의 대상 회원. 일치하는 정상 회원이 없으면 None이다."""
    conditions = [
        TB_MBR.c.OPER_BNDL_SN == bundle_sn,
        TB_MBR.c.MBL_TELNO == phone,
        TB_MBR.c.MBR_STTS_CD != "MS.WITHDRAW",
    ]
    if purpose is OtpPurpose.ID_FIND:
        if not name:
            raise ApiError(ErrorCode.VALIDATION_FAILED, fields={"name": "이름을 입력해 주세요."})
        conditions.append(TB_MBR.c.MBR_NM == name)
    else:
        if not login_id:
            raise ApiError(ErrorCode.VALIDATION_FAILED, fields={"loginId": "아이디를 입력해 주세요."})
        conditions.append(TB_MBR.c.LGN_ID == login_id)
        if name:
            conditions.append(TB_MBR.c.MBR_NM == name)
    found = db.execute(select(TB_MBR.c.MBR_SN).where(*conditions)).scalar_one_or_none()
    return None if found is None else int(found)


def _recently_issued(db: Session, member_sn: int, purpose_code: str, now: datetime) -> bool:
    latest = db.execute(
        select(func.max(TB_CERT_DMND.c.REG_DT)).where(
            TB_CERT_DMND.c.MBR_SN == member_sn, TB_CERT_DMND.c.CERT_PRPS_CD == purpose_code
        )
    ).scalar_one()
    return latest is not None and now - latest < RESEND_INTERVAL


# --- 발급 ----------------------------------------------------------------------------


def issue_otp(
    db: Session,
    settings: Settings,
    sender: SmsSender,
    *,
    bundle_sn: int,
    purpose: OtpPurpose,
    phone: str,
    name: str | None,
    login_id: str | None,
    request_id: str,
    now: datetime,
) -> Issued:
    """인증 요청·문자 요청·수신 대상을 한 트랜잭션으로 커밋한 뒤, 메모리의 코드로 문자를 보낸다(TDD 8.1)."""
    if purpose not in PURPOSE_CODES:
        raise ApiError(ErrorCode.NOT_IMPLEMENTED)  # 전화번호 변경은 로그인한 회원의 프로필 기능에서 다룬다
    purpose_code = PURPOSE_CODES[purpose]
    if purpose is OtpPurpose.JOIN and not (name and name.strip()):
        # 가입 요청에는 이름이 없어서 인증 단계에서 받아 암호문에 담아 둔다
        raise ApiError(ErrorCode.VALIDATION_FAILED, fields={"name": "이름을 입력해 주세요."})
    target = (
        None if purpose is OtpPurpose.JOIN else _find_member(db, bundle_sn, purpose, phone, name, login_id)
    )
    if target is not None and _recently_issued(db, target, purpose_code, now):
        raise ApiError(ErrorCode.OTP_RESEND_TOO_SOON)

    code = new_code()
    cert_id = uuid.uuid4().hex
    # 가입 단계의 이름은 암호문 안에 함께 넣어 둔다. 인증 테이블에 이름 컬럼이 없고 가입 요청에도 이름이 없다.
    payload = json.dumps({"p": phone, "n": name}, ensure_ascii=False)
    cert_sn = db.execute(
        insert(TB_CERT_DMND)
        .values(
            OPER_BNDL_SN=bundle_sn,
            MBR_SN=target,
            CERT_DMND_ID=cert_id,
            CERT_PRPS_CD=purpose_code,
            TELNO_ENCPT_VL=encrypt(settings.secret_key, payload),
            OTP_HASH_VL=code_hash(settings.secret_key, cert_id, code),
            KEY_VER_ID=KEY_VERSION,
            REG_DT=now,  # 재전송 제한이 REG_DT로 판정하므로 만료(EXPRY_DT)와 같은 앱 시계로 맞춘다
            EXPRY_DT=now + OTP_VALID,
            IDEM_KEY=f"otp-{request_id}",
        )
        .returning(TB_CERT_DMND.c.CERT_DMND_SN)
    ).scalar_one()
    cert_sn = int(cert_sn)
    issued = Issued(cert_sn, now + OTP_VALID, now + RESEND_INTERVAL)

    # 일치하는 회원이 없으면 문자는 보내지 않고 인증 행만 남긴다. 확인도 같은 모양으로 실패해
    # 회원 존재를 알 수 없다(FN-061).
    if purpose is not OtpPurpose.JOIN and target is None:
        return issued

    center = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_NM).where(TB_OPER_BNDL.c.OPER_BNDL_SN == bundle_sn)
    ).scalar_one()
    template = MESSAGE_TEMPLATE.format(center=center)
    dmnd_sn = db.execute(
        insert(TB_SMS_DMND)
        .values(
            OPER_BNDL_SN=bundle_sn,
            DMND_TYPE_CD="SM.AUTO",
            TRGT_TYPE_CD="SG.EVENT",
            DSPTCH_TELNO=settings.sms_sender_number,
            SMS_CN=template,
            IDEM_KEY=f"otp-{request_id}",
            DMND_HASH_VL=hashlib.sha256(template.encode()).hexdigest(),
            SRC_EVENT_ID=f"CERT:{cert_sn}",
        )
        .returning(TB_SMS_DMND.c.SMS_DMND_SN)
    ).scalar_one()
    trgt_sn = db.execute(
        insert(TB_SMS_TRGT)
        .values(
            OPER_BNDL_SN=bundle_sn,
            SMS_DMND_SN=dmnd_sn,
            MBR_SN=target,
            CERT_DMND_SN=cert_sn if target is None else None,  # 가입은 회원이 없어 인증 요청에 연결한다
            RCPTN_TELNO_ENCPT_VL=encrypt(settings.secret_key, phone),
        )
        .returning(TB_SMS_TRGT.c.SMS_TRGT_SN)
    ).scalar_one()
    db.commit()  # 문자를 보내기 전에 요청을 확정한다. 공급자 호출을 잠금·트랜잭션 안에서 하지 않는다

    result = sender.send(to=phone, text=template.replace("{code}", code), sender=settings.sms_sender_number)
    status = {
        SendOutcome.ACCEPTED: "SS.SENDING",
        SendOutcome.REJECTED: "SS.FAIL",
        SendOutcome.UNKNOWN: "SS.UNKNOWN",
    }[result.outcome]
    db.execute(
        insert(TB_SMS_SNDNG_HSTRY).values(
            OPER_BNDL_SN=bundle_sn,
            SMS_TRGT_SN=trgt_sn,
            SNDNG_SEQ=1,
            SPLR_NM=sender.provider_name,
            SPLR_ACNT_ID=sender.provider_name,
            SPLR_MSG_ID=result.message_id,
            IDEM_KEY=f"otp-{request_id}",
            PRCS_STTS_CD=status,
            SNDNG_DMND_DT=now,
            FAIL_CD=result.failure_code,
        )
    )
    db.execute(update(TB_SMS_TRGT).where(TB_SMS_TRGT.c.SMS_TRGT_SN == trgt_sn).values(TRGT_STTS_CD=status))
    if result.outcome is SendOutcome.REJECTED:
        db.commit()  # 실패 기록은 오류 응답과 함께 사라지지 않게 먼저 확정한다. 자동으로 다시 보내지 않는다
        raise ApiError(ErrorCode.INTERNAL_ERROR)
    return issued


# --- 확인 ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Verification:
    verified: bool
    remaining_attempts: int | None


def load_for_update(db: Session, cert_sn: int) -> Any:
    return db.execute(
        select(
            TB_CERT_DMND.c.CERT_DMND_SN,
            TB_CERT_DMND.c.CERT_DMND_ID,
            TB_CERT_DMND.c.OPER_BNDL_SN,
            TB_CERT_DMND.c.MBR_SN,
            TB_CERT_DMND.c.CERT_PRPS_CD,
            TB_CERT_DMND.c.TELNO_ENCPT_VL,
            TB_CERT_DMND.c.OTP_HASH_VL,
            TB_CERT_DMND.c.EXPRY_DT,
            TB_CERT_DMND.c.CERT_USE_CMPTN_DT,
            TB_CERT_DMND.c.FAIL_NMTM,
        )
        .where(TB_CERT_DMND.c.CERT_DMND_SN == cert_sn)
        .with_for_update()  # 성공·실패 횟수 갱신을 원자적으로 한다(AUTH-02)
    ).first()


def check_code(db: Session, settings: Settings, row: Any, code: str, now: datetime) -> Verification:
    """잠근 인증 행의 코드를 검사한다. 틀리면 실패 횟수를 올린다. 무효·만료는 오류로 올린다."""
    if row is None or row.CERT_USE_CMPTN_DT is not None or int(row.FAIL_NMTM) >= MAX_FAILURES:
        raise ApiError(ErrorCode.OTP_INVALID)
    if now >= row.EXPRY_DT:
        raise ApiError(ErrorCode.OTP_EXPIRED)
    expected = code_hash(settings.secret_key, str(row.CERT_DMND_ID), code)
    if same(expected, str(row.OTP_HASH_VL)):
        return Verification(True, None)
    failures = int(row.FAIL_NMTM) + 1
    db.execute(
        update(TB_CERT_DMND).where(TB_CERT_DMND.c.CERT_DMND_SN == row.CERT_DMND_SN).values(FAIL_NMTM=failures)
    )
    return Verification(False, max(MAX_FAILURES - failures, 0))


def verify_otp(db: Session, settings: Settings, *, cert_sn: int, code: str, now: datetime) -> Verification:
    """일치 여부만 확인한다. 사용 완료로 표시하지 않는다(최종 업무 API가 다시 검증하고 표시한다)."""
    return check_code(db, settings, load_for_update(db, cert_sn), code, now)


def consume_otp(
    db: Session,
    settings: Settings,
    *,
    cert_sn: int,
    code: str,
    purpose: OtpPurpose,
    bundle_sn: int,
    now: datetime,
) -> Any:
    """업무 확정 API가 인증을 소비하기 전에 다시 검증한다. 인증 행을 잠근 채 돌려주므로 같은 트랜잭션에서
    사용 완료(mark_used)와 업무 변경을 함께 확정한다. 틀린 코드는 횟수를 올리고 커밋한 뒤 거절한다."""
    row = load_for_update(db, cert_sn)
    if row is not None and (row.CERT_PRPS_CD != PURPOSE_CODES[purpose] or int(row.OPER_BNDL_SN) != bundle_sn):
        row = None  # 다른 목적·다른 묶음의 인증은 없는 것과 같다
    if not check_code(db, settings, row, code, now).verified:
        db.commit()  # 실패 횟수가 오류 응답과 함께 사라지지 않게 먼저 확정한다
        raise ApiError(ErrorCode.OTP_INVALID)
    return row


def reject_after_failure(db: Session, row: Any) -> ApiError:
    """코드는 맞았지만 다른 조건이 틀려도 실패로 센다. 맞는 코드로 다른 값을 계속 시험하지 못하게 한다."""
    db.execute(
        update(TB_CERT_DMND)
        .where(TB_CERT_DMND.c.CERT_DMND_SN == row.CERT_DMND_SN)
        .values(FAIL_NMTM=int(row.FAIL_NMTM) + 1)
    )
    db.commit()
    return ApiError(ErrorCode.OTP_INVALID)


def mark_used(db: Session, cert_sn: int, now: datetime) -> None:
    db.execute(
        update(TB_CERT_DMND).where(TB_CERT_DMND.c.CERT_DMND_SN == cert_sn).values(CERT_USE_CMPTN_DT=now)
    )
