# 읽기 게시판의 게시물 목록·상세 공개 조회와 첨부 목록. 공개 판정은 파일 내려받기와 같은 조건을 쓴다(TRD 4.4)
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import TB_BBS, TB_FILE, TB_PST
from app.domain.board.schemas import PostDetail, PostFile, PostImage, PostPage, PostSummary
from app.domain.board.types import BoardKey
from app.domain.site.schemas import PostBrief

# 이 엔드포인트가 다루는 게시판. 질문과 답변·수강후기는 비공개 글과 작성자 판정이 달라 전용 엔드포인트가 맡는다(ADR-036)
PUBLIC_BOARDS = (BoardKey.NOTICE, BoardKey.NEWS, BoardKey.RESOURCES, BoardKey.GALLERY, BoardKey.FAQ)
PUBLIC_BOARD_IDS = tuple(board.value for board in PUBLIC_BOARDS)
FAQ, DATA, GALLERY = "BT.FAQ", "BT.DATA", "BT.GALLERY"
ATTACH, IMAGE, SAFE = "FP.ATTACH", "FP.IMAGE", "FS.SAFE"


def _published_at() -> Any:
    return func.coalesce(TB_PST.c.PSTG_BGNG_DT, TB_PST.c.REG_DT)


def public_post_conditions(bundle_sn: int, now: datetime) -> list[ColumnElement[bool]]:
    """게시판이 쓰이고 글이 원글이며 지워지지도 비공개도 아니고 게시 기간 안인 글의 조건."""
    return [
        TB_PST.c.OPER_BNDL_SN == bundle_sn,
        TB_BBS.c.USE_YN == "Y",
        TB_BBS.c.BBS_ID.in_(PUBLIC_BOARD_IDS),
        TB_PST.c.DEL_YN == "N",
        TB_PST.c.PRVT_YN == "N",
        TB_PST.c.UP_PST_SN.is_(None),
        (TB_PST.c.PSTG_BGNG_DT.is_(None)) | (TB_PST.c.PSTG_BGNG_DT <= now),
        (TB_PST.c.PSTG_END_DT.is_(None)) | (TB_PST.c.PSTG_END_DT > now),
    ]


def _joined(columns: Any) -> Select[Any]:
    return select(*columns).join(
        TB_BBS, and_(TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN, TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN)
    )


def _files(db: Session, bundle_sn: int, post_sns: list[int]) -> dict[int, list[Any]]:
    """글마다 검사를 통과한 첨부·이미지를 정렬 순서로 모은다. 게시판이 첨부를 끄면 호출하지 않는다."""
    if not post_sns:
        return {}
    rows = db.execute(
        select(
            TB_FILE.c.FILE_SN,
            TB_FILE.c.PST_SN,
            TB_FILE.c.FILE_NM,
            TB_FILE.c.FILE_SZ,
            TB_FILE.c.MIME_TYPE_NM,
            TB_FILE.c.FILE_USE_CD,
        )
        .where(
            TB_FILE.c.OPER_BNDL_SN == bundle_sn,
            TB_FILE.c.PST_SN.in_(post_sns),
            TB_FILE.c.FILE_STTS_CD == SAFE,
            TB_FILE.c.FILE_USE_CD.in_([ATTACH, IMAGE]),
        )
        .order_by(TB_FILE.c.SORT_SEQ, TB_FILE.c.FILE_SN)
    ).all()
    grouped: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[int(row.PST_SN)].append(row)
    return grouped


def _post_file(row: Any) -> PostFile:
    return PostFile(
        file_id=str(int(row.FILE_SN)),
        name=str(row.FILE_NM),
        size_bytes=int(row.FILE_SZ),
        content_type=str(row.MIME_TYPE_NM),
    )


def _board(db: Session, bundle_sn: int, board: BoardKey) -> Any:
    row = db.execute(
        select(TB_BBS.c.BBS_SN, TB_BBS.c.BBS_TYPE_CD, TB_BBS.c.ATCH_USE_YN).where(
            TB_BBS.c.OPER_BNDL_SN == bundle_sn, TB_BBS.c.BBS_ID == board.value, TB_BBS.c.USE_YN == "Y"
        )
    ).first()
    if row is None or board not in PUBLIC_BOARDS:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def list_posts(
    db: Session, bundle_sn: int, now: datetime, board: BoardKey, *, q: str | None, page: int, size: int
) -> PostPage:
    bbs = _board(db, bundle_sn, board)
    conditions = [*public_post_conditions(bundle_sn, now), TB_PST.c.BBS_SN == bbs.BBS_SN]
    if q and q.strip():
        conditions.append(TB_PST.c.PST_TTL.contains(q.strip(), autoescape=True))
    total = int(db.execute(_joined([func.count()]).where(*conditions)).scalar_one())
    published = _published_at()
    rows = db.execute(
        _joined(
            [TB_PST.c.PST_SN, TB_PST.c.PST_TTL, TB_PST.c.PST_CN, TB_PST.c.NTC_YN, published.label("PUB_DT")]
        )
        .where(*conditions)
        .order_by(TB_PST.c.NTC_YN.desc(), published.desc(), TB_PST.c.PST_SN.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    files = _files(db, bundle_sn, [int(r.PST_SN) for r in rows]) if bbs.ATCH_USE_YN == "Y" else {}
    items = []
    for row in rows:
        post_files = files.get(int(row.PST_SN), [])
        attachments = [f for f in post_files if f.FILE_USE_CD == ATTACH]
        images = [f for f in post_files if f.FILE_USE_CD == IMAGE]
        items.append(
            PostSummary(
                post_id=str(int(row.PST_SN)),
                board=board,
                title=str(row.PST_TTL),
                published_at=utc(row.PUB_DT),
                pinned=row.NTC_YN == "Y",
                body=str(row.PST_CN) if bbs.BBS_TYPE_CD == FAQ else None,
                primary_file=_post_file(attachments[0]) if bbs.BBS_TYPE_CD == DATA and attachments else None,
                thumbnail=(
                    PostImage(file_id=str(int(images[0].FILE_SN)), alt=str(row.PST_TTL))
                    if bbs.BBS_TYPE_CD == GALLERY and images
                    else None
                ),
            )
        )
    return PostPage(items=items, page=page, size=size, total=total, criteria=PageCriteria(basis_at=utc(now)))


def get_post(db: Session, bundle_sn: int, now: datetime, post_id: str) -> PostDetail:
    row = db.execute(
        _joined(
            [
                TB_PST.c.PST_SN,
                TB_PST.c.PST_TTL,
                TB_PST.c.PST_CN,
                TB_PST.c.NTC_YN,
                TB_BBS.c.BBS_ID,
                TB_BBS.c.ATCH_USE_YN,
                _published_at().label("PUB_DT"),
            ]
        ).where(*public_post_conditions(bundle_sn, now), TB_PST.c.PST_SN == int(post_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    files = (
        _files(db, bundle_sn, [int(row.PST_SN)]).get(int(row.PST_SN), []) if row.ATCH_USE_YN == "Y" else []
    )
    return PostDetail(
        post_id=str(int(row.PST_SN)),
        board=BoardKey(str(row.BBS_ID)),
        title=str(row.PST_TTL),
        published_at=utc(row.PUB_DT),
        pinned=row.NTC_YN == "Y",
        body=str(row.PST_CN),
        facts=[],
        attachments=[_post_file(f) for f in files if f.FILE_USE_CD == ATTACH],
        images=[
            PostImage(file_id=str(int(f.FILE_SN)), alt=str(row.PST_TTL))
            for f in files
            if f.FILE_USE_CD == IMAGE
        ],
    )


def notice_briefs(db: Session, bundle_sn: int, now: datetime, limit: int) -> list[PostBrief]:
    """홈에 보일 공지사항. 상단공지가 먼저, 그다음 최근 글 순이다."""
    published = _published_at()
    rows = db.execute(
        _joined([TB_PST.c.PST_SN, TB_PST.c.PST_TTL, TB_PST.c.NTC_YN, published.label("PUB_DT")])
        .where(*public_post_conditions(bundle_sn, now), TB_BBS.c.BBS_ID == BoardKey.NOTICE.value)
        .order_by(TB_PST.c.NTC_YN.desc(), published.desc(), TB_PST.c.PST_SN.desc())
        .limit(limit)
    ).all()
    return [
        PostBrief(
            post_id=str(int(r.PST_SN)),
            title=str(r.PST_TTL),
            published_at=utc(r.PUB_DT),
            pinned=r.NTC_YN == "Y",
        )
        for r in rows
    ]
