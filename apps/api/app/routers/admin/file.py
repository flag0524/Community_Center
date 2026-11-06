# 관리자 첨부파일 조회 라우터. 소유 업무의 접근 권한이 있는 파일만 보이고 조회만 한다
from typing import Annotated

from fastapi import APIRouter, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.file_schemas import AdminFile, AdminFilePage
from app.domain.admin.term_types import FileOwnerKind, FileStatus
from app.routers.deps import MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(tags=["admin-file"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]


@router.get("/files")
def list_admin_files(
    owner_kind: Annotated[FileOwnerKind | None, Query(alias="ownerKind")] = None,
    status: FileStatus | None = None,
    q: Annotated[str | None, Query(max_length=100, description="파일명")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminFilePage:
    """소유 업무에 접근 권한이 없는 파일은 조건과 무관하게 나오지 않는다(RQ-SER-NF-009)."""
    not_implemented()


@router.get("/files/{file_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_file(file_id: Serial) -> AdminFile:
    """권한이 없는 파일은 존재 여부를 알리지 않도록 404다."""
    not_implemented()
