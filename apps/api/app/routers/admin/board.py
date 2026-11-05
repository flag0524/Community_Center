# 관리자 게시판 설정(AU.BBS_W)과 게시물 관리(AU.POST_W) 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.board_schemas import (
    AdminPost,
    AdminPostPage,
    AdminPostUpdate,
    AdminPostWrite,
    BoardSetting,
    BoardSettingList,
    BoardSettingUpdate,
)
from app.domain.board.types import BoardKey
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-board"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.VERSION_CONFLICT, ErrorCode.RULE_REJECTED)
CREATE_ERRORS = error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/boards")
def list_boards() -> BoardSettingList:
    """게시판 설정 조회. 게시물 권한(AU.POST_W)만 있어도 글쓰기 선택지로 볼 수 있다."""
    not_implemented()


@router.put("/boards/{board_key}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_board(board_key: BoardKey, body: BoardSettingUpdate) -> BoardSetting:
    not_implemented()


@router.get("/posts")
def list_admin_posts(
    board: BoardKey | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminPostPage:
    """상단공지가 먼저 나온다. 삭제한 글은 나오지 않는다."""
    not_implemented()


@router.post("/posts", status_code=201, responses=CREATE_ERRORS, dependencies=[Depends(csrf_header)])
def create_admin_post(body: AdminPostWrite, idempotency_key: IdempotencyKey) -> AdminPost:
    """회원이 쓰는 게시판이나 사용을 중지한 게시판에는 관리자가 새 글을 쓸 수 없다."""
    not_implemented()


@router.get("/posts/{post_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_post(post_id: Serial) -> AdminPost:
    not_implemented()


@router.put("/posts/{post_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_admin_post(post_id: Serial, body: AdminPostUpdate) -> AdminPost:
    not_implemented()


@router.delete(
    "/posts/{post_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.NOT_FOUND),
    dependencies=[Depends(csrf_header)],
)
def delete_admin_post(post_id: Serial) -> None:
    """삭제여부(DEL_YN)만 바꾸는 논리 삭제다. 감사기록에 남는다."""
    not_implemented()
