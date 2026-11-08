# 관리자 문의·답변 라우터. 모두 AU.POST_W이고 답변은 원글당 한 단계다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.inquiry_schemas import (
    AdminInquiry,
    AdminInquiryCategoryList,
    AdminInquiryPage,
    InquiryAnswerWrite,
)
from app.domain.board.types import InquiryStatus
from app.routers.deps import CSV_RESPONSE, MEMBER_ERRORS, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-inquiry"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
ANSWER_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED)


@router.get("/inquiry-categories")
def list_admin_inquiry_categories() -> AdminInquiryCategoryList:
    """문의 분류(IQ). 초기값은 기관 확인 뒤 입력하며 임의로 만들지 않는다(PRD Q26)."""
    not_implemented()


@router.get("/inquiries")
def list_admin_inquiries(
    status: InquiryStatus | None = None,
    category_id: Annotated[str | None, Query(alias="categoryId", pattern=r"^[0-9]{1,22}$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminInquiryPage:
    """범위 밖 문의는 나오지 않는다. 접수 상태(답변 대기)가 먼저 나온다."""
    not_implemented()


@router.get(
    "/inquiries/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_inquiries_csv(
    status: InquiryStatus | None = None,
    category_id: Annotated[str | None, Query(alias="categoryId", pattern=r"^[0-9]{1,22}$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """목록과 같은 조건·권한으로 만든다. 문의 본문·답변·첨부는 담지 않고 작성자는 가린 값이다."""
    not_implemented()


@router.get("/inquiries/{inquiry_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_inquiry(inquiry_id: Serial) -> AdminInquiry:
    not_implemented()


@router.put("/inquiries/{inquiry_id}/answer", responses=ANSWER_ERRORS, dependencies=[Depends(csrf_header)])
def answer_inquiry(inquiry_id: Serial, body: InquiryAnswerWrite) -> AdminInquiry:
    """답변을 작성하거나 고친다. 고치면 수정 이력이 남고 답변은 여전히 한 단계다."""
    not_implemented()
