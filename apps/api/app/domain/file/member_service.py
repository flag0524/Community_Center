# 주민 쪽 첨부파일(문의 첨부). 본인 문의에만 올리고 지우며 본인 파일만 내려받는다(RQ-SER-NF-002, DV179, ADR-059)
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_BBS, TB_FILE, TB_PST, TB_RDCT_BFHD_SRNG
from app.domain.admin.file_service import (
    KINDS,
    Owner,
    _live,
    _owner_file,
    lock_owner,
    store_upload,
)
from app.domain.admin.term_types import FileOwnerKind
from app.domain.file.schemas import MyFile, MyFileList
from app.domain.file.upload import ALLOWED_EXTENSIONS, MAX_BYTES, validate_upload
from app.files.storage import StorageError, read_blob

MAX_FILES = 5  # 문의 한 건의 첨부 한도. 문서에 없어 둔 값이다(개정 요청 R31)
REPLY = TB_PST.alias("reply")


def _owner(db: Session, member_sn: int, bundle_sn: int, post_id: int) -> Owner:
    """본인의 지우지 않은 문의만이다. 남의 문의는 공개 글이어도 없는 것과 같게 404다."""
    row = db.execute(
        select(
            TB_PST.c.PST_TTL,
            TB_PST.c.WRT_MBR_SN,
            TB_BBS.c.ATCH_USE_YN,
            select(REPLY.c.PST_SN)
            .where(
                REPLY.c.UP_PST_SN == TB_PST.c.PST_SN, REPLY.c.DEL_YN == "N", REPLY.c.PST_TYPE_CD == "PT.REPLY"
            )
            .exists()
            .label("ANSWERED"),
        )
        .join(TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN))
        .where(
            TB_PST.c.OPER_BNDL_SN == bundle_sn,
            TB_PST.c.PST_SN == post_id,
            TB_BBS.c.BBS_ID == "qna",
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),
        )
    ).first()
    if row is None or row.WRT_MBR_SN is None or int(row.WRT_MBR_SN) != member_sn:
        raise ApiError(ErrorCode.NOT_FOUND)
    # 답변이 달리면 잠긴다. 게시판이 첨부를 쓰지 않아도 잠긴다
    editable = not row.ANSWERED and row.ATCH_USE_YN == "Y"
    return Owner(
        FileOwnerKind.POST, "PST_SN", post_id, str(row.PST_TTL), True, True, editable, "FP.ATTACH", MAX_FILES
    )


def _reduction_owner(db: Session, member_sn: int, bundle_sn: int, review_id: int) -> Owner:
    """본인의 감면 사전심사만이다. 접수 상태일 때만 더하고 빼며 결정·철회된 뒤에는 잠긴다(RDCT-BFHD-01)."""
    row = db.execute(
        select(TB_RDCT_BFHD_SRNG.c.SRNG_STTS_CD).where(
            TB_RDCT_BFHD_SRNG.c.OPER_BNDL_SN == bundle_sn,
            TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == review_id,
            TB_RDCT_BFHD_SRNG.c.MBR_SN == member_sn,
        )
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    editable = row.SRNG_STTS_CD == "DS.RECEIVED"
    column, purpose, limit = KINDS[FileOwnerKind.REDUCTION]
    return Owner(
        FileOwnerKind.REDUCTION,
        column,
        review_id,
        f"감면 심사 {review_id}",
        True,
        True,
        editable,
        purpose,
        limit,
    )


def _my_file(row: Any) -> MyFile:
    return MyFile(**_owner_file(row).model_dump())


def list_reduction_files(db: Session, *, member_sn: int, bundle_sn: int, review_id: str) -> MyFileList:
    return _list(db, bundle_sn, _reduction_owner(db, member_sn, bundle_sn, int(review_id)))


def upload_reduction_file(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    review_id: str,
    filename: str,
    data: bytes,
    idem_key: str,
    now: datetime,
    request_id: str,
) -> MyFile:
    """접수 상태일 때만 올린다. 심사 행을 잠근 뒤 다시 확인해 관리자 결정·철회와 겹쳐도 결정 뒤에는 올라가지 않는다."""
    sn = int(review_id)
    locked = "접수 상태인 심사에만 증빙을 올릴 수 있습니다."
    if not _reduction_owner(db, member_sn, bundle_sn, sn).can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE, locked)
    upload = validate_upload(filename, data)
    lock_owner(db, bundle_sn, _reduction_owner(db, member_sn, bundle_sn, sn))
    owner = _reduction_owner(db, member_sn, bundle_sn, sn)  # 잠근 뒤 다시 읽는다
    if not owner.can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE, locked)
    stored = store_upload(
        db,
        settings,
        bundle_sn=bundle_sn,
        owner=owner,
        upload=upload,
        idem_key=idem_key,
        now=now,
        request_id=request_id,
        actor="AK.MEMBER",
        member_sn=member_sn,
    )
    return MyFile(**stored.model_dump())


def list_files(db: Session, *, member_sn: int, bundle_sn: int, post_id: str) -> MyFileList:
    return _list(db, bundle_sn, _owner(db, member_sn, bundle_sn, int(post_id)))


def _list(db: Session, bundle_sn: int, owner: Owner) -> MyFileList:
    rows = db.execute(
        select(TB_FILE)
        .where(TB_FILE.c.OPER_BNDL_SN == bundle_sn, _live(owner))
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
    ).all()
    return MyFileList(
        items=[_my_file(r) for r in rows],
        can_edit=owner.can_edit,
        max_files=owner.max_files,
        max_bytes=MAX_BYTES,
        allowed_extensions=ALLOWED_EXTENSIONS,
    )


def upload_file(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    post_id: str,
    filename: str,
    data: bytes,
    idem_key: str,
    now: datetime,
    request_id: str,
) -> MyFile:
    """답변이 달리기 전에만 올린다. 문의 행을 잠근 뒤 다시 확인해 관리자 답변과 겹쳐도 답변 뒤에는 올라가지 않는다."""
    sn = int(post_id)
    if not _owner(db, member_sn, bundle_sn, sn).can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE, "답변이 달렸거나 첨부를 받지 않는 문의입니다.")
    upload = validate_upload(filename, data)
    lock_owner(db, bundle_sn, _owner(db, member_sn, bundle_sn, sn))
    owner = _owner(db, member_sn, bundle_sn, sn)  # 잠근 뒤 다시 읽는다
    if not owner.can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE, "답변이 달렸거나 첨부를 받지 않는 문의입니다.")
    stored = store_upload(
        db,
        settings,
        bundle_sn=bundle_sn,
        owner=owner,
        upload=upload,
        idem_key=idem_key,
        now=now,
        request_id=request_id,
        actor="AK.MEMBER",
        member_sn=member_sn,
    )
    return MyFile(**stored.model_dump())


def _owner_for(db: Session, member_sn: int, bundle_sn: int, row: Any) -> Owner:
    """파일의 소유 업무. 문의 첨부와 감면 증빙만 주민이 다룬다."""
    if row.PST_SN is not None:
        return _owner(db, member_sn, bundle_sn, int(row.PST_SN))
    if row.RDCT_BFHD_SRNG_SN is not None:
        return _reduction_owner(db, member_sn, bundle_sn, int(row.RDCT_BFHD_SRNG_SN))
    raise ApiError(ErrorCode.NOT_FOUND)


def _mine(db: Session, member_sn: int, bundle_sn: int, file_id: str, now: datetime) -> tuple[Any, Owner]:
    """파일과 그 소유 업무(문의·감면 심사). 그 밖이거나 남의 파일이면 404다. 있는 남의 파일을 열려 한 시도는 기록한다."""
    row = db.execute(
        select(TB_FILE).where(TB_FILE.c.OPER_BNDL_SN == bundle_sn, TB_FILE.c.FILE_SN == int(file_id))
    ).first()
    if row is None or (row.PST_SN is None and row.RDCT_BFHD_SRNG_SN is None):
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        owner = _owner_for(db, member_sn, bundle_sn, row)
    except ApiError:
        _denied(db, member_sn, bundle_sn, int(row.FILE_SN), now)
        raise
    return row, owner


def _denied(db: Session, member_sn: int, bundle_sn: int, file_sn: int, now: datetime) -> None:
    """남의 파일을 열려 한 시도를 남긴다. 오류 응답이 되돌려도 남도록 먼저 확정한다."""
    record_job(
        db,
        actor="AK.MEMBER",
        job="FILE_DOWNLOAD",
        table="TB_FILE",
        key=file_sn,
        request_id="denied",
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        result="JR.DENY",
        change="권한 없는 파일 접근",
    )
    db.commit()


def delete_file(
    db: Session, *, member_sn: int, bundle_sn: int, file_id: str, now: datetime, request_id: str
) -> None:
    """논리삭제한다. 남의 파일이면 404, 문의가 잠겼으면 409다. 물리 삭제는 보존기간 뒤에 한다."""
    row, owner = _mine(db, member_sn, bundle_sn, file_id, now)
    if row.FILE_STTS_CD == "FS.DELETE":
        raise ApiError(ErrorCode.NOT_FOUND)
    lock_owner(db, bundle_sn, owner)
    owner = _owner_for(db, member_sn, bundle_sn, row)  # 잠근 뒤 다시 읽는다
    if not owner.can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE, "답변이 달렸거나 접수 상태가 아니어서 고칠 수 없습니다.")
    current = db.execute(select(TB_FILE.c.FILE_STTS_CD).where(TB_FILE.c.FILE_SN == row.FILE_SN)).one()
    if current.FILE_STTS_CD == "FS.DELETE":
        raise ApiError(ErrorCode.NOT_FOUND)
    db.execute(
        update(TB_FILE).where(TB_FILE.c.FILE_SN == row.FILE_SN).values(FILE_STTS_CD="FS.DELETE", MDFCN_DT=now)
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="FILE_DELETE",
        table="TB_FILE",
        key=int(row.FILE_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"{owner.kind.value} {owner.sn} 첨부 삭제",
    )


def download_file(
    db: Session,
    settings: Settings,
    *,
    member_sn: int,
    bundle_sn: int,
    file_id: str,
    now: datetime,
    request_id: str,
) -> Response:
    """내가 올린 파일 중 검사를 통과한 것만 내려준다. 남의 파일과 검사 전·차단 파일은 같은 404다."""
    row, _ = _mine(db, member_sn, bundle_sn, file_id, now)
    if row.FILE_STTS_CD != "FS.SAFE":
        _denied(db, member_sn, bundle_sn, int(row.FILE_SN), now)
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        content = read_blob(settings.file_root, str(row.STRG_KEY))
    except StorageError:
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
    record_job(
        db,
        actor="AK.MEMBER",
        job="FILE_DOWNLOAD",
        table="TB_FILE",
        key=int(row.FILE_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="주민 내려받기",
    )
    return Response(
        content,
        media_type=str(row.MIME_TYPE_NM),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(str(row.FILE_NM))}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
