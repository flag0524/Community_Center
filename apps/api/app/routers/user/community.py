# 질문과 답변(문의)과 수강후기의 조회·작성·수정·삭제 라우터. 작성·수정·삭제는 본인 글만이고 타인의 글은 404다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.deps import Clock, Member, get_clock, request_id_of, require_member, require_member_write
from app.core.errors import ErrorCode, not_implemented
from app.db.session import get_db
from app.domain.board import inquiry
from app.domain.board.schemas import (
    InquiryCategoryList,
    InquiryDetail,
    InquiryPage,
    InquiryWrite,
    ReviewableCourseList,
    ReviewDetail,
    ReviewPage,
    ReviewWrite,
)
from app.routers.deps import (
    MEMBER_ERRORS,
    PUBLIC_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

# 후기 목록·상세는 누구나 본다.
router = APIRouter(tags=["community"], responses=PUBLIC_ERRORS)
# 문의와 내 글, 작성은 로그인한 회원만이다.
member_router = APIRouter(
    tags=["community"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)]
)

PostId = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="게시물 일련번호(문자열)")]
Page_ = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=50)]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/reviews")
def list_reviews(
    q: Annotated[str | None, Query(max_length=100, description="제목 검색어")] = None,
    page: Page_ = 1,
    size: Size = 10,
) -> ReviewPage:
    not_implemented()


@router.get("/reviews/{post_id}", responses=NOT_FOUND)
def get_review(post_id: PostId) -> ReviewDetail:
    not_implemented()


@member_router.get("/inquiry-categories")
def list_inquiry_categories(db: Db, me: Me) -> InquiryCategoryList:
    return inquiry.list_categories(db)


@member_router.get("/inquiries")
def list_inquiries(db: Db, me: Me, clock: Now, page: Page_ = 1, size: Size = 10) -> InquiryPage:
    """모든 문의의 분류·상태·등록일을 준다. 다른 회원의 비공개 문의는 제목과 작성자를 가린다."""
    return inquiry.list_all(
        db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, now=clock(), page=page, size=size
    )


@member_router.get("/inquiries/{post_id}", responses=NOT_FOUND)
def get_inquiry(post_id: PostId, db: Db, me: Me) -> InquiryDetail:
    """다른 회원의 비공개 문의는 없는 것과 같게 404다."""
    return inquiry.get_inquiry(db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, post_id=post_id)


@member_router.get("/me/inquiries")
def list_my_inquiries(db: Db, me: Me, clock: Now, page: Page_ = 1, size: Size = 10) -> InquiryPage:
    return inquiry.list_mine(
        db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, now=clock(), page=page, size=size
    )


@member_router.post(
    "/me/inquiries", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def create_inquiry(
    body: InquiryWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    clock: Now,
) -> InquiryDetail:
    return inquiry.create_inquiry(
        db,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        body=body,
        idem_key=idempotency_key,
        request_id=request_id_of(request),
        now=clock(),
    )


@member_router.put("/me/inquiries/{post_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_inquiry(
    post_id: PostId, body: InquiryWrite, request: Request, db: Db, me: MeWrite, clock: Now
) -> InquiryDetail:
    """답변이 달린 문의는 고칠 수 없다(RULE_REJECTED)."""
    return inquiry.update_inquiry(
        db,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        post_id=post_id,
        body=body,
        request_id=request_id_of(request),
        now=clock(),
    )


@member_router.delete(
    "/me/inquiries/{post_id}",
    status_code=204,
    response_class=Response,
    responses=NOT_FOUND,
    dependencies=[Depends(csrf_header)],
)
def delete_inquiry(post_id: PostId, request: Request, db: Db, me: MeWrite, clock: Now) -> None:
    inquiry.delete_inquiry(
        db,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        post_id=post_id,
        request_id=request_id_of(request),
        now=clock(),
    )


@member_router.get("/me/reviews")
def list_my_reviews(page: Page_ = 1, size: Size = 10) -> ReviewPage:
    not_implemented()


@member_router.get("/me/reviewable-courses")
def list_reviewable_courses() -> ReviewableCourseList:
    not_implemented()


@member_router.post(
    "/me/reviews", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)]
)
def create_review(body: ReviewWrite, idempotency_key: IdempotencyKey) -> ReviewDetail:
    """수강확정인 강좌의 후기만 쓸 수 있다. 직접 요청도 같은 검사를 한다(FN-052)."""
    not_implemented()


@member_router.put("/me/reviews/{post_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_review(post_id: PostId, body: ReviewWrite) -> ReviewDetail:
    not_implemented()


@member_router.delete(
    "/me/reviews/{post_id}",
    status_code=204,
    response_class=Response,
    responses=NOT_FOUND,
    dependencies=[Depends(csrf_header)],
)
def delete_review(post_id: PostId) -> None:
    not_implemented()
