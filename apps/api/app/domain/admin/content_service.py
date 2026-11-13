# 관리자 홈·센터 콘텐츠(AU.SITE_W). 이력이 있는 콘텐츠는 삭제하지 않고 게시 여부로 끈다(FN-011, DV133, ADR-060)
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.core.schema import PageCriteria
from app.core.times import kst_today, utc
from app.db.tables import TB_SITE_CONTS
from app.domain.admin.content_schemas import (
    AdminContent,
    AdminContentPage,
    AdminContentSummary,
    AdminContentUpdate,
    AdminContentWrite,
)
from app.domain.admin.content_types import ContentType
from app.domain.admin.education_service import _idem_mark, _replayed
from app.domain.admin.types import AdminAuthority as AU
from app.domain.board.sanitize import clean_body
from app.domain.site.schemas import ContentDocument, ContentSlug

# 스키마(CT)에 있는 코드만 저장할 수 있다. 나머지 유형은 개정 요청(R9·R14·Q23) 전까지 거절한다
TYPE_CODE = {
    ContentType.BANNER: "CT.BANNER",
    ContentType.POPUP: "CT.POPUP",
    ContentType.HISTORY: "CT.HISTORY",
    ContentType.INTRO: "CT.INTRO",
}
CODE_TYPE = {code: kind for kind, code in TYPE_CODE.items()}
HISTORY_ID = ContentSlug.CENTER_HISTORY.value  # 공개 화면이 이 식별자로 연혁을 찾는다
VERSION = "v1"  # 콘텐츠는 제자리에서 고친다. 약관처럼 버전을 늘리지 않는다
JOB = "CONTENT_CREATE"


def _yn(value: bool) -> str:
    return "Y" if value else "N"


def _naive(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(UTC).replace(tzinfo=None)


def _valid_link(link: str) -> bool:
    """사이트 안 경로(/로 시작하되 //가 아닌 것)이거나 https 주소만 받는다."""
    return (link.startswith("/") and not link.startswith("//")) or link.startswith("https://")


def _summary(row: Any) -> AdminContentSummary:
    return AdminContentSummary(
        content_id=str(int(row.SITE_CONTS_SN)),
        content_type=CODE_TYPE[str(row.CONTS_TYPE_CD)],
        title=str(row.CONTS_TTL),
        posted=row.PSTG_YN == "Y",
        period_start=None if row.PSTG_BGNG_DT is None else utc(row.PSTG_BGNG_DT),
        period_end=None if row.PSTG_END_DT is None else utc(row.PSTG_END_DT),
        sort_seq=int(row.SORT_SEQ),
        updated_on=kst_today(row.MDFCN_DT or row.REG_DT),
    )


def _detail(row: Any) -> AdminContent:
    return AdminContent(
        **_summary(row).model_dump(),
        body=str(row.CONTS_CN),
        url=None if row.URL_ADDR is None else str(row.URL_ADDR),
        contact=None,  # 연락처 유형은 저장 위치가 없다(PRD Q23, 개정 요청 R14)
        version=int(row.RCRD_VER),
    )


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    """콘텐츠의 범위는 콘텐츠의 동이다. 동이 없는 공통 콘텐츠는 묶음 전체 범위만 본다."""
    return query if scope.whole else query.where(TB_SITE_CONTS.c.DONG_SN.in_(scope.dongs))


def _base(bundle_sn: int) -> Select[Any]:
    return select(TB_SITE_CONTS).where(
        TB_SITE_CONTS.c.OPER_BNDL_SN == bundle_sn, TB_SITE_CONTS.c.CONTS_TYPE_CD.in_(list(CODE_TYPE))
    )


def list_contents(
    db: Session, admin: Admin, *, now: datetime, content_type: ContentType | None, page: int, size: int
) -> AdminContentPage:
    scope = permit(db, admin, AU.SITE_W, now)
    query = _in_scope(_base(admin.bundle_sn), scope)
    if content_type is not None:
        query = query.where(TB_SITE_CONTS.c.CONTS_TYPE_CD == TYPE_CODE.get(content_type, ""))
    query = query.order_by(
        TB_SITE_CONTS.c.CONTS_TYPE_CD, TB_SITE_CONTS.c.SORT_SEQ, TB_SITE_CONTS.c.SITE_CONTS_SN
    )
    total = int(db.execute(select(func.count()).select_from(query.order_by(None).subquery())).scalar_one())
    rows = db.execute(query.limit(size).offset((page - 1) * size)).all()
    return AdminContentPage(
        items=[_summary(r) for r in rows],
        page=page,
        size=size,
        total=total,
        criteria=PageCriteria(basis_at=utc(now)),
        can_create=True,
    )


def _load(db: Session, admin: Admin, now: datetime, content_id: str) -> Any:
    """권한이 없으면 403, 없거나 범위 밖이면 같은 404다."""
    scope = permit(db, admin, AU.SITE_W, now)
    row = db.execute(
        _in_scope(_base(admin.bundle_sn), scope).where(TB_SITE_CONTS.c.SITE_CONTS_SN == int(content_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_content(db: Session, admin: Admin, *, now: datetime, content_id: str) -> AdminContent:
    return _detail(_load(db, admin, now, content_id))


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _checked(body: AdminContentWrite) -> tuple[str, str, str | None]:
    """제목·본문·링크를 검사한다. 본문은 허용된 서식만 남기고, 연혁은 공개 화면이 읽는 JSON 모양이어야 한다."""
    kind = body.content_type
    if kind not in TYPE_CODE:
        raise _fail("contentType", "아직 저장할 수 없는 유형입니다(스키마 개정 요청 R9·R14 대기).")
    if body.contact is not None:
        raise _fail("contact", "연락처 구조 입력은 아직 저장할 수 없습니다(PRD Q23 대기).")
    title = body.title.strip()
    if not title:
        raise _fail("title", "제목을 입력해 주세요.")
    url = body.url.strip() if body.url else None
    if url is not None and not _valid_link(url):
        raise _fail("url", "링크는 사이트 안 경로(/로 시작)이거나 https 주소여야 합니다.")
    if body.period_start and body.period_end and body.period_end <= body.period_start:
        raise _fail("periodEnd", "게시 종료는 게시 시작보다 뒤여야 합니다.")
    if kind is ContentType.HISTORY:
        try:
            parsed = json.loads(body.body)
            if not isinstance(parsed, dict):
                raise ValueError("객체가 아니다")
            ContentDocument.model_validate({**parsed, "slug": HISTORY_ID, "title": title})
        except (ValueError, ValidationError):
            raise _fail("body", "연혁 본문은 {subtitle, sections} 모양의 JSON이어야 합니다.") from None
        return title, body.body, url
    return title, clean_body(body.body), url


def _content_dong(scope: Scope) -> int | None:
    """담당자가 올리는 콘텐츠의 동. 묶음 전체 담당자는 공통 콘텐츠이고 동 담당자는 자기 동이다."""
    if scope.whole:
        return None
    if len(scope.dongs) != 1:
        raise ApiError(ErrorCode.RULE_REJECTED, "콘텐츠를 올릴 동이 하나로 정해지지 않습니다.")
    return next(iter(scope.dongs))


def _audit(
    db: Session, admin: Admin, job: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_SITE_CONTS",
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def create_content(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: AdminContentWrite, idem_key: str
) -> AdminContent:
    scope = permit(db, admin, AU.SITE_W, now)
    # 같은 유형의 올리기를 한 줄로 세운다. 멱등 확인과 연혁 하나 규칙과 저장 사이의 틈을 막는다
    code = TYPE_CODE.get(body.content_type)
    if code is not None:
        db.execute(
            select(TB_SITE_CONTS.c.SITE_CONTS_SN)
            .where(TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn, TB_SITE_CONTS.c.CONTS_TYPE_CD == code)
            .with_for_update()
        ).all()
    prior = _replayed(db, admin.bundle_sn, JOB, idem_key, body)
    if prior is not None:
        return _detail(db.execute(_base(admin.bundle_sn).where(TB_SITE_CONTS.c.SITE_CONTS_SN == prior)).one())
    title, text, url = _checked(body)
    dong = _content_dong(scope)
    if body.content_type is ContentType.HISTORY:
        exists = db.execute(
            select(TB_SITE_CONTS.c.SITE_CONTS_SN).where(
                TB_SITE_CONTS.c.OPER_BNDL_SN == admin.bundle_sn, TB_SITE_CONTS.c.CONTS_ID == HISTORY_ID
            )
        ).first()
        if exists is not None:
            raise _fail("contentType", "연혁은 하나만 둘 수 있습니다. 기존 연혁을 고쳐 주세요.")
        conts_id = HISTORY_ID
    else:
        conts_id = f"{body.content_type.value.lower()}-{secrets.token_hex(4)}"
    sn = int(
        db.execute(
            TB_SITE_CONTS.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                DONG_SN=dong,
                CONTS_TYPE_CD=TYPE_CODE[body.content_type],
                CONTS_ID=conts_id,
                CONTS_TTL=title,
                CONTS_CN=text,
                VER_NM=VERSION,
                URL_ADDR=url,
                PSTG_BGNG_DT=_naive(body.period_start),
                PSTG_END_DT=_naive(body.period_end),
                PSTG_YN=_yn(body.posted),
                ESNTL_YN="N",
                SORT_SEQ=body.sort_seq,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_SITE_CONTS.c.SITE_CONTS_SN)
        ).scalar_one()
    )
    _audit(db, admin, JOB, sn, request_id, now, f"{body.content_type.value} {_idem_mark(idem_key, body)}")
    return _detail(db.execute(_base(admin.bundle_sn).where(TB_SITE_CONTS.c.SITE_CONTS_SN == sn)).one())


def update_content(
    db: Session, admin: Admin, *, now: datetime, request_id: str, content_id: str, body: AdminContentUpdate
) -> AdminContent:
    row = _load(db, admin, now, content_id)
    if body.content_type is not CODE_TYPE[str(row.CONTS_TYPE_CD)]:
        raise _fail("contentType", "유형은 바꿀 수 없습니다.")
    locked = db.execute(
        select(TB_SITE_CONTS.c.RCRD_VER)
        .where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)
        .with_for_update()
    ).one()
    if body.version != int(locked.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    title, text, url = _checked(body)
    db.execute(
        update(TB_SITE_CONTS)
        .where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)
        .values(
            CONTS_TTL=title,
            CONTS_CN=text,
            URL_ADDR=url,
            PSTG_BGNG_DT=_naive(body.period_start),
            PSTG_END_DT=_naive(body.period_end),
            PSTG_YN=_yn(body.posted),
            SORT_SEQ=body.sort_seq,
            MDFCN_DT=now,
            RCRD_VER=TB_SITE_CONTS.c.RCRD_VER + 1,
        )
    )
    change = f"{body.content_type.value} 게시 {_yn(body.posted)}"
    _audit(db, admin, "CONTENT_UPDATE", int(row.SITE_CONTS_SN), request_id, now, change)
    return _detail(
        db.execute(_base(admin.bundle_sn).where(TB_SITE_CONTS.c.SITE_CONTS_SN == row.SITE_CONTS_SN)).one()
    )
