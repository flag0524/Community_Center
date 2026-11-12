# 관리자 첨부파일: 소유 업무(강좌·환불)별 올리기·목록, 전체 목록·상세·논리삭제·내려받기와 감사 기록(NF-SER-002, FILE-10, ADR-052)
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import Response
from sqlalchemy import and_, func, or_, select, true, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, scope_for
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import (
    TB_ATNLC_APLY,
    TB_BBS,
    TB_CORS,
    TB_FILE,
    TB_JOB_HSTRY,
    TB_MNGR,
    TB_PST,
    TB_RFND,
    TB_STLM,
)
from app.domain.admin.file_schemas import (
    AdminFile,
    AdminFilePage,
    AdminFileSummary,
    DownloadRecord,
    OwnerFile,
    OwnerFileList,
)
from app.domain.admin.term_types import FileOwnerKind, FilePurpose, FileStatus
from app.domain.admin.types import AdminAuthority as AU
from app.domain.application.seats import lock_course
from app.domain.file.upload import ALLOWED_EXTENSIONS, MAX_BYTES, Upload, validate_upload
from app.files.storage import StorageError, new_key, read_blob, remove_blob, write_blob

STATUS = {
    "FS.PENDING": FileStatus.PENDING,
    "FS.SAFE": FileStatus.SAFE,
    "FS.BLOCK": FileStatus.BLOCK,
    "FS.DELETE": FileStatus.DELETE,
}
STATUS_CODE = {value: code for code, value in STATUS.items()}
PURPOSE = {
    "FP.ATTACH": FilePurpose.ATTACH,
    "FP.PLAN": FilePurpose.PLAN,
    "FP.PROOF": FilePurpose.PROOF,
    "FP.IMAGE": FilePurpose.IMAGE,
}
COURSE_EDITABLE = ("CS.DRAFT", "CS.OPEN", "CS.RUN", "CS.CLOSE")  # 폐강·종료한 강좌는 잠긴다
REFUND_EDITABLE = ("RS.REQUEST", "RS.HOLD")  # 접수·보류 상태에서만 증빙을 더하고 뺀다


@dataclass(frozen=True)
class Owner:
    """파일의 소유 업무와 이 담당자의 권한. 파일의 접근 권한은 소유 업무의 접근 권한이다(FILE-10)."""

    kind: FileOwnerKind
    column: str  # TB_FILE의 소유자 컬럼
    sn: int
    label: str
    can_view: bool
    can_write: bool  # 파일을 더하고 뺄 권한이 있다
    can_edit: bool  # 권한이 있고 소유 업무가 잠기지 않았다
    purpose: str
    max_files: int


KINDS = {
    FileOwnerKind.COURSE: ("CORS_SN", "FP.PLAN", 1),  # 강의계획서는 한 개이고 바꾸려면 먼저 제거한다
    FileOwnerKind.REFUND: ("RFND_SN", "FP.PROOF", 5),
    FileOwnerKind.POST: ("PST_SN", "FP.ATTACH", 5),  # 갤러리 게시판은 이미지(FP.IMAGE) 열 장이다
}
GALLERY_IMAGES = 10
IMAGE_EXTENSIONS = ("jpg", "jpeg", "png")


def _covers(scope: Scope, dong_sn: Any) -> bool:
    return scope.covers(None if dong_sn is None else int(dong_sn))


def _course_owner(db: Session, admin: Admin, now: datetime, sn: int) -> Owner | None:
    row = db.execute(
        select(TB_CORS.c.CORS_NM, TB_CORS.c.DONG_SN, TB_CORS.c.CORS_STTS_CD).where(
            TB_CORS.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS.c.CORS_SN == sn
        )
    ).first()
    if row is None:
        return None
    # 문서는 강의계획서 첨부를 강좌를 고칠 수 있는 담당자만 본다고 정한다(관리자 파일 라우터 설명)
    write = _covers(scope_for(db, admin, AU.CORS_W, now), row.DONG_SN)
    column, purpose, limit = KINDS[FileOwnerKind.COURSE]
    return Owner(
        FileOwnerKind.COURSE,
        column,
        sn,
        str(row.CORS_NM),
        write,
        write,
        write and row.CORS_STTS_CD in COURSE_EDITABLE,
        purpose,
        limit,
    )


def _refund_owner(db: Session, admin: Admin, now: datetime, sn: int) -> Owner | None:
    row = db.execute(
        select(TB_RFND.c.RFND_STTS_CD, TB_CORS.c.DONG_SN)
        .join(TB_STLM, TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN)
        .join(TB_ATNLC_APLY, TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN)
        .join(TB_CORS, TB_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN)
        .where(TB_RFND.c.OPER_BNDL_SN == admin.bundle_sn, TB_RFND.c.RFND_SN == sn)
    ).first()
    if row is None:
        return None
    view = _covers(scope_for(db, admin, AU.RFND_A, now), row.DONG_SN) or _covers(
        scope_for(db, admin, AU.RFND_X, now), row.DONG_SN
    )
    write = _covers(scope_for(db, admin, AU.RFND_A, now), row.DONG_SN)
    column, purpose, limit = KINDS[FileOwnerKind.REFUND]
    return Owner(
        FileOwnerKind.REFUND,
        column,
        sn,
        f"환불 {sn}",
        view,
        write,
        write and row.RFND_STTS_CD in REFUND_EDITABLE,
        purpose,
        limit,
    )


def _post_owner(db: Session, admin: Admin, now: datetime, sn: int) -> Owner | None:
    row = db.execute(
        select(
            TB_PST.c.PST_TTL,
            TB_PST.c.DONG_SN,
            TB_PST.c.WRT_MBR_SN,
            TB_BBS.c.ATCH_USE_YN,
            TB_BBS.c.BBS_TYPE_CD,
        )
        .join(TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN))
        .where(
            TB_PST.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_PST.c.PST_SN == sn,
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),
        )
    ).first()
    if row is None:
        return None
    write = _covers(scope_for(db, admin, AU.POST_W, now), row.DONG_SN)
    column, purpose, limit = KINDS[FileOwnerKind.POST]
    if row.BBS_TYPE_CD == "BT.GALLERY":
        purpose, limit = "FP.IMAGE", GALLERY_IMAGES
    # 첨부를 끈 게시판과 회원이 쓴 글(내용을 고칠 수 없다)에는 파일을 더하거나 빼지 못한다
    editable = write and row.ATCH_USE_YN == "Y" and row.WRT_MBR_SN is None
    return Owner(FileOwnerKind.POST, column, sn, str(row.PST_TTL), write, write, editable, purpose, limit)


def owner_of(db: Session, admin: Admin, now: datetime, kind: FileOwnerKind, sn: int) -> Owner:
    """권한이 없거나 없는 소유 업무는 같은 404다."""
    found = (
        _course_owner(db, admin, now, sn)
        if kind is FileOwnerKind.COURSE
        else _post_owner(db, admin, now, sn)
        if kind is FileOwnerKind.POST
        else _refund_owner(db, admin, now, sn)
    )
    if found is None or not found.can_view:
        raise ApiError(ErrorCode.NOT_FOUND)
    return found


def _live(owner: Owner) -> Any:
    return and_(TB_FILE.c[owner.column] == owner.sn, TB_FILE.c.FILE_STTS_CD != "FS.DELETE")


def _owner_file(row: Any) -> OwnerFile:
    return OwnerFile(
        file_id=str(int(row.FILE_SN)),
        file_name=str(row.FILE_NM),
        size_bytes=int(row.FILE_SZ),
        status=STATUS[str(row.FILE_STTS_CD)],
        registered_on=kst_today(row.REG_DT),
        block_reason=None,  # 차단 사유를 담을 컬럼이 없고 탐지 이름은 노출하지 않는다(개정 요청 R31)
    )


def list_owner_files(
    db: Session, admin: Admin, *, now: datetime, kind: FileOwnerKind, sn: int
) -> OwnerFileList:
    owner = owner_of(db, admin, now, kind, sn)
    rows = db.execute(
        select(TB_FILE)
        .where(TB_FILE.c.OPER_BNDL_SN == admin.bundle_sn, _live(owner))
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
    ).all()
    return OwnerFileList(
        items=[_owner_file(r) for r in rows],
        can_edit=owner.can_edit,
        max_files=owner.max_files,
        max_bytes=MAX_BYTES,
        allowed_extensions=ALLOWED_EXTENSIONS,
    )


def _idem_mark(idem_key: str, owner: Owner, upload: Upload) -> str:
    """파일 테이블에 멱등키 컬럼이 없어 키와 (소유 업무, 내용 해시)를 작업이력 메모에 남긴다(개정 요청 R28)."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    body = hashlib.sha256(
        f"{owner.kind.value}:{owner.sn}:{upload.sha256}:{upload.name}".encode()
    ).hexdigest()[:16]
    return f"[idem {key}:{body}]"


def upload_owner_file(
    db: Session,
    settings: Settings,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    kind: FileOwnerKind,
    sn: int,
    filename: str,
    data: bytes,
    idem_key: str,
) -> OwnerFile:
    """업무를 먼저 저장한 뒤 파일을 한 개씩 올린다. 서버가 확장자·형식·크기·개수를 검사하고 검사 대기로 저장한다."""
    owner = owner_of(db, admin, now, kind, sn)
    if not owner.can_write:
        raise ApiError(ErrorCode.FORBIDDEN)  # 볼 수는 있지만 파일을 더할 권한이 없다
    if not owner.can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE)  # 소유 업무가 잠겼다(폐강·종료, 환불 승인 이후)
    upload = validate_upload(filename, data)
    if owner.purpose == "FP.IMAGE" and upload.extension not in IMAGE_EXTENSIONS:
        message = "갤러리에는 이미지(jpg·jpeg·png)만 올릴 수 있습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"file": message})
    # 같은 소유 업무의 올리기를 한 줄로 세워 멱등 표식 조회와 개수 검사와 삽입 사이의 틈을 막는다
    if owner.kind is FileOwnerKind.COURSE:
        lock_course(db, admin.bundle_sn, sn)
    elif owner.kind is FileOwnerKind.POST:
        db.execute(select(TB_PST.c.PST_SN).where(TB_PST.c.PST_SN == sn).with_for_update()).one()
    else:
        db.execute(select(TB_RFND.c.RFND_SN).where(TB_RFND.c.RFND_SN == sn).with_for_update()).one()
    mark = _idem_mark(idem_key, owner, upload)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == "FILE_UPLOAD",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        again = db.execute(select(TB_FILE).where(TB_FILE.c.FILE_SN == int(prior.TRGT_KEY_VL))).first()
        if again is not None:
            return _owner_file(again)
    live = int(
        db.execute(
            select(func.count())
            .select_from(TB_FILE)
            .where(TB_FILE.c.OPER_BNDL_SN == admin.bundle_sn, _live(owner))
        ).scalar_one()
    )
    if live >= owner.max_files:
        message = f"파일은 {owner.max_files}개까지 올릴 수 있습니다. 먼저 기존 파일을 제거해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"file": message})
    key = new_key(admin.bundle_sn)
    try:
        write_blob(settings.file_root, key, upload.data)
    except StorageError:
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
    try:
        file_sn = int(
            db.execute(
                TB_FILE.insert()
                .values(
                    OPER_BNDL_SN=admin.bundle_sn,
                    FILE_NM=upload.name,
                    STRG_KEY=key,
                    MIME_TYPE_NM=upload.mime,
                    FILE_SZ=upload.size,
                    FILE_HASH_VL=upload.sha256,
                    FILE_STTS_CD="FS.PENDING",  # 업로드 즉시 검사 대기. 검사를 통과해야 내려받을 수 있다
                    FILE_USE_CD=owner.purpose,
                    SORT_SEQ=live + 1,
                    REG_DT=now,
                    **{owner.column: owner.sn},
                )
                .returning(TB_FILE.c.FILE_SN)
            ).scalar_one()
        )
    except Exception:
        remove_blob(settings.file_root, key)  # DB에 못 남긴 파일은 고아가 되지 않게 치운다
        raise
    record_job(
        db,
        actor="AK.ADMIN",
        job="FILE_UPLOAD",
        table="TB_FILE",
        key=file_sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"{owner.kind.value} {owner.sn} 첨부 {upload.size}바이트 {mark}",
    )
    row = db.execute(select(TB_FILE).where(TB_FILE.c.FILE_SN == file_sn)).one()
    return _owner_file(row)


# --- 전체 목록·상세 ---------------------------------------------------------------------------


def _visible_files(db: Session, admin: Admin, now: datetime) -> Any:
    """이 담당자가 소유 업무에 접근할 수 있는 파일의 조건. 소유 업무가 구현되지 않은 종류는 아직 보이지 않는다."""
    course_scope = scope_for(db, admin, AU.CORS_W, now)
    refund_a, refund_x = scope_for(db, admin, AU.RFND_A, now), scope_for(db, admin, AU.RFND_X, now)
    refund_scope = Scope(refund_a.whole or refund_x.whole, refund_a.dongs | refund_x.dongs)
    post_scope = scope_for(db, admin, AU.POST_W, now)
    if course_scope.empty() and refund_scope.empty() and post_scope.empty():
        raise ApiError(ErrorCode.FORBIDDEN)
    pieces = []
    if not course_scope.empty():
        pieces.append(
            and_(
                TB_FILE.c.CORS_SN.is_not(None),
                true() if course_scope.whole else TB_CORS.c.DONG_SN.in_(course_scope.dongs),
            )
        )
    if not refund_scope.empty():
        pieces.append(
            and_(
                TB_FILE.c.RFND_SN.is_not(None),
                true() if refund_scope.whole else RFND_CORS.c.DONG_SN.in_(refund_scope.dongs),
            )
        )
    if not post_scope.empty():
        pieces.append(
            and_(
                TB_FILE.c.PST_SN.is_not(None),
                TB_PST.c.DEL_YN == "N",
                true() if post_scope.whole else TB_PST.c.DONG_SN.in_(post_scope.dongs),
            )
        )
    return or_(*pieces)


RFND_CORS = TB_CORS.alias("rfnd_cors")


def _query(admin: Admin) -> Any:
    source = (
        TB_FILE.outerjoin(TB_CORS, TB_CORS.c.CORS_SN == TB_FILE.c.CORS_SN)
        .outerjoin(TB_RFND, TB_RFND.c.RFND_SN == TB_FILE.c.RFND_SN)
        .outerjoin(TB_STLM, TB_STLM.c.STLM_SN == TB_RFND.c.STLM_SN)
        .outerjoin(TB_ATNLC_APLY, TB_ATNLC_APLY.c.ATNLC_APLY_SN == TB_STLM.c.ATNLC_APLY_SN)
        .outerjoin(RFND_CORS, RFND_CORS.c.CORS_SN == TB_ATNLC_APLY.c.CORS_SN)
        .outerjoin(TB_PST, TB_PST.c.PST_SN == TB_FILE.c.PST_SN)
    )
    return (
        select(TB_FILE, TB_CORS.c.CORS_NM, TB_PST.c.PST_TTL)
        .select_from(source)
        .where(TB_FILE.c.OPER_BNDL_SN == admin.bundle_sn)
    )


def _summary(row: Any) -> AdminFileSummary:
    if row.CORS_SN is not None:
        kind, label = FileOwnerKind.COURSE, str(row.CORS_NM)
    elif row.PST_SN is not None:
        kind, label = FileOwnerKind.POST, str(row.PST_TTL)
    else:
        kind, label = FileOwnerKind.REFUND, f"환불 {int(row.RFND_SN)}"
    return AdminFileSummary(
        file_id=str(int(row.FILE_SN)),
        file_name=str(row.FILE_NM),
        owner_kind=kind,
        owner_label=label,
        size_bytes=int(row.FILE_SZ),
        status=STATUS[str(row.FILE_STTS_CD)],
        registered_on=kst_today(row.REG_DT),
    )


def list_files(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    owner_kind: FileOwnerKind | None,
    status: FileStatus | None,
    q: str | None,
    page: int,
    size: int,
) -> AdminFilePage:
    """소유 업무에 접근 권한이 없는 파일은 조건과 무관하게 나오지 않는다(RQ-SER-NF-009). 삭제한 파일은 상태로 고를 때만 보인다."""
    query = _query(admin).where(_visible_files(db, admin, now))
    if owner_kind is FileOwnerKind.COURSE:
        query = query.where(TB_FILE.c.CORS_SN.is_not(None))
    elif owner_kind is FileOwnerKind.REFUND:
        query = query.where(TB_FILE.c.RFND_SN.is_not(None))
    elif owner_kind is FileOwnerKind.POST:
        query = query.where(TB_FILE.c.PST_SN.is_not(None))
    elif owner_kind is not None:
        query = query.where(TB_FILE.c.FILE_SN == -1)  # 아직 구현되지 않은 소유 업무의 파일은 없다
    query = (
        query.where(TB_FILE.c.FILE_STTS_CD == STATUS_CODE[status])
        if status is not None
        else query.where(TB_FILE.c.FILE_STTS_CD != "FS.DELETE")
    )
    if q and q.strip():
        query = query.where(TB_FILE.c.FILE_NM.contains(q.strip(), autoescape=True))
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(
        query.order_by(TB_FILE.c.REG_DT.desc(), TB_FILE.c.FILE_SN.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    return AdminFilePage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def _file_and_owner(db: Session, admin: Admin, now: datetime, file_id: str) -> tuple[Any, Owner]:
    """파일과 그 소유 업무. 파일이 없거나 소유 업무를 볼 수 없으면 404다. 구현되지 않은 소유 업무의 파일도 같다."""
    row = db.execute(
        select(TB_FILE).where(TB_FILE.c.OPER_BNDL_SN == admin.bundle_sn, TB_FILE.c.FILE_SN == int(file_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if row.CORS_SN is not None:
        owner = _course_owner(db, admin, now, int(row.CORS_SN))
    elif row.RFND_SN is not None:
        owner = _refund_owner(db, admin, now, int(row.RFND_SN))
    elif row.PST_SN is not None:
        owner = _post_owner(db, admin, now, int(row.PST_SN))
    else:
        owner = None
    if owner is None or not owner.can_view:
        _denied(db, admin, now, int(row.FILE_SN))
        raise ApiError(ErrorCode.NOT_FOUND)
    return row, owner


def _denied(db: Session, admin: Admin, now: datetime, file_sn: int) -> None:
    """있는 파일을 권한 없이 열려 한 시도를 남긴다. 오류 응답이 되돌려도 남도록 먼저 확정한다."""
    record_job(
        db,
        actor="AK.ADMIN",
        job="FILE_DOWNLOAD",
        table="TB_FILE",
        key=file_sn,
        request_id="denied",
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        result="JR.DENY",
        change="권한 없는 파일 접근",
    )
    db.commit()


def get_file(db: Session, admin: Admin, *, now: datetime, file_id: str) -> AdminFile:
    row, _ = _file_and_owner(db, admin, now, file_id)
    if row.FILE_STTS_CD == "FS.DELETE":
        raise ApiError(ErrorCode.NOT_FOUND)
    downloads = db.execute(
        select(TB_JOB_HSTRY.c.REG_DT, TB_MNGR.c.MNGR_NM)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN)
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == "FILE_DOWNLOAD",
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_FILE",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(int(row.FILE_SN)),
            TB_JOB_HSTRY.c.JOB_RSLT_CD == "JR.SUCCESS",
        )
        .order_by(TB_JOB_HSTRY.c.REG_DT.desc(), TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
    ).all()
    summary = _summary(db.execute(_query(admin).where(TB_FILE.c.FILE_SN == int(row.FILE_SN))).one())
    return AdminFile(
        **summary.model_dump(),
        purpose=PURPOSE[str(row.FILE_USE_CD)],
        mime_type=str(row.MIME_TYPE_NM),
        hash_prefix=str(row.FILE_HASH_VL)[:8],
        block_reason=None,
        downloads=[
            DownloadRecord(at=utc(d.REG_DT), by=str(d.MNGR_NM or "담당자"), by_admin=True) for d in downloads
        ],
    )


def delete_file(db: Session, admin: Admin, *, now: datetime, request_id: str, file_id: str) -> None:
    """논리삭제한다. 소유 업무가 잠겼으면 409다. 물리 삭제는 보존기간 뒤에 한다."""
    row, owner = _file_and_owner(db, admin, now, file_id)
    if row.FILE_STTS_CD == "FS.DELETE":
        raise ApiError(ErrorCode.NOT_FOUND)
    if not owner.can_write:
        raise ApiError(ErrorCode.FORBIDDEN)
    if not owner.can_edit:
        raise ApiError(ErrorCode.CONFLICT_STATE)
    db.execute(
        update(TB_FILE).where(TB_FILE.c.FILE_SN == row.FILE_SN).values(FILE_STTS_CD="FS.DELETE", MDFCN_DT=now)
    )
    record_job(
        db,
        actor="AK.ADMIN",
        job="FILE_DELETE",
        table="TB_FILE",
        key=int(row.FILE_SN),
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"{owner.kind.value} {owner.sn} 첨부 삭제",
    )


def download_file(
    db: Session, settings: Settings, admin: Admin, *, now: datetime, request_id: str, file_id: str
) -> Response:
    """검사를 통과한 파일만 내려준다. 권한이 없으면 404다. 관리자 내려받기는 허용과 거절을 모두 기록한다."""
    row, _ = _file_and_owner(db, admin, now, file_id)
    if row.FILE_STTS_CD != "FS.SAFE":  # 검사 대기·차단·삭제는 내려주지 않는다
        _denied(db, admin, now, int(row.FILE_SN))
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        content = read_blob(settings.file_root, str(row.STRG_KEY))
    except StorageError:
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
    record_job(
        db,
        actor="AK.ADMIN",
        job="FILE_DOWNLOAD",
        table="TB_FILE",
        key=int(row.FILE_SN),
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change="관리자 내려받기",
    )
    return Response(
        content,
        media_type=str(row.MIME_TYPE_NM),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(str(row.FILE_NM))}",
            "X-Content-Type-Options": "nosniff",  # 브라우저가 내용을 추측해 실행하지 않게 한다
            "Cache-Control": "private, no-store",
        },
    )
