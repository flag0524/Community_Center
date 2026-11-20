# 로그인 세션 저장·조회·갱신·폐기(TB_LGN_SSN). 토큰 원문은 저장하지 않고 해시만 둔다(AUTH-03·05, ADR-008)
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from app.auth.tokens import hash_token, new_token
from app.db.tables import TB_LGN_SSN

Kind = Literal["member", "admin"]
MEMBER_IDLE_SECONDS = 30 * 60  # 회원 유휴 30분(AUTH-05)
ADMIN_IDLE_SECONDS = 15 * 60  # 관리자 유휴 15분(RQ-SER-NF-008)
# 절대 만료. 유휴 연장만으로는 탈취된 세션을 무기한 쓸 수 있어 발급 시각 기준 상한을 둔다
# (코드 리뷰 보안 중-3, 사용자 확정 2026-11-20). 이 시간이 지나면 활동 중이어도 다시 로그인한다
MEMBER_ABSOLUTE_SECONDS = 12 * 3600
ADMIN_ABSOLUTE_SECONDS = 8 * 3600
# 마지막 갱신에서 이 시간이 지나지 않았으면 세션 행을 다시 쓰지 않는다. 요청마다 쓰면 같은 화면의
# 병렬 요청이 세션 행 잠금에서 줄을 서고 쓰기 부하가 늘어난다. 유휴 만료는 최대 이 시간만큼 일찍 온다
TOUCH_MIN_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True)
class SessionRecord:
    session_sn: int
    bundle_sn: int | None
    member_sn: int | None
    admin_sn: int | None
    token_hash: str
    last_activity: datetime
    expires_at: datetime
    issued_at: datetime


def idle_seconds(kind: Kind) -> int:
    return MEMBER_IDLE_SECONDS if kind == "member" else ADMIN_IDLE_SECONDS


def absolute_seconds(kind: Kind) -> int:
    return MEMBER_ABSOLUTE_SECONDS if kind == "member" else ADMIN_ABSOLUTE_SECONDS


def issue_session(
    db: Session, *, bundle_sn: int | None, member_sn: int | None, admin_sn: int | None, now: datetime
) -> tuple[str, SessionRecord]:
    """(쿠키로 보낼 토큰 원문, 저장된 세션). 회원 또는 관리자 중 정확히 한 대상만 연결한다(AUTH-05)."""
    if (member_sn is None) == (admin_sn is None):
        raise ValueError("세션 대상은 회원 또는 관리자 중 정확히 하나여야 한다")
    if member_sn is not None and bundle_sn is None:
        raise ValueError("회원 세션에는 운영묶음이 필요하다")
    kind: Kind = "member" if member_sn is not None else "admin"
    token = new_token()
    token_hash = hash_token(token)
    expires_at = now + timedelta(seconds=idle_seconds(kind))
    serial = db.execute(
        insert(TB_LGN_SSN)
        .values(
            OPER_BNDL_SN=bundle_sn,
            MBR_SN=member_sn,
            MNGR_SN=admin_sn,
            TKN_HASH_VL=token_hash,
            ISSU_DT=now,
            LAST_ACT_DT=now,
            EXPRY_DT=expires_at,
        )
        .returning(TB_LGN_SSN.c.LGN_SSN_SN)
    ).scalar_one()
    return token, SessionRecord(int(serial), bundle_sn, member_sn, admin_sn, token_hash, now, expires_at, now)


def find_active(db: Session, token: str | None, kind: Kind, now: datetime) -> SessionRecord | None:
    """폐기되지 않았고 유휴·절대 만료 전이며 종류가 맞는 세션만 돌려준다. 만료는 매번 검사한다."""
    if not token:
        return None
    subject = TB_LGN_SSN.c.MBR_SN if kind == "member" else TB_LGN_SSN.c.MNGR_SN
    row = db.execute(
        select(
            TB_LGN_SSN.c.LGN_SSN_SN,
            TB_LGN_SSN.c.OPER_BNDL_SN,
            TB_LGN_SSN.c.MBR_SN,
            TB_LGN_SSN.c.MNGR_SN,
            TB_LGN_SSN.c.TKN_HASH_VL,
            TB_LGN_SSN.c.LAST_ACT_DT,
            TB_LGN_SSN.c.EXPRY_DT,
            TB_LGN_SSN.c.ISSU_DT,
        ).where(
            TB_LGN_SSN.c.TKN_HASH_VL == hash_token(token),
            TB_LGN_SSN.c.DSCD_DT.is_(None),
            TB_LGN_SSN.c.EXPRY_DT > now,
            TB_LGN_SSN.c.ISSU_DT > now - timedelta(seconds=absolute_seconds(kind)),
            subject.is_not(None),
        )
    ).first()
    if row is None:
        return None
    return SessionRecord(
        int(row.LGN_SSN_SN),
        None if row.OPER_BNDL_SN is None else int(row.OPER_BNDL_SN),
        None if row.MBR_SN is None else int(row.MBR_SN),
        None if row.MNGR_SN is None else int(row.MNGR_SN),
        str(row.TKN_HASH_VL),
        row.LAST_ACT_DT,
        row.EXPRY_DT,
        row.ISSU_DT,
    )


def touch(
    db: Session, record: SessionRecord, kind: Kind, now: datetime, *, force: bool = False
) -> SessionRecord:
    """사용자 조작이 있을 때만 부른다. 유휴 시간을 처음부터 다시 세되 발급 기준 절대 상한을 넘지 않는다.

    마지막 갱신에서 30초가 지나지 않았으면 쓰지 않는다. 사용자가 직접 연장을 누른 경우는 force로 항상 쓴다.
    """
    if not force and now - record.last_activity < TOUCH_MIN_INTERVAL:
        return record
    expires_at = min(
        now + timedelta(seconds=idle_seconds(kind)),
        record.issued_at + timedelta(seconds=absolute_seconds(kind)),
    )
    db.execute(
        update(TB_LGN_SSN)
        .where(TB_LGN_SSN.c.LGN_SSN_SN == record.session_sn)
        .values(LAST_ACT_DT=now, EXPRY_DT=expires_at)
    )
    return SessionRecord(
        record.session_sn,
        record.bundle_sn,
        record.member_sn,
        record.admin_sn,
        record.token_hash,
        now,
        expires_at,
        record.issued_at,
    )


def discard(db: Session, session_sn: int, reason: str, now: datetime) -> None:
    db.execute(
        update(TB_LGN_SSN)
        .where(TB_LGN_SSN.c.LGN_SSN_SN == session_sn, TB_LGN_SSN.c.DSCD_DT.is_(None))
        .values(DSCD_DT=now, DSCD_RSN=reason)
    )


def discard_all(
    db: Session, *, member_sn: int | None = None, admin_sn: int | None = None, reason: str, now: datetime
) -> int:
    """계정 제한·비밀번호 재설정·권한 회수 때 그 계정의 살아 있는 세션을 모두 폐기한다(AUTH-05)."""
    column = TB_LGN_SSN.c.MBR_SN if member_sn is not None else TB_LGN_SSN.c.MNGR_SN
    result = db.execute(
        update(TB_LGN_SSN)
        .where(column == (member_sn if member_sn is not None else admin_sn), TB_LGN_SSN.c.DSCD_DT.is_(None))
        .values(DSCD_DT=now, DSCD_RSN=reason)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]
