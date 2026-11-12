# 관리자 게시판 설정(AU.BBS_W)과 게시물 관리(AU.POST_W). 삭제는 논리삭제이고 회원이 쓴 글은 내용을 고치지 못한다(DV129·130, ADR-055)
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit, permit_any
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_BBS, TB_MBR, TB_MNGR, TB_PST
from app.domain.admin.board_schemas import (
    AdminPost,
    AdminPostPage,
    AdminPostSummary,
    AdminPostUpdate,
    AdminPostWrite,
    BoardSetting,
    BoardSettingList,
    BoardSettingUpdate,
)
from app.domain.admin.csv_export import audit_export, build_csv, fetch_all
from app.domain.admin.education_service import _idem_mark, _replayed
from app.domain.admin.refund_service import mask_name
from app.domain.admin.types import AdminAuthority as AU
from app.domain.board.sanitize import clean_body, has_text
from app.domain.board.types import BoardKey

PRIVATE_BOARDS = (
    "BT.QNA",
)  # 비공개 글을 쓸 수 있는 게시판 유형. 게시판 정책 컬럼이 없어 유형으로 정한다(개정 요청 R11)


def _yn(value: bool) -> str:
    return "Y" if value else "N"


def _naive(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(UTC).replace(tzinfo=None)


def _audit(
    db: Session, admin: Admin, job: str, table: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table=table,
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


# --- 게시판 설정 -------------------------------------------------------------------------------


def _setting(row: Any, posts: int) -> BoardSetting:
    return BoardSetting(
        board_key=BoardKey(str(row.BBS_ID)),
        name=str(row.BBS_NM),
        member_write=row.MBR_WRT_YN == "Y",
        answer_enabled=row.ANS_USE_YN == "Y",
        attach_enabled=row.ATCH_USE_YN == "Y",
        allow_private=str(row.BBS_TYPE_CD) in PRIVATE_BOARDS,  # 저장할 컬럼이 없어 유형에서 정한다(R11)
        in_use=row.USE_YN == "Y",
        post_count=posts,
        version=int(row.RCRD_VER),
    )


def _post_counts(db: Session, bundle_sn: int) -> dict[int, int]:
    rows = db.execute(
        select(TB_PST.c.BBS_SN, func.count())
        .where(TB_PST.c.OPER_BNDL_SN == bundle_sn, TB_PST.c.DEL_YN == "N", TB_PST.c.UP_PST_SN.is_(None))
        .group_by(TB_PST.c.BBS_SN)
    ).all()
    return {int(r[0]): int(r[1]) for r in rows}


def list_boards(db: Session, admin: Admin, *, now: datetime) -> BoardSettingList:
    """게시물 권한만 있어도 글쓰기 선택지로 볼 수 있다."""
    permit_any(db, admin, (AU.BBS_W, AU.POST_W), now)
    counts = _post_counts(db, admin.bundle_sn)
    rows = db.execute(
        select(TB_BBS)
        .where(TB_BBS.c.OPER_BNDL_SN == admin.bundle_sn)
        .order_by(TB_BBS.c.SORT_SEQ, TB_BBS.c.BBS_SN)
    ).all()
    return BoardSettingList(items=[_setting(r, counts.get(int(r.BBS_SN), 0)) for r in rows])


def update_board(
    db: Session,
    admin: Admin,
    *,
    now: datetime,
    request_id: str,
    board_key: BoardKey,
    body: BoardSettingUpdate,
) -> BoardSetting:
    """게시판 정의는 묶음 전체의 일이라 묶음 전체 범위의 권한이 있어야 한다. 이름과 키는 바꾸지 않는다."""
    if not permit(db, admin, AU.BBS_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)
    row = db.execute(
        select(TB_BBS)
        .where(TB_BBS.c.OPER_BNDL_SN == admin.bundle_sn, TB_BBS.c.BBS_ID == board_key.value)
        .with_for_update()
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    if body.version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    if body.allow_private != (str(row.BBS_TYPE_CD) in PRIVATE_BOARDS):
        message = "비공개 허용은 아직 저장할 수 없습니다(스키마 개정 요청 R11)."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"allowPrivate": message})
    db.execute(
        update(TB_BBS)
        .where(TB_BBS.c.BBS_SN == row.BBS_SN)
        .values(
            MBR_WRT_YN=_yn(body.member_write),
            ANS_USE_YN=_yn(body.answer_enabled),
            ATCH_USE_YN=_yn(body.attach_enabled),
            USE_YN=_yn(body.in_use),
            MDFCN_DT=now,
            RCRD_VER=TB_BBS.c.RCRD_VER + 1,
        )
    )
    change = (
        f"{board_key.value} 회원작성 {_yn(body.member_write)} 답변 {_yn(body.answer_enabled)} "
        f"첨부 {_yn(body.attach_enabled)} 사용 {_yn(body.in_use)}"
    )
    _audit(db, admin, "BBS_UPDATE", "TB_BBS", int(row.BBS_SN), request_id, now, change)
    fresh = db.execute(select(TB_BBS).where(TB_BBS.c.BBS_SN == row.BBS_SN)).one()
    return _setting(fresh, _post_counts(db, admin.bundle_sn).get(int(row.BBS_SN), 0))


# --- 게시물 ------------------------------------------------------------------------------------


def _base(bundle_sn: int) -> Select[Any]:
    source = (
        TB_PST.join(
            TB_BBS, (TB_BBS.c.OPER_BNDL_SN == TB_PST.c.OPER_BNDL_SN) & (TB_BBS.c.BBS_SN == TB_PST.c.BBS_SN)
        )
        .outerjoin(TB_MBR, TB_MBR.c.MBR_SN == TB_PST.c.WRT_MBR_SN)
        .outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_PST.c.WRT_MNGR_SN)
    )
    return (
        select(
            TB_PST,
            TB_BBS.c.BBS_ID,
            TB_BBS.c.USE_YN.label("BBS_USE_YN"),
            TB_BBS.c.MBR_WRT_YN,
            TB_MBR.c.MBR_NM,
            TB_MNGR.c.MNGR_NM,
        )
        .select_from(source)
        .where(
            TB_PST.c.OPER_BNDL_SN == bundle_sn,
            TB_PST.c.DEL_YN == "N",
            TB_PST.c.UP_PST_SN.is_(None),  # 답변은 문의 쪽에서 다룬다
        )
    )


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    """글의 범위는 글의 동이다. 동이 없는 공통 글은 묶음 전체 범위만 본다."""
    return query if scope.whole else query.where(TB_PST.c.DONG_SN.in_(scope.dongs))


def _author(row: Any) -> str:
    return mask_name(str(row.MBR_NM)) if row.WRT_MBR_SN is not None else str(row.MNGR_NM or "")


def _summary(row: Any) -> AdminPostSummary:
    return AdminPostSummary(
        post_id=str(int(row.PST_SN)),
        board_key=BoardKey(str(row.BBS_ID)),
        title=str(row.PST_TTL),
        author_name=_author(row),
        pinned=row.NTC_YN == "Y",
        registered_on=kst_today(row.REG_DT),
    )


def _detail(row: Any) -> AdminPost:
    member_authored = row.WRT_MBR_SN is not None
    return AdminPost(
        **_summary(row).model_dump(),
        content=str(row.PST_CN),
        period_start=None if row.PSTG_BGNG_DT is None else utc(row.PSTG_BGNG_DT),
        period_end=None if row.PSTG_END_DT is None else utc(row.PSTG_END_DT),
        member_authored=member_authored,
        can_edit_content=not member_authored,
        version=int(row.RCRD_VER),
    )


def _filtered(
    db: Session, admin: Admin, now: datetime, *, board: BoardKey | None, q: str | None
) -> Select[Any]:
    """목록과 내보내기가 함께 쓰는 조회. 상단공지가 먼저고 삭제한 글은 나오지 않는다."""
    scope = permit(db, admin, AU.POST_W, now)
    query = _in_scope(_base(admin.bundle_sn), scope)
    if board is not None:
        query = query.where(TB_BBS.c.BBS_ID == board.value)
    if q and q.strip():
        query = query.where(TB_PST.c.PST_TTL.contains(q.strip(), autoescape=True))
    return query.order_by(TB_PST.c.NTC_YN.desc(), TB_PST.c.REG_DT.desc(), TB_PST.c.PST_SN.desc())


def list_posts(
    db: Session, admin: Admin, *, now: datetime, board: BoardKey | None, q: str | None, page: int, size: int
) -> AdminPostPage:
    query = _filtered(db, admin, now, board=board, q=q)
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AdminPostPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
    )


def export_csv(
    db: Session, admin: Admin, *, now: datetime, request_id: str, board: BoardKey | None, q: str | None
) -> bytes:
    """본문과 첨부는 담지 않고 작성자는 가린 값이다. 만들 때마다 작업이력에 남긴다."""
    rows = fetch_all(db, _filtered(db, admin, now, board=board, q=q))
    audit_export(db, admin, "TB_PST", len(rows), request_id, now, {"board": board, "q": q})
    return build_csv(
        ["게시물번호", "게시판", "제목", "작성자", "상단공지", "게시 시작", "게시 종료", "등록일"],
        [
            [
                str(int(r.PST_SN)),
                r.BBS_ID,
                r.PST_TTL,
                _author(r),
                r.NTC_YN == "Y",
                r.PSTG_BGNG_DT,
                r.PSTG_END_DT,
                kst_today(r.REG_DT),
            ]
            for r in rows
        ],
    )


def _load(db: Session, admin: Admin, now: datetime, post_id: str) -> tuple[Any, Scope]:
    """권한이 없으면 403, 없거나 범위 밖이거나 지운 글은 같은 404다."""
    scope = permit(db, admin, AU.POST_W, now)
    row = db.execute(_in_scope(_base(admin.bundle_sn), scope).where(TB_PST.c.PST_SN == int(post_id))).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row, scope


def get_post(db: Session, admin: Admin, *, now: datetime, post_id: str) -> AdminPost:
    return _detail(_load(db, admin, now, post_id)[0])


def _locked(db: Session, post_sn: int) -> Any:
    return db.execute(
        select(TB_PST.c.RCRD_VER, TB_PST.c.DEL_YN).where(TB_PST.c.PST_SN == post_sn).with_for_update()
    ).one()


def _checked(body: AdminPostWrite) -> tuple[str, str]:
    """본문은 허용된 서식만 남기고 정리한다. 정리한 뒤 읽을 글자가 없으면 거절한다."""
    title = body.title.strip()
    content = clean_body(body.content)
    if not title:
        raise ApiError(
            ErrorCode.RULE_REJECTED, "제목을 입력해 주세요.", fields={"title": "제목을 입력해 주세요."}
        )
    if not has_text(content):
        message = "본문에 읽을 수 있는 글자가 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"content": message})
    if body.period_start and body.period_end and body.period_end <= body.period_start:
        message = "게시 종료는 게시 시작보다 뒤여야 합니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"periodEnd": message})
    return title, content


def _post_dong(scope: Scope) -> int | None:
    """관리자가 올리는 글의 동. 묶음 전체 담당자는 공통 글이고, 동 담당자는 자기 동이다."""
    if scope.whole:
        return None
    if len(scope.dongs) != 1:
        message = "글을 올릴 동이 하나로 정해지지 않습니다. 담당 동이 하나인 담당자만 올릴 수 있습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message)
    return next(iter(scope.dongs))


def create_post(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: AdminPostWrite, idem_key: str
) -> AdminPost:
    scope = permit(db, admin, AU.POST_W, now)
    board = db.execute(
        select(TB_BBS.c.BBS_SN, TB_BBS.c.USE_YN, TB_BBS.c.MBR_WRT_YN)
        .where(TB_BBS.c.OPER_BNDL_SN == admin.bundle_sn, TB_BBS.c.BBS_ID == body.board_key.value)
        .with_for_update()  # 같은 게시판의 올리기를 한 줄로 세워 멱등 확인과 저장 사이의 틈을 막는다
    ).first()
    if board is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    prior = _replayed(db, admin.bundle_sn, "POST_CREATE", idem_key, body)
    if prior is not None:
        return _detail(db.execute(_base(admin.bundle_sn).where(TB_PST.c.PST_SN == prior)).one())
    if board.USE_YN != "Y" or board.MBR_WRT_YN == "Y":
        message = "사용을 중지했거나 회원이 쓰는 게시판에는 새 글을 올릴 수 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"boardKey": message})
    title, content = _checked(body)
    dong = _post_dong(scope)
    sn = int(
        db.execute(
            TB_PST.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                DONG_SN=dong,
                BBS_SN=board.BBS_SN,
                PST_TYPE_CD="PT.POST",
                PST_TTL=title,
                PST_CN=content,
                WRT_MNGR_SN=admin.admin_sn,
                PRVT_YN="N",
                NTC_YN=_yn(body.pinned),
                DEL_YN="N",
                PSTG_BGNG_DT=_naive(body.period_start),
                PSTG_END_DT=_naive(body.period_end),
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_PST.c.PST_SN)
        ).scalar_one()
    )
    _audit(
        db,
        admin,
        "POST_CREATE",
        "TB_PST",
        sn,
        request_id,
        now,
        f"{body.board_key.value} {_idem_mark(idem_key, body)}",
    )
    return _detail(db.execute(_base(admin.bundle_sn).where(TB_PST.c.PST_SN == sn)).one())


def update_post(
    db: Session, admin: Admin, *, now: datetime, request_id: str, post_id: str, body: AdminPostUpdate
) -> AdminPost:
    row, _ = _load(db, admin, now, post_id)
    if row.WRT_MBR_SN is not None:
        raise ApiError(
            ErrorCode.RULE_REJECTED, "회원이 쓴 글은 내용을 고칠 수 없습니다. 삭제만 할 수 있습니다."
        )
    if body.board_key.value != row.BBS_ID:
        message = "게시판은 바꿀 수 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"boardKey": message})
    locked = _locked(db, int(row.PST_SN))
    if locked.DEL_YN != "N":
        raise ApiError(ErrorCode.NOT_FOUND)
    if body.version != int(locked.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    title, content = _checked(body)
    db.execute(
        update(TB_PST)
        .where(TB_PST.c.PST_SN == row.PST_SN)
        .values(
            PST_TTL=title,
            PST_CN=content,
            NTC_YN=_yn(body.pinned),
            PSTG_BGNG_DT=_naive(body.period_start),
            PSTG_END_DT=_naive(body.period_end),
            MDFCN_DT=now,
            RCRD_VER=TB_PST.c.RCRD_VER + 1,
        )
    )
    _audit(db, admin, "POST_UPDATE", "TB_PST", int(row.PST_SN), request_id, now, f"{row.BBS_ID} 수정")
    return _detail(db.execute(_base(admin.bundle_sn).where(TB_PST.c.PST_SN == row.PST_SN)).one())


def delete_post(db: Session, admin: Admin, *, now: datetime, request_id: str, post_id: str) -> None:
    """삭제여부만 바꾸는 논리 삭제다. 회원이 쓴 글도 지울 수 있다."""
    row, _ = _load(db, admin, now, post_id)
    if _locked(db, int(row.PST_SN)).DEL_YN != "N":
        raise ApiError(ErrorCode.NOT_FOUND)
    db.execute(
        update(TB_PST)
        .where(TB_PST.c.PST_SN == row.PST_SN)
        .values(DEL_YN="Y", MDFCN_DT=now, RCRD_VER=TB_PST.c.RCRD_VER + 1)
    )
    _audit(db, admin, "POST_DELETE", "TB_PST", int(row.PST_SN), request_id, now, f"{row.BBS_ID} 삭제")
