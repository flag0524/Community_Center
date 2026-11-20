# 로그인한 회원 본인의 정보 조회·수정, 비밀번호 변경, 탈퇴(진행 중인 신청·결제·환불이 있으면 거절). 회원 번호는 세션에서만 온다(ADR-075)
from datetime import datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.deps import Member
from app.auth.member_phone import reveal
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import discard
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.masking import mask_phone
from app.core.times import kst_today
from app.db.tables import TB_ATNLC_APLY, TB_LGN_SSN, TB_MBR, TB_RFND, TB_STLM
from app.domain.member.schemas import MemberProfile, PasswordChange, ProfileUpdate, WithdrawalRequest
from app.domain.member.types import ResidenceStatus

# 자리를 쥐고 있는 신청, 결과를 모르는 결제, 처리 중인 환불이 하나라도 있으면 탈퇴할 수 없다
WAITING_APPLICATIONS = ("ES.WAIT", "ES.HOLD")
UNKNOWN_PAYMENT = "PS.PENDING"
OPEN_REFUNDS = ("RS.REQUEST", "RS.HOLD", "RS.APPROVE", "RS.PENDING")


def _lock(db: Session, member: Member) -> object:
    """회원 행을 잠근다. 신청 생성도 이 행을 잠그므로 탈퇴 검사 뒤에 새 신청이 끼어들지 못한다."""
    row = db.execute(
        select(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member.member_sn, TB_MBR.c.OPER_BNDL_SN == member.bundle_sn)
        .with_for_update()
    ).first()
    if row is None or str(row.MBR_STTS_CD).strip() != "MS.ACTIVE":
        raise ApiError(ErrorCode.UNAUTHENTICATED)  # 잠금을 기다리는 사이 탈퇴·제한이 끝났을 수 있다
    return row


def _profile(settings: Settings, row: object) -> MemberProfile:
    return MemberProfile(
        member_id=str(row.MBR_SN),  # type: ignore[attr-defined]
        name=str(row.MBR_NM),  # type: ignore[attr-defined]
        login_id=str(row.LGN_ID),  # type: ignore[attr-defined]
        email=row.EML_ADDR,  # type: ignore[attr-defined]
        phone_masked=mask_phone(reveal(settings.secret_key, row.MBL_TELNO_ENCPT_VL)) or None,  # type: ignore[attr-defined]
        joined_on=kst_today(row.MBR_JOIN_DT),  # type: ignore[attr-defined]
        residence_declared=None,  # 회원이 입력한 거주 구분을 담는 컬럼이 없다(개정 요청 R10·R33)
        residence_status=ResidenceStatus.VERIFIED
        if str(row.HAB_IDNTY_STTS_CD).strip() == "RV.OK"  # type: ignore[attr-defined]
        else ResidenceStatus.UNVERIFIED,
    )


def get_profile(db: Session, settings: Settings, member: Member) -> MemberProfile:
    row = db.execute(
        select(TB_MBR).where(TB_MBR.c.MBR_SN == member.member_sn, TB_MBR.c.OPER_BNDL_SN == member.bundle_sn)
    ).first()
    if row is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED)
    return _profile(settings, row)


def update_profile(
    db: Session, settings: Settings, member: Member, body: ProfileUpdate, *, request_id: str, now: datetime
) -> MemberProfile:
    """이메일만 저장한다. 거주지역 값은 저장할 곳이 없어 받아도 버리고, 센터 확인 거주구분은 건드리지 않는다."""
    _lock(db, member)
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member.member_sn)
        .values(EML_ADDR=body.email, RCRD_VER=TB_MBR.c.RCRD_VER + 1, MDFCN_DT=now)
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="PROFILE_UPDATE",
        table="TB_MBR",
        key=member.member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=member.bundle_sn,
        member_sn=member.member_sn,
        change="이메일 변경(값은 기록하지 않음)",
    )
    return get_profile(db, settings, member)


def _check_password(row: object, password: str, field: str) -> None:
    if not verify_password(password, str(row.PSWD_HASH_VL)):  # type: ignore[attr-defined]
        raise ApiError(ErrorCode.VALIDATION_FAILED, fields={field: "비밀번호가 맞지 않습니다."})


def change_password(
    db: Session, settings: Settings, member: Member, body: PasswordChange, *, request_id: str, now: datetime
) -> None:
    """현재 비밀번호가 맞아야 바꾼다. 이 세션만 남기고 같은 회원의 다른 세션은 끊는다."""
    row = _lock(db, member)
    _check_password(row, body.current_password, "currentPassword")
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member.member_sn)
        .values(
            PSWD_HASH_VL=hash_password(body.new_password, settings.pbkdf2_iterations),
            RCRD_VER=TB_MBR.c.RCRD_VER + 1,
            MDFCN_DT=now,
        )
    )
    db.execute(
        update(TB_LGN_SSN)
        .where(
            TB_LGN_SSN.c.MBR_SN == member.member_sn,
            TB_LGN_SSN.c.DSCD_DT.is_(None),
            TB_LGN_SSN.c.LGN_SSN_SN != member.record.session_sn,
        )
        .values(DSCD_DT=now, DSCD_RSN="PASSWORD_CHANGE")
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="PASSWORD_CHANGE",
        table="TB_MBR",
        key=member.member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=member.bundle_sn,
        member_sn=member.member_sn,
        change="비밀번호 변경(값은 기록하지 않음)",
    )


def _has_open_work(db: Session, member_sn: int) -> bool:
    mine = TB_ATNLC_APLY.c.MBR_SN == member_sn
    waiting = exists().where(mine, TB_ATNLC_APLY.c.APLY_STTS_CD.in_(WAITING_APPLICATIONS))
    unknown = exists().where(
        TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        TB_STLM.c.STLM_STTS_CD == UNKNOWN_PAYMENT,
    )
    refunding = exists().where(
        TB_RFND.c.STLM_SN == TB_STLM.c.STLM_SN,
        TB_STLM.c.ATNLC_APLY_SN == TB_ATNLC_APLY.c.ATNLC_APLY_SN,
        TB_RFND.c.RFND_STTS_CD.in_(OPEN_REFUNDS),
    )
    found = db.execute(
        select(func.count()).select_from(TB_ATNLC_APLY).where(mine, waiting | unknown | refunding)
    ).scalar()
    return bool(found)


def withdraw(db: Session, member: Member, body: WithdrawalRequest, *, request_id: str, now: datetime) -> None:
    """비밀번호를 다시 확인하고 진행 중인 일이 없을 때만 탈퇴로 바꾼다. 개인정보는 보존기간 뒤 파기 대상이 된다."""
    row = _lock(db, member)
    _check_password(row, body.password, "password")
    if _has_open_work(db, member.member_sn):
        raise ApiError(
            ErrorCode.RULE_REJECTED,
            "진행 중인 신청·결제·환불이 있어 탈퇴할 수 없습니다. 처리가 끝난 뒤 다시 시도해 주세요.",
        )
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member.member_sn)
        .values(MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=now, RCRD_VER=TB_MBR.c.RCRD_VER + 1, MDFCN_DT=now)
    )
    # 다른 세션 행은 건드리지 않는다. 탈퇴 회원은 active_member 검사로 모든 세션이 거절되고, 건드리면 세션 행을 쥔 다른 요청과 교착한다
    discard(db, member.record.session_sn, "WITHDRAW", now)
    reason = "" if body.reason is None else f" 사유 {body.reason.value}"
    record_job(
        db,
        actor="AK.MEMBER",
        job="WITHDRAW",
        table="TB_MBR",
        key=member.member_sn,
        request_id=request_id,
        now=now,
        bundle_sn=member.bundle_sn,
        member_sn=member.member_sn,
        change=f"회원 탈퇴{reason}",
    )
