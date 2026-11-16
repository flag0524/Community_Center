# 공개 강사·모집공고 조회와 강사 지원(작성·수정·내 지원내역) 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from sqlalchemy.orm import Session

from app.auth.deps import (
    Clock,
    Member,
    get_bundle_resolver,
    get_clock,
    request_id_of,
    require_member,
    require_member_write,
)
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode, not_implemented
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.domain.instructor import service
from app.domain.instructor.schemas import (
    InstructorApplication,
    InstructorApplicationPage,
    InstructorApplyWrite,
    InstructorDetail,
    InstructorPage,
    RecruitmentDetail,
    RecruitmentPage,
)
from app.routers.deps import (
    MEMBER_ERRORS,
    PUBLIC_ERRORS,
    IdempotencyKey,
    csrf_header,
    error_responses,
    member_session,
)

# 강사현황과 모집공고는 누구나 본다.
router = APIRouter(tags=["instructor"], responses=PUBLIC_ERRORS)
# 지원은 로그인한 회원만이다.
member_router = APIRouter(
    tags=["instructor"], responses=MEMBER_ERRORS, dependencies=[Security(member_session)]
)

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]
Page_ = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=50)]
NOT_FOUND = error_responses(ErrorCode.NOT_FOUND)
WRITE_ERRORS = error_responses(ErrorCode.NOT_FOUND, ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT)
Db = Annotated[Session, Depends(get_db)]
Bundles = Annotated[BundleResolver, Depends(get_bundle_resolver)]
Now = Annotated[Clock, Depends(get_clock)]
Me = Annotated[Member, Depends(require_member)]
MeWrite = Annotated[Member, Depends(require_member_write)]
Config = Annotated[Settings, Depends(get_settings)]


def optional_member(request: Request, db: Db, clock: Now, bundles: Bundles) -> Member | None:
    """공개 화면이 로그인한 회원에게만 보여 줄 값(이미 지원했는지)을 위해 쓴다. 로그인이 없으면 None이다."""
    try:
        return require_member(request, db, clock, bundles)
    except ApiError as error:
        if error.code is ErrorCode.UNAUTHENTICATED:
            return None
        raise


MaybeMember = Annotated[Member | None, Depends(optional_member)]


@router.get("/instructors")
def list_instructors(
    q: Annotated[str | None, Query(max_length=100, description="강사명 또는 강좌명")] = None,
    page: Page_ = 1,
    size: Size = 10,
) -> InstructorPage:
    not_implemented()


@router.get("/instructors/{instructor_id}", responses=NOT_FOUND)
def get_instructor(instructor_id: Serial) -> InstructorDetail:
    not_implemented()


@router.get("/instructor-recruitments")
def list_recruitments(
    db: Db, bundles: Bundles, clock: Now, page: Page_ = 1, size: Size = 10
) -> RecruitmentPage:
    return service.list_recruitments(db, bundles.resolve(db), clock(), page=page, size=size)


@router.get("/instructor-recruitments/{recruitment_id}", responses=NOT_FOUND)
def get_recruitment(
    recruitment_id: Serial, db: Db, bundles: Bundles, clock: Now, me: MaybeMember
) -> RecruitmentDetail:
    return service.get_recruitment(
        db, bundles.resolve(db), clock(), recruitment_id, None if me is None else me.member_sn
    )


@member_router.get("/me/instructor-applications")
def list_my_instructor_applications(
    db: Db, me: Me, clock: Now, page: Page_ = 1, size: Size = 10
) -> InstructorApplicationPage:
    return service.list_mine(db, me.bundle_sn, me.member_sn, clock(), page=page, size=size)


@member_router.post(
    "/me/instructor-applications",
    status_code=201,
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def create_instructor_application(
    body: InstructorApplyWrite,
    idempotency_key: IdempotencyKey,
    request: Request,
    db: Db,
    me: MeWrite,
    settings: Config,
    clock: Now,
) -> InstructorApplication:
    """모집중이 아닌 공고나 이미 지원한 공고는 RULE_REJECTED다. 직접 요청도 같은 검사를 한다."""
    return service.create_mine(
        db,
        settings,
        bundle_sn=me.bundle_sn,
        member_sn=me.member_sn,
        body=body,
        idem_key=idempotency_key,
        now=clock(),
        request_id=request_id_of(request),
    )


@member_router.get("/me/instructor-applications/{application_id}", responses=NOT_FOUND)
def get_my_instructor_application(application_id: Serial, db: Db, me: Me) -> InstructorApplication:
    return service.get_mine(db, me.bundle_sn, me.member_sn, application_id)


@member_router.put(
    "/me/instructor-applications/{application_id}",
    responses=WRITE_ERRORS,
    dependencies=[Depends(csrf_header)],
)
def update_instructor_application(
    application_id: Serial,
    body: InstructorApplyWrite,
    request: Request,
    db: Db,
    me: MeWrite,
    clock: Now,
) -> InstructorApplication:
    """서류 검토중·보완요청일 때만 고칠 수 있다(RULE_REJECTED)."""
    return service.update_mine(
        db,
        bundle_sn=me.bundle_sn,
        member_sn=me.member_sn,
        application_id=application_id,
        body=body,
        now=clock(),
        request_id=request_id_of(request),
    )
