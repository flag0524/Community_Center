# 회원의 감면 사전심사 라우터. 조리읍 거주가 확인된 회원이 기수별로 신청하고 결과를 본다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Security
from sqlalchemy.orm import Session

from app.auth.deps import Clock, Member, get_clock, request_id_of, require_member, require_member_write
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.reduction import service
from app.domain.reduction.schemas import MyReduction, MyReductionCreate, MyReductionList, MyReductionOptions
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, csrf_header, error_responses, member_session

member_router = APIRouter(
    tags=["member-reduction"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]


@member_router.get("/me/reduction-options")
def get_my_reduction_options(db: Db, me: Me, clock: Now) -> MyReductionOptions:
    """신청할 수 있는 기수와 신청 가능 여부. 거주 확인이 안 된 회원은 이유를 함께 받는다."""
    return service.get_options(db, bundle_sn=me.bundle_sn, member_sn=me.member_sn, now=clock())


@member_router.get("/me/reduction-reviews")
def list_my_reductions(db: Db, me: Me) -> MyReductionList:
    """내 사전심사 신청. 최근 신청이 먼저 나온다."""
    return service.list_mine(db, bundle_sn=me.bundle_sn, member_sn=me.member_sn)


@member_router.post(
    "/me/reduction-reviews",
    status_code=201,
    responses=error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT),
    dependencies=[Depends(csrf_header)],
)
def create_my_reduction(
    body: MyReductionCreate,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    clock: Now,
) -> MyReduction:
    """거주 확인이 안 됐거나 같은 기수에 접수·승인 건이 있으면 RULE_REJECTED다. 증빙은 신청한 뒤에 올린다."""
    return service.create_mine(
        db,
        bundle_sn=me.bundle_sn,
        member_sn=me.member_sn,
        body=body,
        idem_key=idempotency_key,
        now=clock(),
        request_id=request_id_of(request),
    )


@member_router.get("/me/reduction-reviews/{review_id}", responses=NOT_FOUND)
def get_my_reduction(review_id: Serial, db: Db, me: Me) -> MyReduction:
    return service.get_mine(db, bundle_sn=me.bundle_sn, member_sn=me.member_sn, review_id=review_id)


@member_router.post(
    "/me/reduction-reviews/{review_id}/withdraw",
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def withdraw_my_reduction(
    review_id: Serial, request: Request, db: Db, me: MeWrite, clock: Now
) -> MyReduction:
    """접수 상태일 때만 철회한다. 결정된 신청은 철회할 수 없고 다시 심사를 받으려면 새로 신청한다."""
    return service.withdraw_mine(
        db,
        bundle_sn=me.bundle_sn,
        member_sn=me.member_sn,
        review_id=review_id,
        now=clock(),
        request_id=request_id_of(request),
    )
