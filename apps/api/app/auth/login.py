# 회원·관리자 로그인. 실패 이력과 잠금은 응답이 오류여도 남아야 하므로 오류를 내기 전에 커밋한다(AUTH-04)
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.auth.passwords import dummy_hash, verify_password
from app.auth.sessions import SessionRecord, issue_session
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_LGN_FAIL_HSTRY, TB_MBR, TB_MNGR

MEMBER_FAIL_WINDOW = timedelta(minutes=10)  # 직전 10분 안의 실패만 센다(AUTH-04)
MEMBER_MAX_FAILURES = 5
MEMBER_LOCK = timedelta(minutes=15)


@dataclass(frozen=True)
class LoggedIn:
    token: str
    record: SessionRecord
    name: str
    login_id: str
    subject_sn: int


def _count_failures(db: Session, column: object, subject_sn: int, since: datetime) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(TB_LGN_FAIL_HSTRY)
            .where(column == subject_sn, TB_LGN_FAIL_HSTRY.c.FAIL_DT >= since)  # type: ignore[arg-type]
        ).scalar_one()
    )


def _fail_closed(db: Session, error: ErrorCode) -> ApiError:
    """실패 이력·잠금을 먼저 확정한다. get_db는 예외가 나면 되돌리므로 여기서 커밋하지 않으면 사라진다."""
    db.commit()
    return ApiError(error)


def member_login(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    login_id: str,
    password: str,
    request_id: str,
    now: datetime,
) -> LoggedIn:
    member = db.execute(
        select(
            TB_MBR.c.MBR_SN,
            TB_MBR.c.MBR_NM,
            TB_MBR.c.LGN_ID,
            TB_MBR.c.PSWD_HASH_VL,
            TB_MBR.c.MBR_STTS_CD,
            TB_MBR.c.LCK_END_DT,
        )
        .where(TB_MBR.c.OPER_BNDL_SN == bundle_sn, TB_MBR.c.LGN_ID == login_id)
        .with_for_update()  # 같은 계정의 동시 실패가 서로의 횟수를 덮어쓰지 않게 계정 행을 잠근다
    ).first()
    if member is None or member.MBR_STTS_CD == "MS.WITHDRAW":
        # 없는 아이디·탈퇴 계정도 같은 계산을 하고 같은 응답을 준다. 실패 이력은 남기지 않는다.
        verify_password(password, dummy_hash(settings.pbkdf2_iterations))
        raise ApiError(ErrorCode.LOGIN_FAILED)
    member_sn = int(member.MBR_SN)
    if member.MBR_STTS_CD == "MS.LOCKED" or (member.LCK_END_DT is not None and member.LCK_END_DT > now):
        raise ApiError(ErrorCode.LOGIN_LOCKED)
    if not verify_password(password, str(member.PSWD_HASH_VL)):
        db.execute(
            insert(TB_LGN_FAIL_HSTRY).values(
                OPER_BNDL_SN=bundle_sn, MBR_SN=member_sn, FAIL_DT=now, DMND_ID=request_id
            )
        )
        failures = _count_failures(db, TB_LGN_FAIL_HSTRY.c.MBR_SN, member_sn, now - MEMBER_FAIL_WINDOW)
        locked = failures >= MEMBER_MAX_FAILURES
        db.execute(
            update(TB_MBR)
            .where(TB_MBR.c.MBR_SN == member_sn)
            .values(PSWD_FAIL_NMTM=failures, LCK_END_DT=now + MEMBER_LOCK if locked else None)
        )
        raise _fail_closed(db, ErrorCode.LOGIN_LOCKED if locked else ErrorCode.LOGIN_FAILED)
    db.execute(
        update(TB_MBR)
        .where(TB_MBR.c.MBR_SN == member_sn)
        .values(PSWD_FAIL_NMTM=0, LCK_END_DT=None, RCNT_LGN_DT=now)
    )
    token, record = issue_session(db, bundle_sn=bundle_sn, member_sn=member_sn, admin_sn=None, now=now)
    return LoggedIn(token, record, str(member.MBR_NM), str(member.LGN_ID), member_sn)


def admin_login(
    db: Session, settings: Settings, *, login_id: str, password: str, request_id: str, now: datetime
) -> LoggedIn:
    admin = db.execute(
        select(
            TB_MNGR.c.MNGR_SN,
            TB_MNGR.c.MNGR_NM,
            TB_MNGR.c.LGN_ID,
            TB_MNGR.c.PSWD_HASH_VL,
            TB_MNGR.c.USE_YN,
            TB_MNGR.c.LCK_END_DT,
        )
        .where(TB_MNGR.c.LGN_ID == login_id)
        .with_for_update()
    ).first()
    if admin is None or admin.USE_YN != "Y":
        verify_password(password, dummy_hash(settings.pbkdf2_iterations))
        raise ApiError(ErrorCode.LOGIN_FAILED)
    admin_sn = int(admin.MNGR_SN)
    if admin.LCK_END_DT is not None and admin.LCK_END_DT > now:
        raise ApiError(ErrorCode.LOGIN_LOCKED)
    if not verify_password(password, str(admin.PSWD_HASH_VL)):
        db.execute(insert(TB_LGN_FAIL_HSTRY).values(MNGR_SN=admin_sn, FAIL_DT=now, DMND_ID=request_id))
        locked = False
        if settings.admin_lock_failures is not None and settings.admin_lock_minutes is not None:
            window = timedelta(minutes=settings.admin_lock_minutes)
            failures = _count_failures(db, TB_LGN_FAIL_HSTRY.c.MNGR_SN, admin_sn, now - window)
            locked = failures >= settings.admin_lock_failures
            db.execute(
                update(TB_MNGR)
                .where(TB_MNGR.c.MNGR_SN == admin_sn)
                .values(PSWD_FAIL_NMTM=failures, LCK_END_DT=now + window if locked else None)
            )
        raise _fail_closed(db, ErrorCode.LOGIN_LOCKED if locked else ErrorCode.LOGIN_FAILED)
    db.execute(
        update(TB_MNGR)
        .where(TB_MNGR.c.MNGR_SN == admin_sn)
        .values(PSWD_FAIL_NMTM=0, LCK_END_DT=None, RCNT_LGN_DT=now)
    )
    token, record = issue_session(db, bundle_sn=None, member_sn=None, admin_sn=admin_sn, now=now)
    return LoggedIn(token, record, str(admin.MNGR_NM), str(admin.LGN_ID), admin_sn)
