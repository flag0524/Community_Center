# 정원 집계, 강좌 행 잠금, 자리 반환 뒤 대기자 자동 승격(TDD 5.3, ADR-028, FN-035~037)
import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.crypto import encrypt
from app.core.config import Settings
from app.core.times import KST, kst_ymd, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_CORS,
    TB_MBR,
    TB_OPER_BNDL,
    TB_SMS_DMND,
    TB_SMS_TRGT,
    TB_STLM,
)
from app.domain.application.service import PAYMENT_WINDOW_SECONDS, SEAT_STATUSES
from app.domain.course.service import VISIBLE_STATUSES

LOST_ELIGIBILITY = "자격 상실"  # 승격 순서가 됐을 때 회원이 탈퇴·제한이면 신청을 이 사유로 취소한다


def count_by_status(db: Session, bundle_sn: int, course_sn: int, statuses: tuple[str, ...]) -> int:
    return int(
        db.execute(
            select(func.count()).where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
                TB_ATNLC_APLY.c.CORS_SN == course_sn,
                TB_ATNLC_APLY.c.APLY_STTS_CD.in_(statuses),
            )
        ).scalar_one()
    )


def next_wait_seq(db: Session, bundle_sn: int, course_sn: int) -> int:
    last = db.execute(
        select(func.max(TB_ATNLC_APLY.c.WTNG_SEQ)).where(
            TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
            TB_ATNLC_APLY.c.CORS_SN == course_sn,
            TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT",
        )
    ).scalar_one()
    return 1 if last is None else int(last) + 1


def lock_course(db: Session, bundle_sn: int, course_sn: int) -> Any:
    """잠금 순서는 강좌 → 회원 → 신청이다(C07). 정원 판정과 승격은 모두 이 잠금 아래에서 한다."""
    return db.execute(
        select(TB_CORS)
        .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn, TB_CORS.c.CORS_SN == course_sn)
        .with_for_update()
    ).first()


def promotion_allowed(course: Any, now: datetime) -> bool:
    """공개된 강좌이고 교육 시작일 전일 때만 승격한다(PRD Q16·Q18의 기본값). 접수가 끝나도 이어진다."""
    return course.CORS_STTS_CD in VISIBLE_STATUSES and kst_ymd(now) < str(course.EDU_BGNG_YMD)


def _message(center: str, course_name: str, link: str, deadline: datetime | None) -> str:
    """개인정보 없이 강좌명·기한·내역 링크만 담는다(FN-028)."""
    if deadline is None:
        return f"[{center}] '{course_name}' 수강이 확정되었습니다. 내역 확인: {link}"
    due = utc(deadline).astimezone(KST).strftime("%m월 %d일 %H시 %M분")
    return (
        f"[{center}] '{course_name}' 수강 자리가 배정되었습니다. {due}까지 결제해 주세요. 내역 확인: {link}"
    )


def _enqueue_promotion_sms(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    application_sn: int,
    member: Any,
    course: Any,
    deadline: datetime | None,
    now: datetime,
) -> bool:
    """승격 안내를 아웃박스에만 쌓는다. 실제 발송은 커밋 뒤 워커가 한다(FN-028). 번호가 없으면 쌓지 않는다."""
    if not member.MBL_TELNO:
        return False
    bundle = db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_NM, TB_OPER_BNDL.c.URL_ADDR).where(
            TB_OPER_BNDL.c.OPER_BNDL_SN == bundle_sn
        )
    ).one()
    link = f"{str(bundle.URL_ADDR).rstrip('/')}/me/applications/{application_sn}"
    text = _message(str(bundle.OPER_BNDL_NM), str(course.CORS_NM), link, deadline)
    # 같은 승격이 두 번 쌓이지 않게 (묶음, 유형, 사건 식별자)가 유일하다. 배정 시각까지 넣어 재신청과 구분한다.
    event_id = f"PROMO:{application_sn}:{now.isoformat()}"
    request_sn = db.execute(
        insert(TB_SMS_DMND)
        .values(
            OPER_BNDL_SN=bundle_sn,
            DMND_TYPE_CD="SM.AUTO",
            TRGT_TYPE_CD="SG.EVENT",
            DSPTCH_TELNO=settings.sms_sender_number,
            SMS_CN=text,
            IDEM_KEY=f"promo-{application_sn}-{now.isoformat()}",
            DMND_HASH_VL=hashlib.sha256(text.encode()).hexdigest(),
            SRC_EVENT_ID=event_id,
            REG_DT=now,
        )
        .returning(TB_SMS_DMND.c.SMS_DMND_SN)
    ).scalar_one()
    db.execute(
        insert(TB_SMS_TRGT).values(
            OPER_BNDL_SN=bundle_sn,
            SMS_DMND_SN=request_sn,
            MBR_SN=member.MBR_SN,
            RCPTN_TELNO_ENCPT_VL=encrypt(settings.secret_key, str(member.MBL_TELNO)),
            REG_DT=now,
        )
    )
    return True


def promote_waiters(
    db: Session, settings: Settings, course: Any, *, now: datetime, request_id: str
) -> list[int]:
    """빈자리마다 대기 순서가 가장 앞선 신청을 배정한다. 강좌 행을 잠근 상태에서만 부른다.

    승격된 신청 번호를 순서대로 돌려준다. 순서가 된 회원이 탈퇴·제한이면 취소하고 다음 대기자로 넘어간다.
    """
    bundle_sn, course_sn = int(course.OPER_BNDL_SN), int(course.CORS_SN)
    if not promotion_allowed(course, now):
        return []
    promoted: list[int] = []
    while count_by_status(db, bundle_sn, course_sn, SEAT_STATUSES) < int(course.RCRT_NOPE):
        waiter = db.execute(
            select(TB_ATNLC_APLY)
            .where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == bundle_sn,
                TB_ATNLC_APLY.c.CORS_SN == course_sn,
                TB_ATNLC_APLY.c.APLY_STTS_CD == "ES.WAIT",
            )
            .order_by(TB_ATNLC_APLY.c.WTNG_SEQ, TB_ATNLC_APLY.c.ATNLC_APLY_SN)
            .limit(1)
            .with_for_update()
        ).first()
        if waiter is None:
            break
        application_sn = int(waiter.ATNLC_APLY_SN)
        member = db.execute(
            select(TB_MBR.c.MBR_SN, TB_MBR.c.MBR_STTS_CD, TB_MBR.c.MBL_TELNO).where(
                TB_MBR.c.MBR_SN == waiter.MBR_SN
            )
        ).one()
        if member.MBR_STTS_CD != "MS.ACTIVE":
            set_status(db, application_sn, status="ES.CANCEL", now=now, reason=LOST_ELIGIBILITY)
            _log(
                db,
                "APLY_CANCEL",
                bundle_sn,
                application_sn,
                int(member.MBR_SN),
                request_id,
                now,
                "자격 상실로 취소",
            )
            continue
        free = int(waiter.STLM_PRNMNT_AMT) == 0
        deadline = None if free else now + timedelta(seconds=PAYMENT_WINDOW_SECONDS)
        set_status(
            db,
            application_sn,
            status="ES.CONFIRM" if free else "ES.HOLD",
            now=now,
            seat_at=now,
            deadline=deadline,
        )
        queued = _enqueue_promotion_sms(
            db,
            settings,
            bundle_sn=bundle_sn,
            application_sn=application_sn,
            member=member,
            course=course,
            deadline=deadline,
            now=now,
        )
        _log(
            db,
            "APLY_PROMOTE",
            bundle_sn,
            application_sn,
            int(member.MBR_SN),
            request_id,
            now,
            "대기에서 승격" + ("" if queued else "(수신번호 없어 문자 제외)"),
        )
        promoted.append(application_sn)
    return promoted


def set_status(
    db: Session,
    application_sn: int,
    *,
    status: str,
    now: datetime,
    reason: str | None = None,
    seat_at: datetime | None = None,
    deadline: datetime | None = None,
) -> None:
    """대기 신청의 상태를 바꾼다. 대기순서는 대기일 때만 있으므로 비운다(R10). 자리배정일시는 지우지 않는다."""
    values: dict[str, Any] = {
        "APLY_STTS_CD": status,
        "WTNG_SEQ": None,
        "MDFCN_DT": now,
        "RCRD_VER": TB_ATNLC_APLY.c.RCRD_VER + 1,
    }
    if status == "ES.CANCEL":
        values.update(RTRCN_DT=now, RTRCN_RSN=reason)
    elif status in ("ES.HOLD", "ES.CONFIRM"):  # 승격. 새 배정 시각과 기한을 기록한다
        values.update(SEAT_ALTMNT_DT=seat_at, STLM_DDLN_DT=deadline)
    # 만료는 배정 시각·기한을 그대로 둔다(SEAT-02)
    db.execute(update(TB_ATNLC_APLY).where(TB_ATNLC_APLY.c.ATNLC_APLY_SN == application_sn).values(**values))


def cancel_ready_payments(db: Session, bundle_sn: int, application_sn: int, now: datetime) -> None:
    """결제창만 발급된(승인 요청 전) 결제를 승인 전 취소로 바꾼다. 승인 결과를 기다리는 결제는 건드리지 않는다."""
    db.execute(
        update(TB_STLM)
        .where(
            TB_STLM.c.OPER_BNDL_SN == bundle_sn,
            TB_STLM.c.ATNLC_APLY_SN == application_sn,
            TB_STLM.c.STLM_STTS_CD == "PS.READY",
        )
        .values(STLM_STTS_CD="PS.CANCEL", MDFCN_DT=now, RCRD_VER=TB_STLM.c.RCRD_VER + 1)
    )


def expire_application(
    db: Session, settings: Settings, course: Any, application: Any, *, now: datetime, request_id: str
) -> list[int]:
    """결제기한이 지난 결제대기 신청을 만료시키고 자리를 돌려 대기자를 승격한다. 강좌 행 잠금 아래에서만 부른다.

    승인 결과를 기다리는 결제(PS.PENDING)가 있으면 자리를 지켜야 하므로 호출하는 쪽이 먼저 걸러야 한다(ADR-006).
    """
    bundle_sn, application_sn = int(application.OPER_BNDL_SN), int(application.ATNLC_APLY_SN)
    cancel_ready_payments(db, bundle_sn, application_sn, now)
    set_status(db, application_sn, status="ES.EXPIRE", now=now)
    _log(
        db,
        "APLY_EXPIRE",
        bundle_sn,
        application_sn,
        int(application.MBR_SN),
        request_id,
        now,
        "결제기한 만료",
    )
    return promote_waiters(db, settings, course, now=now, request_id=request_id)


def _log(
    db: Session,
    job: str,
    bundle_sn: int,
    application_sn: int,
    member_sn: int,
    request_id: str,
    now: datetime,
    change: str,
) -> None:
    # 시스템 작업은 회원·관리자를 비워야 한다(R21). 대상은 신청 번호로 추적한다.
    record_job(
        db,
        actor="AK.SYSTEM",
        job=job,
        table="TB_ATNLC_APLY",
        key=application_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        change=change,
    )
