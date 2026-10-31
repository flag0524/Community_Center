# 홈, 센터 연락처, 약관 조회 라우터
from typing import Annotated

from fastapi import APIRouter, Path

from app.core.errors import ErrorCode, not_implemented
from app.domain.member.schemas import TermDocument
from app.domain.member.types import TermType
from app.domain.site.schemas import ContactResponse, HomeResponse
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["site"], responses=PUBLIC_ERRORS)


@router.get("/home")
def get_home() -> HomeResponse:
    not_implemented()


@router.get("/site/contact")
def get_contact() -> ContactResponse:
    not_implemented()


@router.get("/terms/{term_type}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_term(term_type: Annotated[TermType, Path()], version: str | None = None) -> TermDocument:
    not_implemented()
