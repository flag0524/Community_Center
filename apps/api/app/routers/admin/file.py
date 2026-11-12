# 관리자 첨부파일 라우터. 소유 업무의 권한이 있는 파일만 보이고 올리기·제거는 소유 업무 경로로 한다
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, Security, UploadFile
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin, require_admin_write
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, not_implemented
from app.db.session import get_db
from app.domain.admin import file_service as service
from app.domain.admin.file_schemas import AdminFile, AdminFilePage, OwnerFile, OwnerFileList
from app.domain.admin.term_types import FileOwnerKind, FileStatus
from app.domain.file.upload import MAX_BYTES
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-file"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
MeWrite = Annotated[Admin, Depends(require_admin_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]


def read_upload(file: UploadFile) -> bytes:
    """한도보다 한 바이트만 더 읽어 큰 파일을 통째로 메모리에 올리지 않는다. 넘침은 검증이 거절한다."""
    return file.file.read(MAX_BYTES + 1)


@router.get("/files")
def list_admin_files(
    db: Db,
    admin: Me,
    clock: Now,
    owner_kind: Annotated[FileOwnerKind | None, Query(alias="ownerKind")] = None,
    status: FileStatus | None = None,
    q: Annotated[str | None, Query(max_length=100, description="파일명")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminFilePage:
    """소유 업무에 접근 권한이 없는 파일은 조건과 무관하게 나오지 않는다(RQ-SER-NF-009)."""
    return service.list_files(
        db, admin, now=clock(), owner_kind=owner_kind, status=status, q=q, page=page, size=size
    )


@router.get("/files/{file_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_admin_file(file_id: Serial, db: Db, admin: Me, clock: Now) -> AdminFile:
    """권한이 없는 파일은 존재 여부를 알리지 않도록 404다."""
    return service.get_file(db, admin, now=clock(), file_id=file_id)


UPLOAD_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT
)
BINARY: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}
}


@router.get("/posts/{post_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_post_files(post_id: Serial, db: Db, admin: Me, clock: Now) -> OwnerFileList:
    """게시물 첨부. 게시물을 고칠 수 있는 담당자(AU.POST_W)만 본다."""
    return service.list_owner_files(db, admin, now=clock(), kind=FileOwnerKind.POST, sn=int(post_id))


@router.post(
    "/posts/{post_id}/files", status_code=201, responses=UPLOAD_ERRORS, dependencies=[Depends(csrf_header)]
)
def upload_post_file(
    post_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> OwnerFile:
    """업무를 먼저 저장한 뒤 파일을 한 개씩 올린다. 서버가 확장자·형식·크기·개수를 검사한다."""
    return service.upload_owner_file(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        kind=FileOwnerKind.POST,
        sn=int(post_id),
        filename=file.filename or "",
        data=read_upload(file),
        idem_key=idempotency_key,
    )


@router.get("/courses/{course_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_course_files(course_id: Serial, db: Db, admin: Me, clock: Now) -> OwnerFileList:
    """강의계획서 첨부. 강좌를 고칠 수 있는 담당자(AU.CORS_W)만 본다."""
    return service.list_owner_files(db, admin, now=clock(), kind=FileOwnerKind.COURSE, sn=int(course_id))


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
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> OwnerFile:
    return service.upload_owner_file(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        kind=FileOwnerKind.COURSE,
        sn=int(course_id),
        filename=file.filename or "",
        data=read_upload(file),
        idem_key=idempotency_key,
    )


@router.get("/refunds/{refund_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_refund_files(refund_id: Serial, db: Db, admin: Me, clock: Now) -> OwnerFileList:
    """환불 증빙. 접수·보류 상태에서만 담당자(AU.RFND_A)가 추가·제거한다."""
    return service.list_owner_files(db, admin, now=clock(), kind=FileOwnerKind.REFUND, sn=int(refund_id))


@router.post(
    "/refunds/{refund_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_refund_file(
    refund_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: MeWrite,
    settings: Config,
    clock: Now,
) -> OwnerFile:
    return service.upload_owner_file(
        db,
        settings,
        admin,
        now=clock(),
        request_id=request_id_of(request),
        kind=FileOwnerKind.REFUND,
        sn=int(refund_id),
        filename=file.filename or "",
        data=read_upload(file),
        idem_key=idempotency_key,
    )


@router.get("/instructor-applications/{application_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_instructor_application_files(application_id: Serial) -> OwnerFileList:
    """강사 지원 증빙. 심사 대기 상태에서만 담당자(AU.INSTR_W)가 추가·제거한다."""
    not_implemented()


@router.post(
    "/instructor-applications/{application_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_instructor_application_file(
    application_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
) -> OwnerFile:
    not_implemented()


@router.get("/contents/{content_id}/files", responses=error_responses(ErrorCode.NOT_FOUND))
def list_content_files(content_id: Serial) -> OwnerFileList:
    """비주얼·배너·팝업의 이미지. 담당자(AU.SITE_W)만 보고 jpg·png 한 장만 둔다."""
    not_implemented()


@router.post(
    "/contents/{content_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_content_file(
    content_id: Serial,
    file: Annotated[UploadFile, File(description="이미지 한 장")],
    idempotency_key: IdempotencyKey,
) -> OwnerFile:
    """이미지를 쓰지 않는 유형이거나 이미 한 장이 있으면 RULE_REJECTED다. 한 장을 바꾸려면 먼저 제거한다."""
    not_implemented()


@router.delete(
    "/files/{file_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def delete_file(file_id: Serial, request: Request, db: Db, admin: MeWrite, clock: Now) -> None:
    """논리삭제한다. 소유 업무가 잠겼으면 409다. 물리 삭제는 보존기간 뒤에 한다."""
    service.delete_file(db, admin, now=clock(), request_id=request_id_of(request), file_id=file_id)


@router.get(
    "/files/{file_id}/download",
    response_class=Response,
    responses={**error_responses(ErrorCode.NOT_FOUND), **BINARY},
)
def download_admin_file(
    file_id: Serial, request: Request, db: Db, admin: Me, settings: Config, clock: Now
) -> Response:
    """검사를 통과한 파일만 내려준다. 권한이 없으면 404다. 비공개 파일과 관리자 내려받기는 기록한다."""
    return service.download_file(
        db, settings, admin, now=clock(), request_id=request_id_of(request), file_id=file_id
    )
