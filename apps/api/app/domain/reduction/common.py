# 감면 사전심사의 주민·관리자 서비스가 함께 쓰는 코드 표와 증빙 건수 쿼리. 이 도메인이 소유한다
from typing import Any

from sqlalchemy import func, select

from app.db.tables import TB_FILE, TB_RDCT_BFHD_SRNG
from app.domain.reduction.types import ReductionStatus, ReductionType

TYPE_CODE = {
    ReductionType.LIVELIHOOD: "DR.LIVELIHD",
    ReductionType.VETERAN: "DR.VETERAN",
    ReductionType.DISABLED: "DR.DISABLED",
}
CODE_TYPE = {code: kind for kind, code in TYPE_CODE.items()}
STATUS_CODE = {
    ReductionStatus.RECEIVED: "DS.RECEIVED",
    ReductionStatus.APPROVED: "DS.APPROVED",
    ReductionStatus.REJECTED: "DS.REJECTED",
    ReductionStatus.REVOKED: "DS.REVOKED",
}
CODE_STATUS = {code: status for status, code in STATUS_CODE.items()}


def evidence_count() -> Any:
    """심사 한 건에 붙은 증빙 파일 수(삭제된 파일 제외). 심사 테이블을 쓰는 쿼리의 열로 넣는다."""
    return (
        select(func.count())
        .where(
            TB_FILE.c.OPER_BNDL_SN == TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN,
            TB_FILE.c.RDCT_BFHD_SRNG_SN == TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN,
            TB_FILE.c.FILE_STTS_CD != "FS.DELETE",
        )
        .scalar_subquery()
    )
