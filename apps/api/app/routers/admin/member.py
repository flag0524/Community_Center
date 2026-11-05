# 관리자 회원 조회·검토 기록 라우터. 모두 AU.MBR_R이며 회원 정보 수정 API는 만들지 않는다(FN-065)
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.member_schemas import (
    AdminMember,
    AdminMemberPage,
    MemberContact,
    MemberReview,
    MemberReviewClose,
    MemberReviewCreate,
    ResidenceRecord,
    RevealRequest,
)
from app.domain.admin.member_types import MemberStatus
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-member"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/members")
def list_members(
    q: Annotated[str | None, Query(max_length=100, description="아이디 또는 이름")] = None,
    status: MemberStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminMemberPage:
    """연령대는 담지 않는다. 개인 연령은 기관 제공 집계자료로만 다룬다(PRD Q7)."""
    not_implemented()


@router.get("/members/{member_id}", responses=NOT_FOUND)
def get_member(member_id: Serial) -> AdminMember:
    not_implemented()


@router.post("/members/{member_id}/reveal", responses=NOT_FOUND, dependencies=[Depends(csrf_header)])
def reveal_member_contact(member_id: Serial, body: RevealRequest) -> MemberContact:
    """사유와 함께 감사기록을 남기고 가려진 연락처를 준다."""
    not_implemented()


@router.post(
    "/members/{member_id}/reviews",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_member_review(
    member_id: Serial, body: MemberReviewCreate, idempotency_key: IdempotencyKey
) -> MemberReview:
    """이용제한·탈퇴·이름 변경 검토 사유를 기록한다. 회원 상태는 바꾸지 않는다."""
    not_implemented()


@router.post(
    "/members/{member_id}/reviews/{review_id}/close",
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def close_member_review(member_id: Serial, review_id: Serial, body: MemberReviewClose) -> MemberReview:
    """검토 중인 기록을 처리 완료로 닫는다."""
    not_implemented()


@router.post("/members/{member_id}/residence", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def record_residence(member_id: Serial, body: ResidenceRecord) -> AdminMember:
    """거주지 확인 결과를 기록한다(RM.MANUAL). 확인 권한 코드는 PRD Q5로 확인한다."""
    not_implemented()
