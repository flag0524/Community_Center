# 회원의 첨부 라우터. 자기 강사 지원서·문의에만 올리고 제거하며 자기 파일만 내려받는다
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Request, Response, Security, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import Clock, Member, get_clock, request_id_of, require_member, require_member_write
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, not_implemented
from app.db.session import get_db
from app.domain.file import member_service as service
from app.domain.file.schemas import MyFile, MyFileList
from app.domain.file.upload import MAX_BYTES
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, csrf_header, error_responses, member_session

member_router = APIRouter(
    tags=["member-file"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Now = Annotated[Clock, Depends(get_clock)]
Config = Annotated[Settings, Depends(get_settings)]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
UPLOAD_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT
)
BINARY: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}
}


def read_upload(file: UploadFile) -> bytes:
    """한도보다 한 바이트만 더 읽어 큰 파일을 통째로 메모리에 올리지 않는다. 넘침은 검증이 거절한다."""
    return file.file.read(MAX_BYTES + 1)


@member_router.get("/me/instructor-applications/{application_id}/files", responses=NOT_FOUND)
def list_my_instructor_application_files(application_id: Serial) -> MyFileList:
    """내 지원서의 증빙. 서류 검토중·보완요청일 때만 추가·제거할 수 있다."""
    not_implemented()


@member_router.post(
    "/me/instructor-applications/{application_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_my_instructor_application_file(
    application_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
) -> MyFile:
    """지원서를 먼저 저장한 뒤 파일을 한 개씩 올린다. 서버가 확장자·형식·크기·개수를 검사한다."""
    not_implemented()


@member_router.get("/me/inquiries/{post_id}/files", responses=NOT_FOUND)
def list_my_inquiry_files(post_id: Serial, db: Db, me: Me) -> MyFileList:
    """내 문의의 첨부. 답변이 달리기 전에만 추가·제거할 수 있다."""
    return service.list_files(db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, post_id=post_id)


@member_router.post(
    "/me/inquiries/{post_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_my_inquiry_file(
    post_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Config,
    clock: Now,
) -> MyFile:
    return service.upload_file(
        db,
        settings,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        post_id=post_id,
        filename=file.filename or "",
        data=read_upload(file),
        idem_key=idempotency_key,
        now=clock(),
        request_id=request_id_of(request),
    )


@member_router.get("/me/reduction-reviews/{review_id}/files", responses=NOT_FOUND)
def list_my_reduction_files(review_id: Serial, db: Db, me: Me) -> MyFileList:
    """내 사전심사의 증빙. 접수 상태일 때만 추가·제거할 수 있고 결정된 뒤에는 잠긴다(RDCT-BFHD-01)."""
    return service.list_reduction_files(
        db, member_sn=me.member_sn, bundle_sn=me.bundle_sn, review_id=review_id
    )


@member_router.post(
    "/me/reduction-reviews/{review_id}/files",
    status_code=201,
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def upload_my_reduction_file(
    review_id: Serial,
    file: Annotated[UploadFile, File(description="파일 한 개")],
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Config,
    clock: Now,
) -> MyFile:
    return service.upload_reduction_file(
        db,
        settings,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        review_id=review_id,
        filename=file.filename or "",
        data=read_upload(file),
        idem_key=idempotency_key,
        now=clock(),
        request_id=request_id_of(request),
    )


@member_router.delete(
    "/me/files/{file_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(ErrorCode.NOT_FOUND, ErrorCode.CONFLICT_STATE),
    dependencies=[Depends(csrf_header)],
)
def delete_my_file(file_id: Serial, request: Request, db: Db, me: MeWrite, clock: Now) -> None:
    """논리삭제한다. 남의 파일이거나 업무가 잠겼으면 거절한다."""
    service.delete_file(
        db,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        file_id=file_id,
        now=clock(),
        request_id=request_id_of(request),
    )


@member_router.get(
    "/me/files/{file_id}",
    response_class=Response,
    responses={**error_responses(ErrorCode.NOT_FOUND), **BINARY},
)
def download_my_file(
    file_id: Serial, request: Request, db: Db, me: Me, settings: Config, clock: Now
) -> Response:
    """내가 올린 파일 중 검사를 통과한 것만 내려준다. 남의 파일은 같은 404다."""
    return service.download_file(
        db,
        settings,
        member_sn=me.member_sn,
        bundle_sn=me.bundle_sn,
        file_id=file_id,
        now=clock(),
        request_id=request_id_of(request),
    )
