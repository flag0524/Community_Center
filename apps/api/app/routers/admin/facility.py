# 관리자 센터·강의실 관리 라우터. 조회와 변경 모두 AU.FCLT_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import facility_service as service
from app.domain.admin.facility_schemas import Facility, FacilityList, FacilityUpdate, FacilityWrite
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-facility"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(
    ErrorCode.NOT_FOUND, ErrorCode.VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT, ErrorCode.RULE_REJECTED
)
Db = Annotated[Session, Depends(get_db)]
Me = Annotated[Admin, Depends(require_admin)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/facilities")
def list_facilities(db: Db, admin: Me, clock: Now) -> FacilityList:
    return service.list_facilities(db, admin, now=clock())


@router.post("/facilities", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_facility(
    body: FacilityWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    admin: Me,
    clock: Now,
) -> Facility:
    return service.create_facility(
        db, admin, now=clock(), request_id=request_id_of(request), body=body, idem_key=idempotency_key
    )


@router.get("/facilities/{facility_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_facility(facility_id: Serial, db: Db, admin: Me, clock: Now) -> Facility:
    return service.get_facility(db, admin, now=clock(), facility_id=facility_id)


@router.put("/facilities/{facility_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_facility(
    facility_id: Serial, body: FacilityUpdate, request: Request, db: Db, admin: Me, clock: Now
) -> Facility:
    return service.update_facility(
        db, admin, now=clock(), request_id=request_id_of(request), facility_id=facility_id, body=body
    )
