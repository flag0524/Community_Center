# 시설안내 공개 조회. 사용 중인 센터와 강의실을 시설 테이블(TB_FCLT)에서 그대로 읽는다(ADR-117)
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.tables import TB_FCLT
from app.domain.site.schemas import FacilityInfo, FacilityListResponse

# 관리자 시설 관리가 층을 설명 칸에 저장하는 표식과 시설 유형 코드다. 같은 값인지는 시험이 지킨다.
FLOOR_LABEL = "층: "
CODE_KIND: dict[str, Literal["CENTER", "ROOM"]] = {"FT.CENTER": "CENTER", "FT.ROOM": "ROOM"}


def _floor(explanation: Any) -> str | None:
    """층은 설명 칸에 `층: ` 표식과 함께 저장돼 있다. 표식이 없는 설명은 층이 아니라 내지 않는다."""
    text = None if explanation is None else str(explanation)
    return text.removeprefix(FLOOR_LABEL) if text and text.startswith(FLOOR_LABEL) else None


def list_facilities(db: Session, bundle_sn: int) -> FacilityListResponse:
    """사용 중인 시설만이다. 센터가 먼저고 그 아래 강의실이 층 순서(층이 없으면 맨 뒤), 이름순으로 온다."""
    rows = db.execute(
        select(TB_FCLT)
        .where(TB_FCLT.c.OPER_BNDL_SN == bundle_sn, TB_FCLT.c.USE_YN == "Y")
        .order_by(
            func.coalesce(TB_FCLT.c.UP_FCLT_SN, TB_FCLT.c.FCLT_SN),
            TB_FCLT.c.UP_FCLT_SN.is_not(None),
            TB_FCLT.c.FCLT_EXPLN.is_(None),
            TB_FCLT.c.FCLT_EXPLN,
            TB_FCLT.c.FCLT_NM,
            TB_FCLT.c.FCLT_SN,
        )
    ).all()
    return FacilityListResponse(
        items=[
            FacilityInfo(
                facility_id=str(int(r.FCLT_SN)),
                kind=CODE_KIND[str(r.FCLT_TYPE_CD)],
                parent_id=None if r.UP_FCLT_SN is None else str(int(r.UP_FCLT_SN)),
                name=str(r.FCLT_NM),
                floor=_floor(r.FCLT_EXPLN),
                address=None if r.ADDR is None else str(r.ADDR),
            )
            for r in rows
        ]
    )
