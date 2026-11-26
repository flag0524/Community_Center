# 첨부파일의 소유 업무·잠금·저장 코어. 접근 권한은 소유 업무를 따른다(FILE-10). 관리자·주민이 함께 쓴다(ADR-113)
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.audit import Actor, record_job
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.core.times import kst_today
from app.db.tables import (
    TB_FCLT,
    TB_FILE,
    TB_INSTR_APLY,
    TB_JOB_HSTRY,
    TB_PST,
    TB_RDCT_BFHD_SRNG,
    TB_RFND,
    TB_SITE_CONTS,
)
from app.domain.application.seats import lock_course
from app.domain.file.schemas import OwnerFile
from app.domain.file.types import FileOwnerKind, FileStatus
from app.domain.file.upload import Upload
from app.files.storage import StorageError, new_key, remove_blob, write_blob

STATUS = {
    "FS.PENDING": FileStatus.PENDING,
    "FS.SAFE": FileStatus.SAFE,
    "FS.BLOCK": FileStatus.BLOCK,
    "FS.DELETE": FileStatus.DELETE,
}
STATUS_CODE = {value: code for code, value in STATUS.items()}


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
    accepts_files: bool = True  # 이 소유 업무의 유형이 파일을 쓰는가(이미지를 쓰지 않는 콘텐츠 유형은 false)


KINDS = {
    FileOwnerKind.COURSE: ("CORS_SN", "FP.PLAN", 1),  # 강의계획서는 한 개이고 바꾸려면 먼저 제거한다
    FileOwnerKind.REFUND: ("RFND_SN", "FP.PROOF", 5),
    FileOwnerKind.POST: ("PST_SN", "FP.ATTACH", 5),  # 갤러리 게시판은 이미지(FP.IMAGE) 열 장이다
    # 주민이 올리고 관리자는 열람만 한다(R31과 같은 한도)
    FileOwnerKind.REDUCTION: ("RDCT_BFHD_SRNG_SN", "FP.PROOF", 5),
    # 지원자와 묶음 전체 담당자가 서류 검토중일 때 더한다
    FileOwnerKind.INSTRUCTOR_APPLICATION: ("INSTR_APLY_SN", "FP.PROOF", 5),
    # 홈 배너·팝업의 이미지 한 장(jpg·png). 다른 유형은 이미지를 쓰지 않는다
    FileOwnerKind.CONTENT: ("SITE_CONTS_SN", "FP.IMAGE", 1),
    # 시설·강의실 사진 다섯 장. 정렬순서의 맨 앞이 대표 사진이다(ADR-129)
    FileOwnerKind.FACILITY: ("FCLT_SN", "FP.IMAGE", 5),
}
INSTRUCTOR_EDITABLE = ("IA.WAIT",)  # 서류 검토중에만 증빙을 더하고 뺀다


def live_files(owner: Owner) -> Any:
    return and_(TB_FILE.c[owner.column] == owner.sn, TB_FILE.c.FILE_STTS_CD != "FS.DELETE")


def owner_file(row: Any) -> OwnerFile:
    return OwnerFile(
        file_id=str(int(row.FILE_SN)),
        file_name=str(row.FILE_NM),
        size_bytes=int(row.FILE_SZ),
        status=STATUS[str(row.FILE_STTS_CD)],
        registered_on=kst_today(row.REG_DT),
        block_reason=None,  # 차단 사유를 담을 컬럼이 없고 탐지 이름은 노출하지 않는다(개정 요청 R31)
    )


def _idem_mark(idem_key: str, owner: Owner, upload: Upload) -> str:
    """파일 테이블에 멱등키 컬럼이 없어 키와 (소유 업무, 내용 해시)를 작업이력 메모에 남긴다(개정 요청 R28)."""
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    body = hashlib.sha256(
        f"{owner.kind.value}:{owner.sn}:{upload.sha256}:{upload.name}".encode()
    ).hexdigest()[:16]
    return f"[idem {key}:{body}]"


def lock_owner(db: Session, bundle_sn: int, owner: Owner) -> None:
    """같은 소유 업무의 올리기를 한 줄로 세워 멱등 표식 조회와 개수 검사와 삽입 사이의 틈을 막는다."""
    if owner.kind is FileOwnerKind.COURSE:
        lock_course(db, bundle_sn, owner.sn)
    elif owner.kind is FileOwnerKind.POST:
        db.execute(select(TB_PST.c.PST_SN).where(TB_PST.c.PST_SN == owner.sn).with_for_update()).one()
    elif owner.kind is FileOwnerKind.CONTENT:
        db.execute(
            select(TB_SITE_CONTS.c.SITE_CONTS_SN)
            .where(TB_SITE_CONTS.c.SITE_CONTS_SN == owner.sn)
            .with_for_update()
        ).one()
    elif owner.kind is FileOwnerKind.FACILITY:
        db.execute(select(TB_FCLT.c.FCLT_SN).where(TB_FCLT.c.FCLT_SN == owner.sn).with_for_update()).one()
    elif owner.kind is FileOwnerKind.REDUCTION:
        db.execute(
            select(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN)
            .where(TB_RDCT_BFHD_SRNG.c.RDCT_BFHD_SRNG_SN == owner.sn)
            .with_for_update()
        ).one()
    elif owner.kind is FileOwnerKind.INSTRUCTOR_APPLICATION:
        db.execute(
            select(TB_INSTR_APLY.c.INSTR_APLY_SN)
            .where(TB_INSTR_APLY.c.INSTR_APLY_SN == owner.sn)
            .with_for_update()
        ).one()
    else:
        db.execute(select(TB_RFND.c.RFND_SN).where(TB_RFND.c.RFND_SN == owner.sn).with_for_update()).one()


def store_upload(
    db: Session,
    settings: Settings,
    *,
    bundle_sn: int,
    owner: Owner,
    upload: Upload,
    idem_key: str,
    now: datetime,
    request_id: str,
    actor: Actor,
    admin_sn: int | None = None,
    member_sn: int | None = None,
) -> OwnerFile:
    """멱등 표식 확인·개수 검사·저장·기록. 호출하기 전에 소유 업무를 잠가야 한다(lock_owner). 관리자와 주민이 함께 쓴다."""
    mark = _idem_mark(idem_key, owner, upload)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD == "FILE_UPLOAD",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        again = db.execute(select(TB_FILE).where(TB_FILE.c.FILE_SN == int(prior.TRGT_KEY_VL))).first()
        if again is not None:
            return owner_file(again)
    live = int(
        db.execute(
            select(func.count())
            .select_from(TB_FILE)
            .where(TB_FILE.c.OPER_BNDL_SN == bundle_sn, live_files(owner))
        ).scalar_one()
    )
    if live >= owner.max_files:
        message = f"파일은 {owner.max_files}개까지 올릴 수 있습니다. 먼저 기존 파일을 제거해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"file": message})
    last = int(
        db.execute(
            select(func.coalesce(func.max(TB_FILE.c.SORT_SEQ), 0)).where(
                TB_FILE.c.OPER_BNDL_SN == bundle_sn, live_files(owner)
            )
        ).scalar_one()
    )
    key = new_key(bundle_sn)
    try:
        write_blob(settings.file_root, key, upload.data)
    except StorageError:
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
    try:
        file_sn = int(
            db.execute(
                TB_FILE.insert()
                .values(
                    OPER_BNDL_SN=bundle_sn,
                    FILE_NM=upload.name,
                    STRG_KEY=key,
                    MIME_TYPE_NM=upload.mime,
                    FILE_SZ=upload.size,
                    FILE_HASH_VL=upload.sha256,
                    FILE_STTS_CD="FS.PENDING",  # 업로드 즉시 검사 대기. 검사를 통과해야 내려받을 수 있다
                    FILE_USE_CD=owner.purpose,
                    # 지운 파일이 있어도 새 파일은 맨 뒤에 놓는다(맨 앞의 대표 사진 자리를 빼앗지 않게)
                    SORT_SEQ=last + 1,
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
        actor=actor,
        job="FILE_UPLOAD",
        table="TB_FILE",
        key=file_sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        admin_sn=admin_sn,
        member_sn=member_sn,
        change=f"{owner.kind.value} {owner.sn} 첨부 {upload.size}바이트 {mark}",
    )
    row = db.execute(select(TB_FILE).where(TB_FILE.c.FILE_SN == file_sn)).one()
    return owner_file(row)
