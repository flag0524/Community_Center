# 관리자 센터·강의실 관리 라우터. 조회와 변경 모두 AU.FCLT_W다
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.facility_schemas import Facility, FacilityList, FacilityUpdate, FacilityWrite
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-facility"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
WRITE_ERRORS = error_responses(ErrorCode.VERSION_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT)


@router.get("/facilities")
def list_facilities() -> FacilityList:
    not_implemented()


@router.post("/facilities", status_code=201, responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def create_facility(body: FacilityWrite, idempotency_key: IdempotencyKey) -> Facility:
    not_implemented()


@router.get("/facilities/{facility_id}")
def get_facility(facility_id: Serial) -> Facility:
    not_implemented()


@router.put("/facilities/{facility_id}", responses=WRITE_ERRORS, dependencies=[Depends(csrf_header)])
def update_facility(facility_id: Serial, body: FacilityUpdate) -> Facility:
    not_implemented()
