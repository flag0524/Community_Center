# 신청 금액 산정과 감면 적용 가능 여부 판정(FN-038, 039). 금액은 서버가 계산하며 요청 값은 쓰지 않는다
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session, aliased

from app.db.tables import TB_ATNLC_APLY, TB_CORS, TB_RDCT_BFHD_SRNG, TB_RDCT_HSTRY

REDUCTION_PERCENT = 50
REDUCTION_TYPES = ("DR.LIVELIHD", "DR.VETERAN", "DR.DISABLED")


@dataclass(frozen=True)
class Quote:
    fee: int
    reduction: int
    payable: int
    approval_sn: int | None  # 적용한 사전심사 승인. 없으면 감면이 없다


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


def find_usable_approval(db: Session, member: Any, cycle_sn: int, now: datetime) -> int | None:
    """회원·기수 단위로 승인된 사전심사 중 지금 쓸 수 있는 것의 번호(TDD 5.5)."""
    if member.HAB_RGN_CD != "RA.JORI" or member.HAB_IDNTY_STTS_CD != "RV.OK":
        return None
    approval = db.execute(
        select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN)
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
    ).scalar_one_or_none()
    if approval is None or _already_reduced(db, int(member.OPER_BNDL_SN), int(member.MBR_SN), cycle_sn):
        return None
    return int(approval)


def quote(db: Session, member: Any, course: Any, now: datetime) -> Quote:
    """수강료 스냅샷, 감면(수강료의 50% 내림), 결제 예정액. 결제 예정액은 0 아래로 내려가지 않는다."""
    fee = int(course.TTCHG)
    approval = find_usable_approval(db, member, int(course.EDU_CYCL_SN), now)
    reduction = fee * REDUCTION_PERCENT // 100 if approval is not None else 0
    return Quote(fee=fee, reduction=reduction, payable=fee - reduction, approval_sn=approval)
