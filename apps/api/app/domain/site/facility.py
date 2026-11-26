# 시설안내 공개 조회. 사용 중인 센터와 강의실을 시설 테이블(TB_FCLT)에서 그대로 읽는다(ADR-117)
from typing import Any, Literal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.db.tables import TB_FCLT, TB_FILE
from app.domain.file.types import file_url
from app.domain.site.schemas import FacilityInfo, FacilityListResponse

# 관리자 시설 관리가 층을 설명 칸에 저장하는 표식과 시설 유형 코드다. 같은 값인지는 시험이 지킨다.
FLOOR_LABEL = "층: "
CODE_KIND: dict[str, Literal["CENTER", "ROOM"]] = {"FT.CENTER": "CENTER", "FT.ROOM": "ROOM"}


def _floor(explanation: Any) -> str | None:
    """층은 설명 칸에 `층: ` 표식과 함께 저장돼 있다. 표식이 없는 설명은 층이 아니라 내지 않는다."""
    text = None if explanation is None else str(explanation)
    return text.removeprefix(FLOOR_LABEL) if text and text.startswith(FLOOR_LABEL) else None


def center_in_use() -> Any:
    """강의실(TB_FCLT)의 상위 센터가 사용 중인가. 센터를 사용 중지하면 그 강의실은 배정할 수 없다."""
    center = TB_FCLT.alias("open_center")
    return or_(
        TB_FCLT.c.UP_FCLT_SN.is_(None),
        exists(
            select(center.c.FCLT_SN).where(center.c.FCLT_SN == TB_FCLT.c.UP_FCLT_SN, center.c.USE_YN == "Y")
        ).correlate(TB_FCLT),
    )


def _photos(db: Session, bundle_sn: int, facility_sns: list[int]) -> dict[int, list[str]]:
    """검사를 통과한 사진 주소. 정렬순서의 맨 앞이 대표 사진이다."""
    found: dict[int, list[str]] = {sn: [] for sn in facility_sns}
    for row in db.execute(
        select(TB_FILE.c.FCLT_SN, TB_FILE.c.FILE_SN)
        .where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.FCLT_SN.in_(facility_sns),
            TB_FILE.c.FILE_STTS_CD == "FS.SAFE",
            TB_FILE.c.FILE_USE_CD == "FP.IMAGE",
        )
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
    ):
        found[int(row.FCLT_SN)].append(file_url(int(row.FILE_SN)))
    return found


def list_facilities(db: Session, bundle_sn: int) -> FacilityListResponse:
    """사용 중인 시설만이며 사용 중지한 센터의 강의실도 뺀다.

    센터가 먼저고 그 아래 강의실이 층 순서(층이 없으면 맨 뒤), 이름순으로 온다.
    """
    rows = db.execute(
        select(TB_FCLT)
        .where(TB_FCLT.c.OPER_BNDL_SN == bundle_sn, TB_FCLT.c.USE_YN == "Y", center_in_use())
        .order_by(
            func.coalesce(TB_FCLT.c.UP_FCLT_SN, TB_FCLT.c.FCLT_SN),
            TB_FCLT.c.UP_FCLT_SN.is_not(None),
            TB_FCLT.c.FCLT_EXPLN.is_(None),
            TB_FCLT.c.FCLT_EXPLN,
            TB_FCLT.c.FCLT_NM,
            TB_FCLT.c.FCLT_SN,
        )
    ).all()
    photos = _photos(db, bundle_sn, [int(r.FCLT_SN) for r in rows])
    return FacilityListResponse(
        items=[
            FacilityInfo(
                facility_id=str(int(r.FCLT_SN)),
                kind=CODE_KIND[str(r.FCLT_TYPE_CD)],
                parent_id=None if r.UP_FCLT_SN is None else str(int(r.UP_FCLT_SN)),
                name=str(r.FCLT_NM),
                floor=_floor(r.FCLT_EXPLN),
                address=None if r.ADDR is None else str(r.ADDR),
                photo_urls=photos[int(r.FCLT_SN)],
            )
            for r in rows
        ]
    )
