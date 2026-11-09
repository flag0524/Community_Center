# 홈, 센터 연락처, 약관 조회 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.auth.deps import Clock, get_bundle_resolver, get_clock
from app.core.errors import ErrorCode, not_implemented
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.domain.member.schemas import TermDocument
from app.domain.member.types import TermType
from app.domain.site import service
from app.domain.site.schemas import ContactResponse, ContentDocument, ContentSlug, HomeResponse
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["site"], responses=PUBLIC_ERRORS)


@router.get("/home")
def get_home() -> HomeResponse:
    not_implemented()


@router.get("/site/contact")
def get_contact(
    db: Annotated[Session, Depends(get_db)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
) -> ContactResponse:
    return service.get_contact(db, bundles.resolve(db))


@router.get("/terms/{term_type}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_term(
    term_type: Annotated[TermType, Path()],
    db: Annotated[Session, Depends(get_db)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
    clock: Annotated[Clock, Depends(get_clock)],
    version: str | None = None,
) -> TermDocument:
    return service.get_term(db, bundles.resolve(db), term_type, version, clock())


@router.get("/contents/{slug}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_content(
    slug: Annotated[ContentSlug, Path()],
    db: Annotated[Session, Depends(get_db)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ContentDocument:
    """안내·센터소개 글. 관리자 콘텐츠 관리(TB_SITE_CONTS)에서 고친 게시본을 내려준다."""
    return service.get_content(db, bundles.resolve(db), slug, clock())
