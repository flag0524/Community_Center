# 신청 금액 산정과 감면 적용 가능 여부 판정(FN-038, 039). 금액은 서버가 계산하며 요청 값은 쓰지 않는다
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, insert, select
from sqlalchemy.orm import Session, aliased

from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_RDCT_BFHD_SRNG, TB_RDCT_HSTRY

REDUCTION_PERCENT = 50
REDUCTION_TYPES = ("DR.LIVELIHD", "DR.VETERAN", "DR.DISABLED")


REDUCTION_REASON = {  # 신청 행에 남기는 감면 사유. 증빙 내용이 아니라 대상 유형만 적는다
    "DR.LIVELIHD": "기초생활보장 수급자 본인 사전심사 승인",
    "DR.VETERAN": "국가유공자 본인 사전심사 승인",
    "DR.DISABLED": "등록 장애인 본인 사전심사 승인",
}


@dataclass(frozen=True)
class Approval:
    """적용할 사전심사 승인. 신청 행의 감면 사유·담당자와 감면 이력에 쓴다."""

    sn: int
    type_code: str
    reviewer_sn: int


@dataclass(frozen=True)
class Quote:
    fee: int
    reduction: int
    payable: int
    approval: Approval | None  # 적용한 사전심사 승인. 없으면 감면이 없다


def is_resident(member: Any) -> bool:
    """우선접수 대상. 센터가 거주지를 확인한 파주시 주민이다(RCPT-PRIOR-01)."""
    return member.HAB_IDNTY_STTS_CD == "RV.OK" and member.HAB_RGN_CD in ("RA.JORI", "RA.PAJU_ETC")


def _already_reduced(db: Session, bundle_sn: int, member_sn: int, cycle_sn: int) -> bool:
    """같은 기수에 감면을 적용한 신청이 있고 담당자가 해제하지 않았으면 참이다. 취소·환불로는 복구하지 않는다."""
    approve = aliased(TB_RDCT_HSTRY)
    release = aliased(TB_RDCT_HSTRY)
    applied = (
        select(approve.c.RDCT_HSTRY_SN)
        .join(
            TB_ATNLC_APLY,
            and_(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == approve.c.OPER_BNDL_SN,
                TB_ATNLC_APLY.c.ATNLC_APLY_SN == approve.c.ATNLC_APLY_SN,
            ),
        )
        .join(
            TB_CORS,
            and_(
                TB_CORS.c.OPER_BNDL_SN == TB_ATNLC_APLY.c.OPER_BNDL_SN,
                TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN,
            ),
        )
        .where(
            approve.c.OPER_BNDL_SN == bundle_sn,
            approve.c.DCSN_RSLT_CD == "DR.APPROVE",
            TB_ATNLC_APLY.c.MBR_SN == member_sn,
            TB_CORS.c.EDU_CYCL_SN == cycle_sn,
            ~exists().where(
                release.c.OPER_BNDL_SN == approve.c.OPER_BNDL_SN,
                release.c.ATNLC_APLY_SN == approve.c.ATNLC_APLY_SN,
                release.c.DCSN_RSLT_CD == "DR.REJECT",
                release.c.RDCT_HSTRY_SN > approve.c.RDCT_HSTRY_SN,
            ),
        )
    )
    return bool(db.execute(select(exists(applied))).scalar_one())


def find_usable_approval(db: Session, member: Any, cycle_sn: int, now: datetime) -> Approval | None:
    """회원·기수 단위로 승인된 사전심사 중 지금 쓸 수 있는 것의 번호(TDD 5.5)."""
    if member.HAB_RGN_CD != "RA.JORI" or member.HAB_IDNTY_STTS_CD != "RV.OK":
        return None
    approval = db.execute(
        select(
            TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN,
            TB_RDCT_BFHD_SRNG.c.RDCT_TYPE_CD,
            TB_RDCT_BFHD_SRNG.c.SRNG_MNGR_SN,
        )
        .where(
            TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == member.OPER_BNDL_SN,
            TB_RDCT_BFHD_SRNG.c.MBR_SN == member.MBR_SN,
            TB_RDCT_BFHD_SRNG.c.EDU_CYCL_SN == cycle_sn,
            TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD == "DS.APPROVED",
            TB_RDCT_BFHD_SRNG.c.RDCT_TYPE_CD.in_(REDUCTION_TYPES),
            (TB_RDCT_BFHD_SRNG.c.VLD_END_DT.is_(None)) | (TB_RDCT_BFHD_SRNG.c.VLD_END_DT > now),
        )
        .order_by(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN.desc())
        .limit(1)
    ).first()
    if approval is None or _already_reduced(db, int(member.OPER_BNDL_SN), int(member.MBR_SN), cycle_sn):
        return None
    return Approval(int(approval.RDCT_BFHD_SRNG_SN), str(approval.RDCT_TYPE_CD), int(approval.SRNG_MNGR_SN))


def quote(db: Session, member: Any, course: Any, now: datetime) -> Quote:
    """수강료 스냅샷, 감면(수강료의 50% 내림), 결제 예정액. 결제 예정액은 0 아래로 내려가지 않는다."""
    fee = int(course.TTCHG)
    approval = find_usable_approval(db, member, int(course.EDU_CYCL_SN), now)
    reduction = fee * REDUCTION_PERCENT // 100 if approval is not None else 0
    return Quote(fee=fee, reduction=reduction, payable=fee - reduction, approval=approval)


def has_applied(db: Session, bundle_sn: int, application_sn: int) -> bool:
    """이 신청에 감면 적용 이력이 이미 있는가."""
    found = select(TB_RDCT_HSTRY.c.RDCT_HSTRY_SN).where(
        TB_RDCT_HSTRY.c.OPER_BNDL_SN == bundle_sn,
        TB_RDCT_HSTRY.c.ATNLC_APLY_SN == application_sn,
        TB_RDCT_HSTRY.c.DCSN_RSLT_CD == "DR.APPROVE",
    )
    return bool(db.execute(select(exists(found))).scalar_one())


def record_applied(
    db: Session, bundle_sn: int, application_sn: int, amount: int, approval: Approval, now: datetime
) -> None:
    """감면 적용을 남긴다. 자리를 배정하는 순간에만 부른다(DV20). 이력은 INSERT만 한다.

    이 행이 있어야 같은 기수에 감면을 다시 쓰지 못하므로(RDCT-BFHD-02) 회원 행을 잠근 상태에서 판정하고 남긴다.
    """
    db.execute(
        insert(TB_RDCT_HSTRY).values(
            OPER_BNDL_SN=bundle_sn,
            ATNLC_APLY_SN=application_sn,
            DCSN_RSLT_CD="DR.APPROVE",
            RDCT_AMT=amount,
            DCSN_RSN=REDUCTION_REASON[approval.type_code],
            DCSN_MNGR_SN=approval.reviewer_sn,
            DCSN_DT=now,
            REG_DT=now,
            RDCT_BFHD_SRNG_SN=approval.sn,
        )
    )
