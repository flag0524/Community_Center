# 관리자 센터·강의실 관리(AU.FCLT_W). 사용을 중지해도 기존 일정은 유지하고 새 일정에는 배정하지 못한다(FN-050, DV106, ADR-061)
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin, Scope, permit
from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_CORS_SCHDL, TB_FCLT
from app.db.versioned import update_versioned
from app.domain.admin.education_service import _idem_mark, _replayed
from app.domain.admin.education_types import FacilityKind
from app.domain.admin.facility_schemas import Facility, FacilityList, FacilityUpdate, FacilityWrite
from app.domain.admin.types import AdminAuthority as AU

KIND_CODE = {FacilityKind.CENTER: "FT.CENTER", FacilityKind.ROOM: "FT.ROOM"}
CODE_KIND = {code: kind for kind, code in KIND_CODE.items()}
FLOOR_LABEL = "층: "  # 층을 담을 컬럼이 없어 설명(FCLT_EXPLN)에 이 표식과 함께 둔다(개정 요청 R35)


def _fail(field: str, message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={field: message})


def _yn(value: bool) -> str:
    return "Y" if value else "N"


def _in_scope(query: Select[Any], scope: Scope) -> Select[Any]:
    """시설의 범위는 시설의 동이다. 강의실은 센터의 동을 따른다. 동이 없는 시설은 묶음 전체 범위만 본다."""
    return query if scope.whole else query.where(TB_FCLT.c.DONG_SN.in_(scope.dongs))


def _count() -> Any:
    return (
        select(func.count())
        .where(TB_CORS_SCHDL.c.FCLT_SN == TB_FCLT.c.FCLT_SN)
        .correlate(TB_FCLT)
        .scalar_subquery()
    )


def _base(bundle_sn: int) -> Select[Any]:
    return select(TB_FCLT, _count().label("SCHEDULE_CNT")).where(TB_FCLT.c.OPER_BNDL_SN == bundle_sn)


def _floor(explanation: Any) -> str | None:
    text = None if explanation is None else str(explanation)
    return text.removeprefix(FLOOR_LABEL) if text and text.startswith(FLOOR_LABEL) else None


def _facility(row: Any) -> Facility:
    return Facility(
        facility_id=str(int(row.FCLT_SN)),
        kind=CODE_KIND[str(row.FCLT_TYPE_CD)],
        parent_id=None if row.UP_FCLT_SN is None else str(int(row.UP_FCLT_SN)),
        name=str(row.FCLT_NM),
        floor=_floor(row.FCLT_EXPLN),
        address=None if row.ADDR is None else str(row.ADDR),
        is_public=True,  # 공개 여부를 담을 컬럼이 없어 항상 공개로 본다(개정 요청 R35)
        in_use=row.USE_YN == "Y",
        version=int(row.RCRD_VER),
        schedule_count=int(row.SCHEDULE_CNT),
    )


def list_facilities(db: Session, admin: Admin, *, now: datetime) -> FacilityList:
    """센터와 강의실 전체다. 센터가 먼저고 그 아래 강의실이 이름순으로 온다."""
    scope = permit(db, admin, AU.FCLT_W, now)
    query = _in_scope(_base(admin.bundle_sn), scope).order_by(
        func.coalesce(TB_FCLT.c.UP_FCLT_SN, TB_FCLT.c.FCLT_SN),
        TB_FCLT.c.UP_FCLT_SN.is_not(None),
        TB_FCLT.c.FCLT_NM,
        TB_FCLT.c.FCLT_SN,
    )
    return FacilityList(items=[_facility(r) for r in db.execute(query).all()])


def _load(db: Session, admin: Admin, now: datetime, facility_id: str) -> Any:
    """권한이 없으면 403, 없거나 범위 밖이면 같은 404다."""
    scope = permit(db, admin, AU.FCLT_W, now)
    row = db.execute(
        _in_scope(_base(admin.bundle_sn), scope).where(TB_FCLT.c.FCLT_SN == int(facility_id))
    ).first()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    return row


def get_facility(db: Session, admin: Admin, *, now: datetime, facility_id: str) -> Facility:
    return _facility(_load(db, admin, now, facility_id))


def _checked(body: FacilityWrite) -> tuple[str, str | None, str | None]:
    """이름·층·주소를 검사한다. 공개 여부는 저장할 곳이 없어 현재 값(공개)과 다르면 거절한다."""
    name = body.name.strip()
    if not name:
        raise _fail("name", "이름을 입력해 주세요.")
    if not body.is_public:
        raise _fail("isPublic", "비공개 시설은 아직 저장할 수 없습니다(스키마 개정 요청 R35 대기).")
    floor = body.floor.strip() if body.floor else None
    address = body.address.strip() if body.address else None
    if body.kind is FacilityKind.ROOM and address:
        raise _fail("address", "주소는 센터만 입력합니다.")
    return name, (FLOOR_LABEL + floor if floor else None), address or None


def _parent_dong(db: Session, admin: Admin, scope: Scope, parent_id: str) -> int | None:
    """강의실의 상위 센터. 이 담당자의 범위 안의 센터여야 한다."""
    parent = db.execute(
        _in_scope(select(TB_FCLT).where(TB_FCLT.c.OPER_BNDL_SN == admin.bundle_sn), scope)
        .where(TB_FCLT.c.FCLT_SN == int(parent_id), TB_FCLT.c.FCLT_TYPE_CD == "FT.CENTER")
        .with_for_update()  # 같은 센터 아래의 올리기를 한 줄로 세워 이름 중복 확인과 저장 사이의 틈을 막는다
    ).first()
    if parent is None:
        raise _fail("parentId", "상위 센터를 찾을 수 없습니다.")
    return None if parent.DONG_SN is None else int(parent.DONG_SN)


def _duplicate(
    db: Session, bundle_sn: int, parent: str | None, name: str, *, except_sn: int | None = None
) -> None:
    """같은 위치(같은 상위 센터, 센터끼리는 묶음 안)의 같은 이름은 거절한다. 사용 중지한 시설도 센다."""
    query = select(TB_FCLT.c.FCLT_SN).where(TB_FCLT.c.OPER_BNDL_SN == bundle_sn, TB_FCLT.c.FCLT_NM == name)
    query = query.where(
        TB_FCLT.c.UP_FCLT_SN.is_(None) if parent is None else TB_FCLT.c.UP_FCLT_SN == int(parent)
    )
    if except_sn is not None:
        query = query.where(TB_FCLT.c.FCLT_SN != except_sn)
    if db.execute(query).first() is not None:
        raise _fail("name", "같은 위치에 같은 이름의 시설이 있습니다.")


def _single_dong(scope: Scope) -> int | None:
    """담당자가 만드는 센터의 동. 묶음 전체 담당자는 공통 센터이고 동 담당자는 자기 동이다."""
    if scope.whole:
        return None
    if len(scope.dongs) != 1:
        raise ApiError(ErrorCode.RULE_REJECTED, "시설을 만들 동이 하나로 정해지지 않습니다.")
    return next(iter(scope.dongs))


def _audit(
    db: Session, admin: Admin, job: str, key: int, request_id: str, now: datetime, change: str
) -> None:
    record_job(
        db,
        actor="AK.ADMIN",
        job=job,
        table="TB_FCLT",
        key=key,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=change,
    )


def create_facility(
    db: Session, admin: Admin, *, now: datetime, request_id: str, body: FacilityWrite, idem_key: str
) -> Facility:
    scope = permit(db, admin, AU.FCLT_W, now)
    name, explanation, address = _checked(body)
    if body.kind is FacilityKind.CENTER:
        if body.parent_id is not None:
            raise _fail("parentId", "센터는 상위 시설이 없습니다.")
        # 센터끼리의 올리기를 한 줄로 세운다
        db.execute(
            select(TB_FCLT.c.FCLT_SN)
            .where(
                TB_FCLT.c.OPER_BNDL_SN == admin.bundle_sn,
                TB_FCLT.c.UP_FCLT_SN.is_(None),
            )
            .with_for_update()
        ).all()
        dong = _single_dong(scope)
    else:
        if body.parent_id is None:
            raise _fail("parentId", "강의실은 상위 센터가 필요합니다.")
        dong = _parent_dong(db, admin, scope, body.parent_id)
    prior = _replayed(db, admin.bundle_sn, "FCLT_CREATE", idem_key, body)
    if prior is not None:
        return _facility(db.execute(_base(admin.bundle_sn).where(TB_FCLT.c.FCLT_SN == prior)).one())
    _duplicate(db, admin.bundle_sn, body.parent_id, name)
    sn = int(
        db.execute(
            TB_FCLT.insert()
            .values(
                OPER_BNDL_SN=admin.bundle_sn,
                DONG_SN=dong,
                UP_FCLT_SN=None if body.parent_id is None else int(body.parent_id),
                FCLT_TYPE_CD=KIND_CODE[body.kind],
                FCLT_NM=name,
                ADDR=address,
                FCLT_EXPLN=explanation,
                USE_YN=_yn(body.in_use),
                REG_DT=now,
                RCRD_VER=1,
            )
            .returning(TB_FCLT.c.FCLT_SN)
        ).scalar_one()
    )
    _audit(db, admin, "FCLT_CREATE", sn, request_id, now, f"{body.kind.value} {_idem_mark(idem_key, body)}")
    return _facility(db.execute(_base(admin.bundle_sn).where(TB_FCLT.c.FCLT_SN == sn)).one())


def update_facility(
    db: Session, admin: Admin, *, now: datetime, request_id: str, facility_id: str, body: FacilityUpdate
) -> Facility:
    row = _load(db, admin, now, facility_id)
    if body.kind is not CODE_KIND[str(row.FCLT_TYPE_CD)]:
        raise _fail("kind", "종류는 바꿀 수 없습니다.")
    parent = None if row.UP_FCLT_SN is None else str(int(row.UP_FCLT_SN))
    if body.parent_id != parent:
        raise _fail("parentId", "상위 센터는 바꿀 수 없습니다.")
    name, explanation, address = _checked(body)
    _duplicate(db, admin.bundle_sn, parent, name, except_sn=int(row.FCLT_SN))
    update_versioned(
        db,
        TB_FCLT,
        {"OPER_BNDL_SN": admin.bundle_sn, "FCLT_SN": int(row.FCLT_SN)},
        body.version,
        {"FCLT_NM": name, "ADDR": address, "FCLT_EXPLN": explanation, "USE_YN": _yn(body.in_use)},
    )
    change = f"{body.kind.value} 사용 {_yn(body.in_use)}"
    _audit(db, admin, "FCLT_UPDATE", int(row.FCLT_SN), request_id, now, change)
    return _facility(db.execute(_base(admin.bundle_sn).where(TB_FCLT.c.FCLT_SN == row.FCLT_SN)).one())
