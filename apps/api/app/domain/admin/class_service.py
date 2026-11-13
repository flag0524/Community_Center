# 관리자 강좌분류(센터별 분류). 이름은 서버가 정규화해 삭제한 것까지 포함해 중복을 막고 변경 전후 값을 작업이력으로 남긴다(CLSF-01~03, ADR-061)
import json
import re
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, permit, permit_any, scope_for
from app.core.errors import ApiError, ErrorCode
from app.core.times import utc
from app.db.tables import TB_CORS, TB_CORS_CLSF, TB_JOB_HSTRY, TB_MNGR, TB_OPER_BNDL
from app.domain.admin.class_schemas import (
    ClassHistoryEntry,
    ClassHistoryList,
    CourseClass,
    CourseClassList,
    CourseClassUpdate,
    CourseClassWrite,
)
from app.domain.admin.class_types import ClassHistoryAction
from app.domain.admin.education_service import _idem_mark, _replayed
from app.domain.admin.types import AdminAuthority as AU

NAME_MAX = 100  # 표시 이름 컬럼(CORS_CLSF_NM)의 길이. 넘으면 절단하지 않고 거절한다(CLSF-01)
KEY_MAX = 128  # 정규화키 컬럼(CLSF_NM_KEY)의 길이
JOBS = {
    ClassHistoryAction.CREATE: "CLSF_CREATE",
    ClassHistoryAction.RENAME: "CLSF_RENAME",
    ClassHistoryAction.REORDER: "CLSF_REORDER",
    ClassHistoryAction.DEACTIVATE: "CLSF_DEACTIVATE",
    ClassHistoryAction.ACTIVATE: "CLSF_ACTIVATE",
    ClassHistoryAction.DELETE: "CLSF_DELETE",
}
JOB_ACTION = {job: action for action, job in JOBS.items()}
IDEM_TAIL = re.compile(r"\s\[idem [0-9a-f]{16}:[0-9a-f]{16}\]$")
STATE = {True: "활성", False: "비활성"}


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def normalize(name: str) -> tuple[str, str]:
    """(표시 이름, 정규화키). 표시 이름은 공백만 정리하고 키는 NFKC·공백 정리·소문자 통일이다(CLSF-01)."""
    shown = " ".join(name.split())
    key = " ".join(unicodedata.normalize("NFKC", name).split()).lower()
    if not shown:
        raise _fail("name", "분류 이름을 입력해 주세요.")
    if len(shown) > NAME_MAX or len(key) > KEY_MAX:
        raise _fail("name", f"분류 이름은 {NAME_MAX}자까지 입력할 수 있습니다.")
    return shown, key


def _write_scope(db: Session, admin: Admin, now: datetime) -> None:
    """분류는 센터 전체의 설정이라 묶음 전체 범위의 담당자만 바꾼다."""
    if not permit(db, admin, AU.CORS_W, now).whole:
        raise ApiError(ErrorCode.FORBIDDEN)


def _counts(db: Session, bundle_sn: int) -> dict[int, int]:
    rows = db.execute(
        select(TB_CORS.c.CORS_CLSF_SN, func.count())
        .where(TB_CORS.c.OPER_BNDL_SN == bundle_sn, TB_CORS.c.CORS_CLSF_SN.is_not(None))
        .group_by(TB_CORS.c.CORS_CLSF_SN)
    ).all()
    return {int(r[0]): int(r[1]) for r in rows}


def _course_count(db: Session, bundle_sn: int, class_sn: int) -> int:
    return int(
        db.execute(
            select(func.count()).where(
                TB_CORS.c.OPER_BNDL_SN == bundle_sn, TB_CORS.c.CORS_CLSF_SN == class_sn
            )
        ).scalar_one()
    )


def _class(row: Any, count: int) -> CourseClass:
    active = row.USE_YN == "Y"
    return CourseClass(
        class_id=str(int(row.CORS_CLSF_SN)),
        name=str(row.CORS_CLSF_NM),
        sort_seq=int(row.SORT_SEQ),
        active=active,
        course_count=count,
        version=int(row.RCRD_VER),
        can_deactivate=active and count == 0,
        can_delete=count == 0,
    )


def list_classes(db: Session, admin: Admin, *, now: datetime) -> CourseClassList:
    """삭제하지 않은 분류를 순서대로 준다. 분류가 없는 기존 강좌는 자동으로 옮기지 않고 수만 알린다."""
    permit_any(db, admin, (AU.CORS_R, AU.CORS_W), now)
    rows = db.execute(
        select(TB_CORS_CLSF)
        .where(TB_CORS_CLSF.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS_CLSF.c.DEL_YN == "N")
        .order_by(TB_CORS_CLSF.c.SORT_SEQ, TB_CORS_CLSF.c.CORS_CLSF_SN)
    ).all()
    counts = _counts(db, admin.bundle_sn)
    uncategorized = int(
        db.execute(
            select(func.count()).where(
                TB_CORS.c.OPER_BNDL_SN == admin.bundle_sn, TB_CORS.c.CORS_CLSF_SN.is_(None)
            )
        ).scalar_one()
    )
    can_edit = scope_for(db, admin, AU.CORS_W, now).whole
    return CourseClassList(
        items=[_class(r, counts.get(int(r.CORS_CLSF_SN), 0)) for r in rows],
        can_edit=can_edit,
        uncategorized_count=uncategorized,
    )


def _row(db: Session, bundle_sn: int, class_id: str, *, lock: bool = False, deleted_ok: bool = False) -> Any:
    query = select(TB_CORS_CLSF).where(
        TB_CORS_CLSF.c.OPER_BNDL_SN == bundle_sn, TB_CORS_CLSF.c.CORS_CLSF_SN == int(class_id)
    )
    if not deleted_ok:
        query = query.where(TB_CORS_CLSF.c.DEL_YN == "N")
    row = db.execute(query.with_for_update() if lock else query).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def _record(
    db: Session,
    admin: Admin,
    action: ClassHistoryAction,
    class_sn: int,
    request_id: str,
    now: datetime,
    before: str | None,
    after: str | None,
    tail: str = "",
) -> None:
    """변경 전후 값은 작업이력 메모에 JSON으로 남긴다(CLSF-03). 고치거나 지우지 않는다."""
    record_job(
        db,
        actor="AK.ADMIN",
        job=JOBS[action],
        table="TB_CORS_CLSF",
        key=class_sn,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=json.dumps({"b": before, "a": after}, ensure_ascii=False) + tail,
    )


def _key_free(db: Session, bundle_sn: int, key: str, *, except_sn: int | None = None) -> None:
    """삭제한 분류까지 포함해 같은 정규화키가 있으면 거절한다. 삭제한 이름은 다시 쓸 수 없다."""
    query = select(TB_CORS_CLSF.c.CORS_CLSF_SN).where(
        TB_CORS_CLSF.c.OPER_BNDL_SN == bundle_sn, TB_CORS_CLSF.c.CLSF_NM_KEY == key
    )
    if except_sn is not None:
        query = query.where(TB_CORS_CLSF.c.CORS_CLSF_SN != except_sn)
    if db.execute(query).first() is not None:
        raise _fail("name", "같은 이름의 분류가 이미 있거나 삭제된 이름입니다.")


def create_class(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: CourseClassWrite, idem_key: str
) -> CourseClass:
    _write_scope(db, admin, now)
    # 분류 등록을 한 줄로 세운다. 분류가 하나도 없으면 잠글 행이 없으므로 묶음 행을 잠근다(READ COMMITTED는 틈을 잠그지 않는다)
    db.execute(
        select(TB_OPER_BNDL.c.OPER_BNDL_SN)
        .where(TB_OPER_BNDL.c.OPER_BNDL_SN == admin.bundle_sn)
        .with_for_update()
    ).one()
    prior = _replayed(db, admin.bundle_sn, JOBS[ClassHistoryAction.CREATE], idem_key, body)
    if prior is not None:
        return _class(
            _row(db, admin.bundle_sn, str(prior), deleted_ok=True), _course_count(db, admin.bundle_sn, prior)
        )
    shown, key = normalize(body.name)
    _key_free(db, admin.bundle_sn, key)
    sn = int(
        db.execute(
            TB_CORS_CLSF.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                CORS_CLSF_NM=shown,
                CLSF_NM_KEY=key,
                SORT_SEQ=body.sort_seq,
                USE_YN="Y",
                DEL_YN="N",
                REG_MNGR_SN=admin.admin_sn,
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_CORS_CLSF.c.CORS_CLSF_SN)
        ).scalar_one()
    )
    _record(
        db,
        admin,
        ClassHistoryAction.CREATE,
        sn,
        request_id,
        now,
        None,
        shown,
        " " + _idem_mark(idem_key, body),
    )
    return _class(_row(db, admin.bundle_sn, str(sn)), 0)


def update_class(
    db: Session, admin: Admin, *, now: datetime, request_id: str, class_id: str, body: CourseClassUpdate
) -> CourseClass:
    _write_scope(db, admin, now)
    _row(db, admin.bundle_sn, class_id)
    row = _row(db, admin.bundle_sn, class_id, lock=True)
    if body.version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    shown, key = normalize(body.name)
    sn = int(row.CORS_CLSF_SN)
    values: dict[str, Any] = {}
    if key != row.CLSF_NM_KEY or shown != row.CORS_CLSF_NM:
        _key_free(db, admin.bundle_sn, key, except_sn=sn)
        values.update(CORS_CLSF_NM=shown, CLSF_NM_KEY=key)
    if body.sort_seq != int(row.SORT_SEQ):
        values["SORT_SEQ"] = body.sort_seq
    if values:
        db.execute(
            update(TB_CORS_CLSF)
            .where(TB_CORS_CLSF.c.CORS_CLSF_SN == sn)
            .values(**values, MDFCN_DT=now, RCRD_VER=TB_CORS_CLSF.c.RCRD_VER + 1)
        )
        if "CORS_CLSF_NM" in values:
            _record(db, admin, ClassHistoryAction.RENAME, sn, request_id, now, str(row.CORS_CLSF_NM), shown)
        if "SORT_SEQ" in values:
            _record(
                db,
                admin,
                ClassHistoryAction.REORDER,
                sn,
                request_id,
                now,
                str(int(row.SORT_SEQ)),
                str(body.sort_seq),
            )
    return _class(_row(db, admin.bundle_sn, class_id), _course_count(db, admin.bundle_sn, sn))


def _locked_count(db: Session, admin: Admin, class_id: str, version: int) -> tuple[Any, int]:
    """분류 행을 잠근 채 같은 트랜잭션에서 연결 강좌 수를 센다. 강좌가 분류를 연결할 때도 같은 행을 잠근다(CLSF-02)."""
    row = _row(db, admin.bundle_sn, class_id, lock=True)
    if version != int(row.RCRD_VER):
        raise ApiError(ErrorCode.VERSION_CONFLICT)
    return row, _course_count(db, admin.bundle_sn, int(row.CORS_CLSF_SN))


def deactivate_class(
    db: Session, admin: Admin, *, now: datetime, request_id: str, class_id: str, version: int
) -> CourseClass:
    """연결 강좌가 있으면 거절한다. 기존 연결은 그대로 둔다."""
    _write_scope(db, admin, now)
    row, count = _locked_count(db, admin, class_id, version)
    if row.USE_YN != "Y":
        raise ApiError(ErrorCode.CONFLICT_STATE, "이미 비활성인 분류입니다.")
    if count > 0:
        message = f"연결된 강좌가 {count}건 있어 비활성할 수 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"classId": message})
    sn = int(row.CORS_CLSF_SN)
    db.execute(
        update(TB_CORS_CLSF)
        .where(TB_CORS_CLSF.c.CORS_CLSF_SN == sn)
        .values(USE_YN="N", MDFCN_DT=now, RCRD_VER=TB_CORS_CLSF.c.RCRD_VER + 1)
    )
    _record(db, admin, ClassHistoryAction.DEACTIVATE, sn, request_id, now, STATE[True], STATE[False])
    return _class(_row(db, admin.bundle_sn, class_id), count)


def activate_class(
    db: Session, admin: Admin, *, now: datetime, request_id: str, class_id: str, version: int
) -> CourseClass:
    _write_scope(db, admin, now)
    row, count = _locked_count(db, admin, class_id, version)
    if row.USE_YN == "Y":
        raise ApiError(ErrorCode.CONFLICT_STATE, "이미 활성인 분류입니다.")
    sn = int(row.CORS_CLSF_SN)
    db.execute(
        update(TB_CORS_CLSF)
        .where(TB_CORS_CLSF.c.CORS_CLSF_SN == sn)
        .values(USE_YN="Y", MDFCN_DT=now, RCRD_VER=TB_CORS_CLSF.c.RCRD_VER + 1)
    )
    _record(db, admin, ClassHistoryAction.ACTIVATE, sn, request_id, now, STATE[False], STATE[True])
    return _class(_row(db, admin.bundle_sn, class_id), count)


def delete_class(
    db: Session, admin: Admin, *, now: datetime, request_id: str, class_id: str, version: int
) -> None:
    """논리삭제한다. 연결 강좌가 있으면 거절하고 삭제한 이름은 다시 쓸 수 없다."""
    _write_scope(db, admin, now)
    row, count = _locked_count(db, admin, class_id, version)
    if count > 0:
        message = f"연결된 강좌가 {count}건 있어 삭제할 수 없습니다."
        raise ApiError(ErrorCode.RULE_REJECTED, message, fields={"classId": message})
    sn = int(row.CORS_CLSF_SN)
    db.execute(
        update(TB_CORS_CLSF)
        .where(TB_CORS_CLSF.c.CORS_CLSF_SN == sn)
        .values(DEL_YN="Y", DEL_DT=now, MDFCN_DT=now, RCRD_VER=TB_CORS_CLSF.c.RCRD_VER + 1)
    )
    _record(db, admin, ClassHistoryAction.DELETE, sn, request_id, now, str(row.CORS_CLSF_NM), None)


def history(db: Session, admin: Admin, *, now: datetime, class_id: str) -> ClassHistoryList:
    """등록·명칭·순서 변경·비활성·재활성·삭제의 전후 값과 처리자. 최근 것이 먼저다."""
    permit_any(db, admin, (AU.CORS_R, AU.CORS_W), now)
    _row(db, admin.bundle_sn, class_id, deleted_ok=True)
    rows = db.execute(
        select(TB_JOB_HSTRY.c.JOB_CD, TB_JOB_HSTRY.c.REG_DT, TB_JOB_HSTRY.c.CHG_CN, TB_MNGR.c.MNGR_NM)
        .select_from(TB_JOB_HSTRY.outerjoin(TB_MNGR, TB_MNGR.c.MNGR_SN == TB_JOB_HSTRY.c.MNGR_SN))
        .where(
            TB_JOB_HSTRY.c.OPER_BNDL_SN == admin.bundle_sn,
            TB_JOB_HSTRY.c.JOB_CD.in_(list(JOB_ACTION)),
            TB_JOB_HSTRY.c.TRGT_TBL_NM == "TB_CORS_CLSF",
            TB_JOB_HSTRY.c.TRGT_KEY_VL == str(int(class_id)),
        )
        .order_by(TB_JOB_HSTRY.c.JOB_HSTRY_SN.desc())
    ).all()
    items = []
    for r in rows:
        values = json.loads(IDEM_TAIL.sub("", str(r.CHG_CN)))
        items.append(
            ClassHistoryEntry(
                at=utc(r.REG_DT),
                by=str(r.MNGR_NM or ""),
                action=JOB_ACTION[str(r.JOB_CD)],
                before=values["b"],
                after=values["a"],
            )
        )
    return ClassHistoryList(items=items)
