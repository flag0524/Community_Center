# 홈 화면 응답 조립. 기준 기수, 분야별 접수 현황, 공지, 배너·팝업을 서버가 판정해 지금 보일 것만 담는다(FN-006, FN-054)
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.times import utc
from app.db.tables import TB_CORS, TB_CORS_CLSF, TB_FILE, TB_SITE_CONTS
from app.domain.board.service import IMAGE, SAFE, notice_briefs
from app.domain.course.schemas import CategoryRef
from app.domain.course.service import (
    VISIBLE_STATUSES,
    current_cycle,
    cycle_info,
    reception_state,
    ymd,
)
from app.domain.course.types import ReceptionState
from app.domain.file.service import file_url
from app.domain.site.schemas import (
    CategoryOverview,
    HomeBanner,
    HomeImage,
    HomePopup,
    HomeResponse,
)
from app.domain.site.service import published_window

NOTICE_COUNT = 5
COURSE_NAME_COUNT = 3


def safe_link(value: str | None) -> str | None:
    """사이트 안 경로(/로 시작, //는 제외)나 https 주소만 링크로 인정한다. javascript: 같은 값은 버린다."""
    if value is None:
        return None
    link = value.strip()
    if link.startswith("/") and not link.startswith("//"):
        return link
    if link.startswith("https://") and len(link) > len("https://"):
        return link
    return None


def _categories(db: Session, bundle_sn: int, cycle: Any, now: datetime) -> list[CategoryOverview]:
    rows = db.execute(
        select(
            TB_CORS.c.CORS_NM,
            TB_CORS.c.CORS_STTS_CD,
            TB_CORS.c.RCPT_BGNG_DT,
            TB_CORS.c.RCPT_END_DT,
            TB_CORS.c.EDU_BGNG_YMD,
            TB_CORS.c.EDU_END_YMD,
            TB_CORS_CLSF.c.CORS_CLSF_SN,
            TB_CORS_CLSF.c.CORS_CLSF_NM,
        )
        .join(
            TB_CORS_CLSF,
            and_(
                TB_CORS_CLSF.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_CORS_CLSF.c.CORS_CLSF_SN == TB_CORS.c.CORS_CLSF_SN,
                TB_CORS_CLSF.c.USE_YN == "Y",
                TB_CORS_CLSF.c.DEL_YN == "N",
            ),
        )
        .where(
            TB_CORS.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS.c.EDU_CYCL_SN == cycle.EDU_CYCL_SN,
            TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_STATUSES),
        )
        .order_by(TB_CORS_CLSF.c.SORT_SEQ, TB_CORS_CLSF.c.CORS_CLSF_SN, TB_CORS.c.CORS_SN)
    ).all()
    grouped: dict[int, list[Any]] = {}
    for row in rows:
        grouped.setdefault(int(row.CORS_CLSF_SN), []).append(row)
    result = []
    for courses in grouped.values():
        states = {reception_state(str(c.CORS_STTS_CD), c.RCPT_BGNG_DT, c.RCPT_END_DT, now) for c in courses}
        if ReceptionState.OPEN in states:
            state = ReceptionState.OPEN
        elif ReceptionState.UPCOMING in states:
            state = ReceptionState.UPCOMING
        else:
            state = ReceptionState.CLOSED
        first = courses[0]
        result.append(
            CategoryOverview(
                category=CategoryRef(category_id=str(int(first.CORS_CLSF_SN)), name=str(first.CORS_CLSF_NM)),
                reception_state=state,
                reception_start=utc(min(c.RCPT_BGNG_DT for c in courses)),
                reception_end=utc(max(c.RCPT_END_DT for c in courses)),
                education_start=ymd(min(str(c.EDU_BGNG_YMD) for c in courses)),
                education_end=ymd(max(str(c.EDU_END_YMD) for c in courses)),
                course_names=[str(c.CORS_NM) for c in courses[:COURSE_NAME_COUNT]],
            )
        )
    return result


def _contents(db: Session, bundle_sn: int, content_type: str, now: datetime) -> list[Any]:
    """게시 중인 홈 콘텐츠. 같은 콘텐츠 아이디가 여러 버전이면 가장 늦게 만든 것만 쓴다."""
    rows = db.execute(
        select(TB_SITE_CONTS)
        .where(
            TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn,
            TB_SITE_CONTS.c.CONTS_TYPE_CD == content_type,
            published_window(now),
        )
        .order_by(TB_SITE_CONTS.c.SITE_CONTS_SN.desc())
    ).all()
    latest: dict[str, Any] = {}
    for row in rows:
        latest.setdefault(str(row.CONTS_ID), row)
    return sorted(latest.values(), key=lambda r: (int(r.SORT_SEQ), int(r.SITE_CONTS_SN)))


def _images(db: Session, bundle_sn: int, content_sns: list[int]) -> dict[int, int]:
    """콘텐츠마다 검사를 통과한 첫 이미지 파일 번호."""
    if not content_sns:
        return {}
    rows = db.execute(
        select(TB_FILE.c.SITE_CONTS_SN, TB_FILE.c.FILE_SN)
        .where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.SITE_CONTS_SN.in_(content_sns),
            TB_FILE.c.FILE_USE_CD == IMAGE,
            TB_FILE.c.FILE_STTS_CD == SAFE,
        )
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
    ).all()
    first: dict[int, int] = {}
    for row in rows:
        first.setdefault(int(row.SITE_CONTS_SN), int(row.FILE_SN))
    return first


def get_home(db: Session, bundle_sn: int, now: datetime) -> HomeResponse:
    cycle = current_cycle(db, bundle_sn, now)
    banners = _contents(db, bundle_sn, "CT.BANNER", now)
    popups = _contents(db, bundle_sn, "CT.POPUP", now)
    images = _images(db, bundle_sn, [int(r.SITE_CONTS_SN) for r in (*banners, *popups)])

    def image(row: Any) -> HomeImage | None:
        file_sn = images.get(int(row.SITE_CONTS_SN))
        return None if file_sn is None else HomeImage(url=file_url(file_sn), alt=str(row.CONTS_TTL))

    return HomeResponse(
        server_now=utc(now),
        cycle=None if cycle is None else cycle_info(cycle, now),
        categories=[] if cycle is None else _categories(db, bundle_sn, cycle, now),
        notices=notice_briefs(db, bundle_sn, now, NOTICE_COUNT),
        visual=None,  # 저장 위치(CT.VISUAL)가 스키마 개정 R14로 확정될 때까지 비운다(ADR-036)
        banners=[
            HomeBanner(
                content_id=str(int(r.SITE_CONTS_SN)),
                title=str(r.CONTS_TTL),
                link_url=safe_link(r.URL_ADDR),
                image=image(r),
            )
            for r in banners
        ],
        popups=[
            HomePopup(
                content_id=str(int(r.SITE_CONTS_SN)),
                title=str(r.CONTS_TTL),
                body=str(r.CONTS_CN).strip() or None,
                link_url=safe_link(r.URL_ADDR),
                image=image(r),
            )
            for r in popups
        ],
    )
