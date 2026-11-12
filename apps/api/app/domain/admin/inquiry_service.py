# 관리자 문의·답변(AU.POST_W). 답변은 원글당 한 단계이고 고칠 수 있으며 고칠 때마다 이력을 남긴다(FN-053, DV132, ADR-057)
import re
from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, func, select, update
from sqlalchemy.orm import Session, aliased

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_BBS, TB_COM_CD, TB_JOB_HSTRY, TB_MBR, TB_MNGR, TB_PST
from app.domain.admin.content_types import AnswerAction
from app.domain.admin.csv_export import audit_export, build_csv, fetch_all
from app.domain.admin.inquiry_schemas import (
    AdminInquiry,
    AdminInquiryCategory,
    AdminInquiryCategoryList,
    AdminInquiryPage,
    AdminInquirySummary,
    AnswerHistoryEntry,
    InquiryAnswer,
    InquiryAnswerWrite,
)
from app.domain.admin.refund_service import mask_name
from app.domain.admin.types import AdminAuthority as AU
from app.domain.board.types import InquiryStatus

BOARD = "qna"  # 문의는 질문과 답변 게시판의 글이다
ANSWER_JOBS = {"INQ_ANSWER": AnswerAction.CREATED, "INQ_ANSWER_EDIT": AnswerAction.EDITED}
LINK_LABEL = (
    "\n\n관련 화면: "  # 답변에 관련 화면 링크를 담을 컬럼이 없어 본문 끝에 이 표식과 함께 둔다(개정 요청 R34)
)
LINK_TAIL = re.compile(r"\n\n관련 화면: (\S+)$")
REPLY = aliased(TB_PST, name="reply")
ANSWERER = aliased(TB_MNGR, name="answerer")


def _valid_link(link: str) -> bool:
    """사이트 안 경로(/로 시작하되 //가 아닌 것)이거나 https 주소만 받는다."""
    return (link.startswith("/") and not link.startswith("//")) or link.startswith("https://")


def _split_answer(stored: str) -> tuple[str, str | None]:
    found = LINK_TAIL.search(stored)
    if found is None or not _valid_link(found.group(1)):
        return stored, None
    return stored[: found.start()], found.group(1)


def _base(bundle_sn: int) -> Select[Any]:
    source = (
        TB_PST.join(
            TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN)
        )
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_PST.c.WRT_MBR_SN)
        .outerjoin(TB_COM_CD, TB_COM_CD.c.COM_CD == TB_PST.c.INQRY_CLSF_CD)
        .outerjoin(
            REPLY,
            (REPLY.c.UP_PST_SN == TB_PST.c.PST_SN)
            & (REPLY.c.DEL_YN == "N")
            & (REPLY.c.PST_TYPE_CD == "PT.REPLY"),
        )
        .outerjoin(ANSWERER, ANSWERER.c.MNGR_SN == REPLY.c.WRT_MNGR_SN)
    )
    return (
        select(
            TB_PST,
            TB_MBR.c.MBR_NM,
            TB_COM_CD.c.CD_NM,
            REPLY.c.PST_SN.label("RPL_SN"),
            REPLY.c.PST_CN.label("RPL_CN"),
            REPLY.c.RCRD_VER.label("RPL_VER"),
            func.coalesce(REPLY.c.MDFCN_DT, REPLY.c.REG_DT).label("RPL_DT"),
            ANSWERER.c.MNGR_NM.label("RPL_BY"),
        )
        .select_from(source)
        .where(
            TB_PST.c.OPER_BNDL_SN == bundle_sn,
            TB_BBS.c.BBS_ID == BOARD,
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),
        )
    )


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    """문의의 범위는 글의 동이다. 동이 없는 글은 묶음 전체 범위만 본다."""
    return query if scope.whole else query.where(TB_PST.c.DONG_SN.in_(scope.dongs))


def _summary(row: Any) -> AdminInquirySummary:
    return AdminInquirySummary(
        inquiry_id=str(int(row.PST_SN)),
        title=str(row.PST_TTL),
        category_name=str(row.CD_NM or ""),
        author_name=mask_name(str(row.MBR_NM)) if row.MBR_NM is not None else "",
        is_private=row.PRVT_YN == "Y",
        status=InquiryStatus.ANSWERED if row.RPL_SN is not None else InquiryStatus.RECEIVED,
        received_on=kst_today(row.REG_DT),
    )


def list_categories(db: Session, admin: Admin, *, now: datetime) -> AdminInquiryCategoryList:
    """분류는 공통코드(IQ)에서 읽는다. 초기값은 기관 확인 뒤 입력하며 임의로 만들지 않는다(PRD Q26)."""
    permit(db, admin, AU.POST_W, now)
    rows = db.execute(
        select(TB_COM_CD.c.COM_CD, TB_COM_CD.c.CD_NM)
        .where(TB_COM_CD.c.COM_CD.like("IQ.%"), TB_COM_CD.c.USE_YN == "Y")
        .order_by(TB_COM_CD.c.SORT_SEQ, TB_COM_CD.c.COM_CD)
    ).all()
    return AdminInquiryCategoryList(
        items=[AdminInquiryCategory(id=str(r.COM_CD), name=str(r.CD_NM)) for r in rows]
    )


def _filtered(
    db: Session,
    admin: Admin,
    now: datetime,
    *,
    status: InquiryStatus | None,
    category_id: str | None,
    q: str | None,
) -> Select[Any]:
    """목록과 내보내기가 함께 쓰는 조회. 답변 대기 건이 먼저이고 각각 오래된 순이다."""
    scope = permit(db, admin, AU.POST_W, now)
    query = _in_scope(_base(admin.bundle_sn), scope)
    if status is InquiryStatus.RECEIVED:
        query = query.where(REPLY.c.PST_SN.is_(None))
    elif status is InquiryStatus.ANSWERED:
        query = query.where(REPLY.c.PST_SN.is_not(None))
    if category_id:
        query = query.where(TB_PST.c.INQRY_CLSF_CD == category_id)
    if q and q.strip():
        query = query.where(TB_PST.c.PST_TTL.contains(q.strip(), autoescape=True))
    return query.order_by(
        case((REPLY.c.PST_SN.is_(None), 0), else_=1), TB_PST.c.REG_DT.asc(), TB_PST.c.PST_SN.asc()
    )


def list_inquiries(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    status: InquiryStatus | None,
    category_id: str | None,
    q: str | None,
    page: int,
    size: int,
) -> AdminInquiryPage:
    query = _filtered(db, admin, now, status=status, category_id=category_id, q=q)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AdminInquiryPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def export_csv(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    status: InquiryStatus | None,
    category_id: str | None,
    q: str | None,
) -> bytes:
    """문의 본문·답변·첨부는 담지 않고 작성자는 가린 값이다. 만들 때마다 작업이력에 남긴다."""
    rows = fetch_all(db, _filtered(db, admin, now, status=status, category_id=category_id, q=q))
    audit_export(
        db, admin, "TB_PST", len(rows), request_id, now, {"status": status, "categoryId": category_id, "q": q}
    )
    return build_csv(
        ["문의번호", "분류", "제목", "작성자", "공개 여부", "상태", "접수일"],
        [
            [
                s.inquiry_id,
                s.category_name,
                s.title,
                s.author_name,
                "비공개" if s.is_private else "공개",
                s.status.value,
                s.received_on,
            ]
            for s in map(_summary, rows)
        ],
    )


def _load(db: Session, admin: Admin, now: datetime, inquiry_id: str) -> Any:
    """권한이 없으면 403, 없거나 범위 밖이거나 지운 문의는 같은 404다."""
    scope = permit(db, admin, AU.POST_W, now)
    row = db.execute(
        _in_scope(_base(admin.bundle_sn), scope).where(TB_PST.c.PST_SN == int(inquiry_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _history(db: Session, admin: Admin, post_sn: int) -> list[AnswerHistoryEntry]:
    rows = db.execute(
        select(TB_JOB_HSTRY.c.JOB_CD, TB_JOB_HSTRY.c.REG_DT, TB_MNGR.c.MNGR_NM)
        .select_from(TB_JOB_HSTRY.outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN))
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD.in_(list(ANSWER_JOBS)),
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(post_sn),
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN)
    ).all()
    return [
        AnswerHistoryEntry(at=utc(r.REG_DT), by=str(r.MNGR_NM or ""), action=ANSWER_JOBS[str(r.JOB_CD)])
        for r in rows
    ]


def _detail(db: Session, admin: Admin, row: Any) -> AdminInquiry:
    answer = None
    if row.RPL_SN is not None:
        content, link = _split_answer(str(row.RPL_CN))
        answer = InquiryAnswer(
            content=content,
            related_link=link,
            answered_by=str(row.RPL_BY or ""),
            answered_at=utc(row.RPL_DT),
            version=int(row.RPL_VER),
        )
    return AdminInquiry(
        **_summary(row).model_dump(),
        content=str(row.PST_CN),
        answer=answer,
        history=_history(db, admin, int(row.PST_SN)),
        can_answer=True,  # 이 담당자의 범위 안에서 조회된 문의라 답변 권한이 있다
    )


def get_inquiry(db: Session, admin: Admin, *, now: datetime, inquiry_id: str) -> AdminInquiry:
    return _detail(db, admin, _load(db, admin, now, inquiry_id))


def answer_inquiry(
    db: Session, admin: Admin, *, now: datetime, request_id: str, inquiry_id: str, body: InquiryAnswerWrite
) -> AdminInquiry:
    """답변을 작성하거나 고친다. 읽은 답변 버전(없으면 0)이 다르면 409다. 고칠 때마다 이력을 남긴다."""
    row = _load(db, admin, now, inquiry_id)
    content = body.content.strip()
    link = body.related_link.strip() if body.related_link else None
    if not content:
        message = "답변 내용을 입력해 주세요."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"content": message})
    if link is not None and not _valid_link(link):
        message = "관련 화면 링크는 사이트 안 경로(/로 시작)이거나 https 주소여야 합니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"relatedLink": message})
    # 같은 문의의 답변 요청을 한 줄로 세워 버전 확인과 저장 사이의 틈을 막는다
    db.execute(select(TB_PST.c.PST_SN).where(TB_PST.c.PST_SN == row.PST_SN).with_for_update()).one()
    current = db.execute(
        select(TB_PST.c.PST_SN, TB_PST.c.RCRD_VER).where(
            TB_PST.c.UP_PST_SN == row.PST_SN, TB_PST.c.PST_TYPE_CD == "PT.REPLY", TB_PST.c.DEL_YN == "N"
        )
    ).first()
    if body.version != (0 if current is None else int(current.RCRD_VER)):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    stored = content + (LINK_LABEL + link if link else "")
    if current is None:
        db.execute(
            TB_PST.insert().values(
                OPER_BNDL_SN=admin.bundle_sn,
                DONG_SN=row.DONG_SN,
                BBS_SN=row.BBS_SN,
                UP_PST_SN=row.PST_SN,
                PST_TYPE_CD="PT.REPLY",
                PST_TTL=f"답변: {row.PST_TTL}"[:256],
                PST_CN=stored,
                WRT_MNGR_SN=admin.admin_sn,
                PRVT_YN=row.PRVT_YN,  # 답변은 원글의 분류와 공개범위를 따른다(PST-02)
                NTC_YN="N",
                DEL_YN="N",
                INQRY_CLSF_CD=row.INQRY_CLSF_CD,
                REG_DT=now,
                RCRD_VER=1,
            )
        )
        job = "INQ_ANSWER"
    else:
        db.execute(
            update(TB_PST)
            .where(TB_PST.c.PST_SN == current.PST_SN)
            .values(PST_CN=stored, WRT_MNGR_SN=admin.admin_sn, MDFCN_DT=now, RCRD_VER=TB_PST.c.RCRD_VER + 1)
        )
        job = "INQ_ANSWER_EDIT"
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_PST",
        key=int(row.PST_SN),
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change="답변 작성" if current is None else "답변 수정",
    )
    return _detail(db, admin, _load(db, admin, now, inquiry_id))
