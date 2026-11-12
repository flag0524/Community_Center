# 관리자 게시판 설정(AU.BBS_W)과 게시물 관리(AU.POST_W) 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import board_service as service
from app.domain.admin.board_schemas import (
    AdminPost,
    AdminPostPage,
    AdminPostUpdate,
    AdminPostWrite,
    BoardSetting,
    BoardSettingList,
    BoardSettingUpdate,
)
from app.domain.admin.csv_export import csv_response
from app.domain.board.types import BoardKey
from app.routers.deps import (
    CSV_RESPONSE,
    MEMBER_ERRORS,
    IdempotencyKey,
    admin_session,
    csrf_header,
    error_responses,
)

router = APIRouter(tags=["admin-board"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED)
CREATE_ERRORS = error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/boards")
def list_boards(db: Db, admin: Me, clock: Now) -> BoardSettingList:
    """게시판 설정 조회. 게시물 권한(AU.POST_W)만 있어도 글쓰기 선택지로 볼 수 있다."""
    return service.list_boards(db, admin, now=clock())


@router.put("/boards/{board_key}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_board(
    board_key: BoardKey, body: BoardSettingUpdate, request: Request, db: Db, admin: Me, clock: Now
) -> BoardSetting:
    return service.update_board(
        db, admin, now=clock(), request_id=request_id_of(request), board_key=board_key, body=body
    )


@router.get("/posts")
def list_admin_posts(
    db: Db,
    admin: Me,
    clock: Now,
    board: BoardKey | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminPostPage:
    """상단공지가 먼저 나온다. 삭제한 글은 나오지 않는다."""
    return service.list_posts(db, admin, now=clock(), board=board, q=q, page=page, size=size)


@router.get(
    "/posts/export.csv",
    response_class=Response,
    responses={**error_responses(ErrorCode.RULE_REJECTED), **CSV_RESPONSE},
)
def export_posts_csv(
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
    board: BoardKey | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Response:
    """목록과 같은 조건·권한으로 만든다. 본문과 첨부는 담지 않고 작성자는 가린 값이다."""
    content = service.export_csv(db, admin, now=clock(), request_id=request_id_of(request), board=board, q=q)
    return csv_response("posts.csv", content)


@router.post("/posts", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_post(
    body: AdminPostWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> AdminPost:
    """회원이 쓰는 게시판이나 사용을 중지한 게시판에는 관리자가 새 글을 쓸 수 없다."""
    return service.create_post(
        db, admin, now=clock(), request_id=request_id_of(request), body=body, idem_key=idempotency_key
    )


@router.get("/posts/{post_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_post(post_id: Serial, db: Db, admin: Me, clock: Now) -> AdminPost:
    return service.get_post(db, admin, now=clock(), post_id=post_id)


@router.put("/posts/{post_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_admin_post(
    post_id: Serial, body: AdminPostUpdate, request: Request, db: Db, admin: Me, clock: Now
) -> AdminPost:
    return service.update_post(
        db, admin, now=clock(), request_id=request_id_of(request), post_id=post_id, body=body
    )


@router.delete(
    "/posts/{post_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.NOT_FOUND),
    dependencies=[Depends(csrf_header)],
)
def delete_admin_post(post_id: Serial, request: Request, db: Db, admin: Me, clock: Now) -> None:
    """삭제여부(DEL_YN)만 바꾸는 논리 삭제다. 감사기록에 남는다."""
    service.delete_post(db, admin, now=clock(), request_id=request_id_of(request), post_id=post_id)
