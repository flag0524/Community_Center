# 첨부파일 내려받기 판정. 파일은 소유 업무의 지금 공개 상태를 따르고 검사를 통과한 것만 나간다(TRD 4.5, NF-SER-002)
from datetime import datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_BBS, TB_CORS, TB_FILE, TB_PST, TB_SITE_CONTS
from app.domain.board.service import ATTACH, IMAGE, SAFE, public_post_conditions
from app.domain.course.service import VISIBLE_STATUSES
from app.domain.site.service import published_window
from app.files.storage import StorageError, read_blob

HOME_CONTENT_TYPES = ("CT.BANNER", "CT.POPUP")  # 이미지를 올릴 수 있는 홈 콘텐츠
FILE_URL = "/api/v1/files/{}"


def file_url(file_sn: int) -> str:
    return FILE_URL.format(file_sn)


def public_file(db: Session, bundle_sn: int, file_id: str, now: datetime) -> Any:
    """주민에게 열어도 되는 파일 행. 아니면 None이다. 소유 업무가 없거나 비공개가 되면 곧바로 닫힌다."""
    file = db.execute(
        select(TB_FILE).where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.FILE_SN == int(file_id),
            TB_FILE.c.FILE_STTS_CD == SAFE,
        )
    ).first()
    if file is None:
        return None
    if file.PST_SN is not None:
        owner = exists().where(
            TB_PST.c.PST_SN == file.PST_SN,
            TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN,
            TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN,
            TB_BBS.c.ATCH_USE_YN == "Y",
            *public_post_conditions(bundle_sn, now),
        )
        allowed = file.FILE_USE_CD in (ATTACH, IMAGE)
    elif file.SITE_CONTS_SN is not None:
        owner = exists().where(
            TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn,
            TB_SITE_CONTS.c.SITE_CONTS_SN == file.SITE_CONTS_SN,
            TB_SITE_CONTS.c.CONTS_TYPE_CD.in_(HOME_CONTENT_TYPES),
            published_window(now),
        )
        allowed = file.FILE_USE_CD == IMAGE
    elif file.CORS_SN is not None:
        owner = exists().where(
            TB_CORS.c.OPER_BNDL_SN == bundle_sn,
            TB_CORS.c.CORS_SN == file.CORS_SN,
            TB_CORS.c.CORS_STTS_CD.in_(VISIBLE_STATUSES),
        )
        allowed = file.FILE_USE_CD == "FP.PLAN"
    else:
        return None  # 감면 증빙·강사 지원서·만족도 자료 등 비공개 소유자
    if not allowed or not db.execute(select(owner)).scalar_one():
        return None
    return file


def download(
    db: Session, settings: Settings, bundle_sn: int, file_id: str, now: datetime
) -> tuple[Any, bytes]:
    file = public_file(db, bundle_sn, file_id, now)
    if file is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    try:
        return file, read_blob(settings.file_root, str(file.STRG_KEY))
    except StorageError:
        raise ApiError(ErrorCode.INTERNAL_ERROR) from None
