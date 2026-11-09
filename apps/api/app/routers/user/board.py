# 게시판 목록, 게시물 상세, 첨부 내려받기 라우터
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.auth.deps import Clock, get_bundle_resolver, get_clock
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.domain.board import service
from app.domain.board.schemas import PostDetail, PostPage
from app.domain.board.types import BoardKey
from app.domain.file import service as file_service
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["board"], responses=PUBLIC_ERRORS)

Db = Annotated[Session, Depends(get_db)]
Bundles = Annotated[BundleResolver, Depends(get_bundle_resolver)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/boards/{board}/posts", responses=error_responses(ErrorCode.NOT_FOUND))
def list_posts(
    board: Annotated[BoardKey, Path()],
    db: Db,
    bundles: Bundles,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100, description="제목 검색어")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> PostPage:
    """공개된 게시물만 상단공지, 등록일시 내림차순으로 준다."""
    return service.list_posts(db, bundles.resolve(db), clock(), board, q=q, page=page, size=size)


@router.get("/posts/{post_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_post(
    post_id: Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="게시물 일련번호(문자열)")],
    db: Db,
    bundles: Bundles,
    clock: Now,
) -> PostDetail:
    return service.get_post(db, bundles.resolve(db), clock(), post_id)


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
    db: Db,
    bundles: Bundles,
    clock: Now,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """소유 게시물이 공개일 때, 게시 중인 홈 콘텐츠의 이미지일 때, 공개 강좌의 강의계획서일 때만 내려준다."""
    file, content = file_service.download(db, settings, bundles.resolve(db), file_id, clock())
    mime = str(file.MIME_TYPE_NM)
    inline = file.FILE_USE_CD == "FP.IMAGE" and mime.startswith("image/")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(str(file.FILE_NM))}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",  # 비공개가 되면 바로 막혀야 해서 응답을 오래 쥐지 않는다
        },
    )
