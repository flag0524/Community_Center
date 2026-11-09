# 약관·안내 글·센터 연락처 공개 조회(게시 중인 것만, 운영묶음 안에서만)
import json
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.join import TERM_CONTENT_TYPES
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_OPER_BNDL, TB_SITE_CONTS
from app.domain.member.schemas import TermDocument
from app.domain.member.types import TermType
from app.domain.site.schemas import ContactResponse, ContentDocument, ContentSlug

KST = timezone(timedelta(hours=9))
# 안내 글 중 지금 저장 위치(CT 코드)가 있는 것만 둔다. 나머지 셋은 스키마 개정 R9 전까지 404다(ADR-034).
SLUG_CONTENT_TYPE = {ContentSlug.CENTER_HISTORY: "CT.HISTORY"}


def _kst_date(value: datetime | None) -> date | None:
    """DB의 시간대 없는 UTC 시각을 한국 날짜로 바꾼다."""
    return None if value is None else value.replace(tzinfo=UTC).astimezone(KST).date()


def _latest_published(
    db: Session,
    bundle_sn: int,
    content_type: str,
    now: datetime,
    *,
    content_id: str | None,
    version: str | None,
) -> Any:
    """게시 여부와 게시 기간을 모두 만족하는 문안 중 가장 최근에 만든 것. 없으면 None."""
    query = select(TB_SITE_CONTS).where(
        TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn,
        TB_SITE_CONTS.c.CONTS_TYPE_CD == content_type,
        TB_SITE_CONTS.c.PSTG_YN == "Y",
        (TB_SITE_CONTS.c.PSTG_BGNG_DT.is_(None)) | (TB_SITE_CONTS.c.PSTG_BGNG_DT <= now),
        (TB_SITE_CONTS.c.PSTG_END_DT.is_(None)) | (TB_SITE_CONTS.c.PSTG_END_DT > now),
    )
    if content_id is not None:
        query = query.where(TB_SITE_CONTS.c.CONTS_ID == content_id)
    if version is not None:
        query = query.where(TB_SITE_CONTS.c.VER_NM == version)
    return db.execute(query.order_by(TB_SITE_CONTS.c.SITE_CONTS_SN.desc()).limit(1)).first()


def get_term(
    db: Session, bundle_sn: int, term_type: TermType, version: str | None, now: datetime
) -> TermDocument:
    row = _latest_published(
        db, bundle_sn, TERM_CONTENT_TYPES[term_type], now, content_id=None, version=version
    )
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return TermDocument(
        term_type=term_type,
        version=str(row.VER_NM),
        title=str(row.CONTS_TTL),
        body=str(row.CONTS_CN),
        effective_on=_kst_date(row.PSTG_BGNG_DT),
    )


def get_content(db: Session, bundle_sn: int, slug: ContentSlug, now: datetime) -> ContentDocument:
    """본문(CONTS_CN)은 `{"subtitle": ..., "sections": [...]}` 모양의 JSON이다. 깨져 있으면 서버 오류다."""
    content_type = SLUG_CONTENT_TYPE.get(slug)
    row = (
        None
        if content_type is None
        else _latest_published(db, bundle_sn, content_type, now, content_id=slug.value, version=None)
    )
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        body = json.loads(str(row.CONTS_CN))
        if not isinstance(body, dict):
            raise ValueError("본문이 객체가 아니다")
        updated = _kst_date(row.MDFCN_DT or row.REG_DT)
        return ContentDocument.model_validate(
            {**body, "slug": slug.value, "title": str(row.CONTS_TTL), "updatedOn": updated}
        )
    except (ValueError, ValidationError):
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None


def get_contact(db: Session, bundle_sn: int) -> ContactResponse:
    """연락처 저장 위치가 아직 없어(Q23) 운영묶음의 전화·주소만 채우고 나머지는 비운다."""
    row = db.execute(
        select(TB_OPER_BNDL.c.TELNO, TB_OPER_BNDL.c.ADDR).where(TB_OPER_BNDL.c.OPER_BNDL_SN == bundle_sn)
    ).one()
    return ContactResponse(phone=row.TELNO, address=row.ADDR)
