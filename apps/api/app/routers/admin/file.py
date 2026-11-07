# 관리자 첨부파일 라우터. 소유 업무의 권한이 있는 파일만 보이고 올리기·제거는 소유 업무 경로로 한다
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Query, Response, Security, UploadFile

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.file_schemas import AdminFile, AdminFilePage, OwnerFile, OwnerFileList
from app.domain.admin.term_types import FileOwnerKind, FileStatus
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

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


UPLOAD_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT
)
BINARY: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}
}


@router.get("/posts/{post_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_post_files(post_id: Serial) -> OwnerFileList:
    """게시물 첨부. 게시물을 고칠 수 있는 담당자(AU.POST_W)만 본다."""
    not_implemented()


@router.post(
    "/posts/{post_id}/files", status_code=201, responses=UPLOAD_ERRORS, dependencies=[Depends(csrf_header)]
)
def upload_post_file(
    post_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
) -> OwnerFile:
    """업무를 먼저 저장한 뒤 파일을 한 개씩 올린다. 서버가 확장자·형식·크기·개수를 검사한다."""
    not_implemented()


@router.get("/courses/{course_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_course_files(course_id: Serial) -> OwnerFileList:
    """강의계획서 첨부. 강좌를 고칠 수 있는 담당자(AU.CORS_W)만 본다."""
    not_implemented()


@router.post(
    "/courses/{course_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_course_file(
    course_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
) -> OwnerFile:
    not_implemented()


@router.delete(
    "/files/{file_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def delete_file(file_id: Serial) -> None:
    """논리삭제한다. 소유 업무가 잠겼으면 409다. 물리 삭제는 보존기간 뒤에 한다."""
    not_implemented()


@router.get(
    "/files/{file_id}/download",
    response_class=Response,
    responses={**error_responses(ErrorCode.NOT_FOUND), **BINARY},
)
def download_admin_file(file_id: Serial) -> Response:
    """검사를 통과한 파일만 내려준다. 권한이 없으면 404다. 비공개 파일과 관리자 내려받기는 기록한다."""
    not_implemented()
