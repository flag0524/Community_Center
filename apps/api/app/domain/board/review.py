# 수강후기 조회와 주민 쪽 작성·수정·삭제. 수강확정 이후의 강좌만 한 강좌에 한 번 쓰고 본인 글만 고치며 타인의 글은 404다(FN-020, PRD Q19, ADR-067)
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import TB_ATNLC_APLY, TB_BBS, TB_CORS, TB_JOB_HSTRY, TB_MBR, TB_PST
from app.domain.admin.refund_service import mask_name
from app.domain.board.schemas import (
    ReviewableCourse,
    ReviewableCourseList,
    ReviewDetail,
    ReviewPage,
    ReviewSummary,
    ReviewWrite,
)

BOARD = "review"
ELIGIBLE = ("ES.CONFIRM", "ES.COMPLETE")  # 수강확정과 수강종료(PRD Q19 가정)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _base(bundle_sn: int) -> Select[Any]:
    """게시판이 쓰이고 지우지도 비공개도 아닌 후기 원글."""
    return (
        select(TB_PST, TB_MBR.c.MBR_NM, TB_CORS.c.CORS_NM)
        .select_from(TB_PST)
        .join(TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN))
        .join(
            TB_CORS,
            (TB_CORS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_CORS.c.CORS_SN == TB_PST.c.CORS_SN),
        )
        .outerjoin(
            TB_MBR,
            (TB_MBR.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_MBR.c.MBR_SN == TB_PST.c.WRT_MBR_SN),
        )
        .where(
            TB_PST.c.OPER_BNDL_SN == bundle_sn,
            TB_BBS.c.BBS_ID == BOARD,
            TB_BBS.c.USE_YN == "Y",
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.PRVT_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),
        )
    )


def _is_mine(row: Any, member_sn: int | None) -> bool:
    return member_sn is not None and row.WRT_MBR_SN is not None and int(row.WRT_MBR_SN) == member_sn


def _summary(row: Any, member_sn: int | None) -> ReviewSummary:
    return ReviewSummary(
        post_id=str(int(row.PST_SN)),
        title=str(row.PST_TTL),
        author_name=mask_name(str(row.MBR_NM or "")),
        course_name=str(row.CORS_NM),
        is_mine=_is_mine(row, member_sn),
        published_at=utc(row.REG_DT),
    )


def _detail(row: Any, member_sn: int | None) -> ReviewDetail:
    mine = _is_mine(row, member_sn)
    return ReviewDetail(
        post_id=str(int(row.PST_SN)),
        course_id=str(int(row.CORS_SN)),
        course_name=str(row.CORS_NM),
        title=str(row.PST_TTL),
        body=str(row.PST_CN),
        author_name=mask_name(str(row.MBR_NM or "")),
        published_at=utc(row.REG_DT),
        can_edit=mine,
        can_delete=mine,
    )


def _page(
    db: Session, query: Select[Any], member_sn: int | None, now: datetime, page: int, size: int
) -> ReviewPage:
    query = query.order_by(TB_PST.c.REG_DT.desc(), TB_PST.c.PST_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return ReviewPage(
        items=[_summary(r, member_sn) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def list_reviews(
    db: Session,
    bundle_sn: int,
    member_sn: int | None,
    now: datetime,
    *,
    q: str | None,
    page: int,
    size: int,
) -> ReviewPage:
    query = _base(bundle_sn)
    if q and q.strip():
        query = query.where(TB_PST.c.PST_TTL.contains(q.strip(), autoescape=True))
    return _page(db, query, member_sn, now, page, size)


def list_mine(
    db: Session, bundle_sn: int, member_sn: int, now: datetime, *, page: int, size: int
) -> ReviewPage:
    return _page(db, _base(bundle_sn).where(TB_PST.c.WRT_MBR_SN == member_sn), member_sn, now, page, size)


def _row(db: Session, bundle_sn: int, post_id: str) -> Any:
    row = db.execute(_base(bundle_sn).where(TB_PST.c.PST_SN == int(post_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_review(db: Session, bundle_sn: int, member_sn: int | None, post_id: str) -> ReviewDetail:
    return _detail(_row(db, bundle_sn, post_id), member_sn)


def _mine(db: Session, bundle_sn: int, member_sn: int, post_id: str) -> Any:
    """본인 글만이다. 남의 글은 공개 글이어도 없는 것과 같게 404다."""
    row = _row(db, bundle_sn, post_id)
    if not _is_mine(row, member_sn):
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _eligible(bundle_sn: int, member_sn: int) -> Select[Any]:
    """수강확정 이후인 내 신청의 강좌. 이미 쓴 후기가 있는 강좌는 뺀다."""
    reviewed = (
        select(TB_PST.c.PST_SN)
        .join(TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN))
        .where(
            TB_PST.c.OPER_BNDL_SN == bundle_sn,
            TB_BBS.c.BBS_ID == BOARD,
            TB_PST.c.CORS_SN == TB_CORS.c.CORS_SN,
            TB_PST.c.WRT_MBR_SN == member_sn,
            TB_PST.c.DEL_YN == "N",
        )
        .exists()
    )
    return (
        select(TB_CORS.c.CORS_SN, TB_CORS.c.CORS_NM, TB_CORS.c.DONG_SN)
        .select_from(TB_CORS)
        .where(
            TB_CORS.c.OPER_BNDL_SN == bundle_sn,
            select(TB_ATNLC_APLY.c.ATNLC_APLY_SN)
            .where(
                TB_ATNLC_APLY.c.OPER_BNDL_SN == TB_CORS.c.OPER_BNDL_SN,
                TB_ATNLC_APLY.c.CORS_SN == TB_CORS.c.CORS_SN,
                TB_ATNLC_APLY.c.MBR_SN == member_sn,
                TB_ATNLC_APLY.c.APLY_STTS_CD.in_(ELIGIBLE),
            )
            .exists(),
            ~reviewed,
        )
    )


def list_reviewable(db: Session, bundle_sn: int, member_sn: int) -> ReviewableCourseList:
    rows = db.execute(_eligible(bundle_sn, member_sn).order_by(TB_CORS.c.CORS_NM, TB_CORS.c.CORS_SN)).all()
    return ReviewableCourseList(
        items=[ReviewableCourse(course_id=str(int(r.CORS_SN)), name=str(r.CORS_NM)) for r in rows]
    )


def _texts(body: ReviewWrite) -> tuple[str, str]:
    title, text = body.title.strip(), body.body.strip()
    if not title:
        raise _fail("title", "제목을 입력해 주세요.")
    if not text:
        raise _fail("body", "내용을 입력해 주세요.")
    return title, text


def _mark(idem_key: str, body: ReviewWrite) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def create_review(
    db: Session,
    *,
    member_sn: int,
    bundle_sn: int,
    body: ReviewWrite,
    idem_key: str,
    request_id: str,
    now: datetime,
) -> ReviewDetail:
    """회원 행을 잠근 뒤 같은 키의 이전 글을 먼저 찾고, 없으면 게시판·자격·중복을 검사해 쓴다(FN-052)."""
    db.execute(select(TB_MBR.c.MBR_SN).where(TB_MBR.c.MBR_SN == member_sn).with_for_update()).one()
    mark = _mark(idem_key, body)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.MBR_SN == member_sn,
            TB_JOB_HSTRY.c.JOB_CD == "RVW_CREATE",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _detail(_row(db, bundle_sn, str(prior.TRGT_KEY_VL)), member_sn)
    board = db.execute(
        select(TB_BBS.c.BBS_SN, TB_BBS.c.USE_YN, TB_BBS.c.MBR_WRT_YN).where(
            TB_BBS.c.OPER_BNDL_SN == bundle_sn, TB_BBS.c.BBS_ID == BOARD
        )
    ).first()
    if board is None or board.USE_YN != "Y" or board.MBR_WRT_YN != "Y":
        raise ApiError(ErrorCode.RULE_REJECTED, "지금은 수강후기를 받지 않습니다.")
    title, text = _texts(body)
    course = db.execute(
        _eligible(bundle_sn, member_sn).where(TB_CORS.c.CORS_SN == int(body.course_id))
    ).first()
    if course is None:
        raise _fail("courseId", "수강확정한 강좌의 후기만 쓸 수 있고 강좌마다 한 번만 쓸 수 있습니다.")
    sn = int(
        db.execute(
            TB_PST.insert()
            .values(
                OPER_BNDL_SN=bundle_sn,
                DONG_SN=course.DONG_SN,  # 강좌의 동이 글의 동이라 그 동의 담당자가 후기를 본다
                BBS_SN=board.BBS_SN,
                PST_TYPE_CD="PT.POST",
                PST_TTL=title,
                PST_CN=text,
                WRT_MBR_SN=member_sn,
                PRVT_YN="N",
                NTC_YN="N",
                DEL_YN="N",
                CORS_SN=int(body.course_id),
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_PST.c.PST_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="RVW_CREATE",
        table="TB_PST",
        key=sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"후기 등록 {mark}",
    )
    return _detail(_row(db, bundle_sn, str(sn)), member_sn)


def _lock(db: Session, post_sn: int) -> Any:
    return db.execute(select(TB_PST.c.DEL_YN).where(TB_PST.c.PST_SN == post_sn).with_for_update()).one()


def update_review(
    db: Session,
    *,
    member_sn: int,
    bundle_sn: int,
    post_id: str,
    body: ReviewWrite,
    request_id: str,
    now: datetime,
) -> ReviewDetail:
    """본인 후기의 제목·내용만 고친다. 강좌는 바꿀 수 없다."""
    row = _mine(db, bundle_sn, member_sn, post_id)
    if _lock(db, int(row.PST_SN)).DEL_YN != "N":
        raise ApiError(ErrorCode.NOT_FOUND)
    if int(body.course_id) != int(row.CORS_SN):
        raise _fail("courseId", "후기를 쓴 강좌는 바꿀 수 없습니다.")
    title, text = _texts(body)
    db.execute(
        update(TB_PST)
        .where(TB_PST.c.PST_SN == row.PST_SN)
        .values(PST_TTL=title, PST_CN=text, MDFCN_DT=now, RCRD_VER=TB_PST.c.RCRD_VER + 1)
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="RVW_UPDATE",
        table="TB_PST",
        key=int(row.PST_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="후기 수정",
    )
    return _detail(_row(db, bundle_sn, post_id), member_sn)


def delete_review(
    db: Session, *, member_sn: int, bundle_sn: int, post_id: str, request_id: str, now: datetime
) -> None:
    """본인 후기만 지운다. 삭제는 논리 삭제이고 지우면 같은 강좌에 다시 쓸 수 있다."""
    row = _mine(db, bundle_sn, member_sn, post_id)
    if _lock(db, int(row.PST_SN)).DEL_YN != "N":
        raise ApiError(ErrorCode.NOT_FOUND)
    db.execute(
        update(TB_PST)
        .where(TB_PST.c.PST_SN == row.PST_SN)
        .values(DEL_YN="Y", MDFCN_DT=now, RCRD_VER=TB_PST.c.RCRD_VER + 1)
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="RVW_DELETE",
        table="TB_PST",
        key=int(row.PST_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="후기 삭제",
    )
