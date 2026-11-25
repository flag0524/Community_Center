# 아이디 찾기와 비밀번호 재설정. 인증(OTP) 소비와 업무 변경을 한 트랜잭션으로 확정한다(TDD 8.1, AUTH-05)
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.otp import consume_otp, mark_used, reject_after_failure
from app.auth.passwords import hash_password
from app.auth.sessions import discard_all
from app.core.config import Settings
from app.core.masking import mask_login_id
from app.db.tables import TB_MBR
from app.domain.member.types import OtpPurpose


def find_login_id(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    cert_id: str,
    code: str,
    request_id: str,
    now: datetime,
) -> str | None:
    """일치하는 회원이 있으면 마스킹한 아이디를, 없으면 None을 돌려준다(FN-061)."""
    row = consume_otp(
        db, settings, cert_id=cert_id, code=code, purpose=OtpPurpose.ID_FIND, bundle_sn=bundle_sn, now=now
    )
    mark_used(db, int(row.CERT_DMND_SN), now)
    if row.MBR_SN is None:  # 가짜 인증(회원이 없는 대상). 실제와 같은 모양으로 비어 있다고만 답한다
        return None
    login_id = db.execute(select(TB_MBR.c.LGN_ID).where(TB_MBR.c.MBR_SN == row.MBR_SN)).scalar_one()
    record_job(
        db,
        actor="AK.MEMBER",
        job="ID_FIND",
        table="TB_MBR",
        key=int(row.MBR_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=int(row.MBR_SN),
        change="아이디 찾기(마스킹된 값만 노출)",
    )
    return mask_login_id(str(login_id))


def reset_password(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    cert_id: str,
    code: str,
    login_id: str,
    new_password: str,
    request_id: str,
    now: datetime,
) -> bool:
    """성공하면 True. 인증된 회원의 아이디와 입력한 아이디가 다르면 인증이 무효인 것처럼 거절한다."""
    row = consume_otp(
        db,
        settings,
        cert_id=cert_id,
        code=code,
        purpose=OtpPurpose.PASSWORD_RESET,
        bundle_sn=bundle_sn,
        now=now,
    )
    stored = (
        None
        if row.MBR_SN is None
        else db.execute(select(TB_MBR.c.LGN_ID).where(TB_MBR.c.MBR_SN == row.MBR_SN)).scalar_one()
    )
    if stored is None or str(stored) != login_id:
        raise reject_after_failure(db, row)
    member_sn = int(row.MBR_SN)
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member_sn)
        .values(PSWD_HASH_VL=hash_password(new_password, settings.pbkdf2_iterations))
    )
    mark_used(db, int(row.CERT_DMND_SN), now)
    discard_all(db, member_sn=member_sn, reason="PASSWORD_RESET", now=now)  # 기존 로그인은 모두 끊는다
    record_job(
        db,
        actor="AK.MEMBER",
        job="PASSWORD_RESET",
        table="TB_MBR",
        key=member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="비밀번호 재설정(값은 기록하지 않음)",
    )
    return True
