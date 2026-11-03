# 게시판 목록, 게시물 상세, 첨부 내려받기 라우터
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from app.core.errors import ErrorCode, not_implemented
from app.domain.board.schemas import PostDetail, PostPage
from app.domain.board.types import BoardKey
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["board"], responses=PUBLIC_ERRORS)


@router.get("/boards/{board}/posts", responses=error_responses(ErrorCode.NOT_FOUND))
def list_posts(
    board: Annotated[BoardKey, Path()],
    q: Annotated[str | None, Query(max_length=100, description="제목 검색어")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PostPage:
    """공개된 게시물만 상단공지, 등록일 내림차순으로 준다."""
    not_implemented()


@router.get("/posts/{post_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_post(
    post_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="게시물 일련번호(문자열)")],
) -> PostDetail:
    not_implemented()


@router.get(
    "/files/{file_id}",
    response_class=Response,
    responses={
        **error_responses(ErrorCode.NOT_FOUND),
        200: {"description": "첨부 내용", "content": {"application/octet-stream": {}}},
    },
)
def download_file(
    file_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="파일 일련번호(문자열)")],
) -> Response:
    """소유 게시물이 공개일 때만 내려준다."""
    not_implemented()
