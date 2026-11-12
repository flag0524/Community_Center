# 주민 쪽 문의(질문과 답변) 조회·작성·수정·삭제. 작성·수정·삭제는 본인 글만이고 타인의 글은 404다(FN-053, DV86·87, ADR-058)
import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import utc
from app.db.tables import TB_BBS, TB_COM_CD, TB_JOB_HSTRY, TB_MBR, TB_PST
from app.domain.admin.inquiry_service import _base
from app.domain.admin.refund_service import mask_name
from app.domain.board.schemas import (
    InquiryAnswer,
    InquiryCategory,
    InquiryCategoryList,
    InquiryDetail,
    InquiryPage,
    InquirySummary,
    InquiryWrite,
)
from app.domain.board.types import InquiryStatus

PRIVATE_TITLE = "비공개 문의입니다."


def _author(row: Any, mine: bool) -> str:
    name = str(row.MBR_NM or "")
    if row.PRVT_YN == "Y" and not mine:
        return name[:1] + "*" * max(len(name) - 1, 0)  # 다른 회원의 비공개 문의는 앞 글자만 남긴다
    return mask_name(name)


def _summary(row: Any, member_sn: int) -> InquirySummary:
    mine = row.WRT_MBR_SN is not None and int(row.WRT_MBR_SN) == member_sn
    hidden = row.PRVT_YN == "Y" and not mine
    return InquirySummary(
        post_id=str(int(row.PST_SN)),
        category_name=str(row.CD_NM or ""),
        title=PRIVATE_TITLE if hidden else str(row.PST_TTL),
        author_name=_author(row, mine),
        status=InquiryStatus.ANSWERED if row.RPL_SN is not None else InquiryStatus.RECEIVED,
        is_private=row.PRVT_YN == "Y",
        is_mine=mine,
        published_at=utc(row.REG_DT),
    )


def _detail(row: Any, member_sn: int) -> InquiryDetail:
    mine = row.WRT_MBR_SN is not None and int(row.WRT_MBR_SN) == member_sn
    answered = row.RPL_SN is not None
    return InquiryDetail(
        post_id=str(int(row.PST_SN)),
        category_id=str(row.INQRY_CLSF_CD or ""),
        category_name=str(row.CD_NM or ""),
        title=str(row.PST_TTL),
        body=str(row.PST_CN),
        author_name=_author(row, mine),
        status=InquiryStatus.ANSWERED if answered else InquiryStatus.RECEIVED,
        is_private=row.PRVT_YN == "Y",
        published_at=utc(row.REG_DT),
        # 관련 화면 링크는 답변 글 끝의 표식과 함께 그대로 보여 준다(개정 요청 R34)
        answer=InquiryAnswer(body=str(row.RPL_CN), answered_at=utc(row.RPL_DT)) if answered else None,
        can_edit=mine and not answered,
        can_delete=mine,
    )


def list_categories(db: Session) -> InquiryCategoryList:
    """분류는 공통코드(IQ)에서 읽는다. 초기값은 기관 확인 뒤 입력하며 임의로 만들지 않는다(PRD Q26)."""
    rows = db.execute(
        select(TB_COM_CD.c.COM_CD, TB_COM_CD.c.CD_NM)
        .where(TB_COM_CD.c.COM_CD.like("IQ.%"), TB_COM_CD.c.USE_YN == "Y")
        .order_by(TB_COM_CD.c.SORT_SEQ, TB_COM_CD.c.COM_CD)
    ).all()
    return InquiryCategoryList(
        items=[InquiryCategory(category_id=str(r.COM_CD), name=str(r.CD_NM)) for r in rows]
    )


def _page(
    db: Session, query: Select[Any], member_sn: int, now: datetime, page: int, size: int
) -> InquiryPage:
    query = query.order_by(TB_PST.c.REG_DT.desc(), TB_PST.c.PST_SN.desc())
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return InquiryPage(
        items=[_summary(r, member_sn) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def list_all(
    db: Session, *, member_sn: int, bundle_sn: int, now: datetime, page: int, size: int
) -> InquiryPage:
    """모든 문의의 분류·상태·등록일을 준다. 다른 회원의 비공개 문의는 제목과 작성자를 가린다."""
    return _page(db, _base(bundle_sn), member_sn, now, page, size)


def list_mine(
    db: Session, *, member_sn: int, bundle_sn: int, now: datetime, page: int, size: int
) -> InquiryPage:
    return _page(db, _base(bundle_sn).where(TB_PST.c.WRT_MBR_SN == member_sn), member_sn, now, page, size)


def _row(db: Session, bundle_sn: int, post_id: str) -> Any:
    row = db.execute(_base(bundle_sn).where(TB_PST.c.PST_SN == int(post_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_inquiry(db: Session, *, member_sn: int, bundle_sn: int, post_id: str) -> InquiryDetail:
    """다른 회원의 비공개 문의는 없는 것과 같게 404다. 답변도 원글의 비공개 범위를 따른다."""
    row = _row(db, bundle_sn, post_id)
    mine = row.WRT_MBR_SN is not None and int(row.WRT_MBR_SN) == member_sn
    if row.PRVT_YN == "Y" and not mine:
        raise ApiError(ErrorCode.NOT_FOUND)
    return _detail(row, member_sn)


def _mine(db: Session, bundle_sn: int, member_sn: int, post_id: str) -> Any:
    """본인 글만이다. 남의 글은 공개 글이어도 없는 것과 같게 404다."""
    row = _row(db, bundle_sn, post_id)
    if row.WRT_MBR_SN is None or int(row.WRT_MBR_SN) != member_sn:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _category(db: Session, category_id: str) -> None:
    found = db.execute(
        select(TB_COM_CD.c.COM_CD).where(
            TB_COM_CD.c.COM_CD == category_id, TB_COM_CD.c.COM_CD.like("IQ.%"), TB_COM_CD.c.USE_YN == "Y"
        )
    ).first()
    if found is None:
        message = "문의 분류를 확인해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"categoryId": message})


def _texts(body: InquiryWrite) -> tuple[str, str]:
    title, text = body.title.strip(), body.body.strip()
    if not title:
        raise ApiError(
            ErrorCode.RULE_REJECTED, "제목을 입력해 주세요.", fields={"title": "제목을 입력해 주세요."}
        )
    if not text:
        raise ApiError(
            ErrorCode.RULE_REJECTED, "내용을 입력해 주세요.", fields={"body": "내용을 입력해 주세요."}
        )
    return title, text


def _mark(idem_key: str, body: InquiryWrite) -> str:
    key = hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]
    return f"[idem {key}:{digest}]"


def create_inquiry(
    db: Session,
    *,
    member_sn: int,
    bundle_sn: int,
    body: InquiryWrite,
    idem_key: str,
    request_id: str,
    now: datetime,
) -> InquiryDetail:
    # 같은 회원의 올리기를 한 줄로 세워 멱등 확인과 저장 사이의 틈을 막는다
    member = db.execute(select(TB_MBR.c.DONG_SN).where(TB_MBR.c.MBR_SN == member_sn).with_for_update()).one()
    mark = _mark(idem_key, body)
    prefix = mark.split(":")[0] + ":"
    prior = db.execute(
        select(TB_JOB_HSTRY.c.TRGT_KEY_VL, TB_JOB_HSTRY.c.CHG_CN).where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == bundle_sn,
            TB_JOB_HSTRY.c.MBR_SN == member_sn,
            TB_JOB_HSTRY.c.JOB_CD == "INQ_CREATE",
            TB_JOB_HSTRY.c.CHG_CN.contains(prefix, autoescape=True),
        )
    ).first()
    if prior is not None:
        if mark not in str(prior.CHG_CN):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _detail(_row(db, bundle_sn, str(prior.TRGT_KEY_VL)), member_sn)
    board = db.execute(
        select(TB_BBS.c.BBS_SN, TB_BBS.c.USE_YN, TB_BBS.c.MBR_WRT_YN).where(
            TB_BBS.c.OPER_BNDL_SN == bundle_sn, TB_BBS.c.BBS_ID == "qna"
        )
    ).first()
    if board is None or board.USE_YN != "Y" or board.MBR_WRT_YN != "Y":
        raise ApiError(ErrorCode.RULE_REJECTED, "지금은 문의를 받지 않습니다.")
    _category(db, body.category_id)
    title, text = _texts(body)
    sn = int(
        db.execute(
            TB_PST.insert()
            .values(
                OPER_BNDL_SN=bundle_sn,
                DONG_SN=member.DONG_SN,  # 작성 회원의 동이 글의 동이라 그 동의 담당자가 문의를 본다
                BBS_SN=board.BBS_SN,
                PST_TYPE_CD="PT.POST",
                PST_TTL=title,
                PST_CN=text,
                WRT_MBR_SN=member_sn,
                PRVT_YN="Y" if body.is_private else "N",
                NTC_YN="N",
                DEL_YN="N",
                INQRY_CLSF_CD=body.category_id,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_PST.c.PST_SN)
        ).scalar_one()
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="INQ_CREATE",
        table="TB_PST",
        key=sn,
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change=f"문의 등록 {mark}",
    )
    return _detail(_row(db, bundle_sn, str(sn)), member_sn)


def _lock(db: Session, post_sn: int) -> Any:
    """원글을 잠가 관리자 답변·본인 수정·삭제를 한 줄로 세운다(답변도 같은 잠금을 쓴다)."""
    return db.execute(select(TB_PST.c.DEL_YN).where(TB_PST.c.PST_SN == post_sn).with_for_update()).one()


def update_inquiry(
    db: Session,
    *,
    member_sn: int,
    bundle_sn: int,
    post_id: str,
    body: InquiryWrite,
    request_id: str,
    now: datetime,
) -> InquiryDetail:
    """답변이 달린 문의는 고칠 수 없다(RULE_REJECTED)."""
    row = _mine(db, bundle_sn, member_sn, post_id)
    if _lock(db, int(row.PST_SN)).DEL_YN != "N":
        raise ApiError(ErrorCode.NOT_FOUND)
    current = _row(db, bundle_sn, post_id)  # 잠근 뒤 답변 여부를 다시 읽는다
    if current.RPL_SN is not None:
        raise ApiError(ErrorCode.RULE_REJECTED, "답변이 달린 문의는 고칠 수 없습니다.")
    _category(db, body.category_id)
    title, text = _texts(body)
    db.execute(
        update(TB_PST)
        .where(TB_PST.c.PST_SN == row.PST_SN)
        .values(
            PST_TTL=title,
            PST_CN=text,
            PRVT_YN="Y" if body.is_private else "N",
            INQRY_CLSF_CD=body.category_id,
            MDFCN_DT=now,
            RCRD_VER=TB_PST.c.RCRD_VER + 1,
        )
    )
    record_job(
        db,
        actor="AK.MEMBER",
        job="INQ_UPDATE",
        table="TB_PST",
        key=int(row.PST_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="문의 수정",
    )
    return _detail(_row(db, bundle_sn, post_id), member_sn)


def delete_inquiry(
    db: Session, *, member_sn: int, bundle_sn: int, post_id: str, request_id: str, now: datetime
) -> None:
    """본인 문의만 지운다. 답변이 달렸어도 지울 수 있고 삭제는 논리 삭제다."""
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
        job="INQ_DELETE",
        table="TB_PST",
        key=int(row.PST_SN),
        request_id=request_id,
        now=now,
        bundle_sn=bundle_sn,
        member_sn=member_sn,
        change="문의 삭제",
    )
