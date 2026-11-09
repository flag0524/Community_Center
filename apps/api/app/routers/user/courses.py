# 강좌 목록·상세·강의계획 조회 라우터
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.auth.deps import Clock, get_bundle_resolver, get_clock
from app.core.errors import ErrorCode
from app.core.schema import SerialId
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.domain.course import service
from app.domain.course.schemas import CategoryList, CourseDetail, CoursePage, CoursePlan
from app.domain.course.types import ReceptionState, Weekday
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["courses"], responses=PUBLIC_ERRORS)

CourseId = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="강좌 일련번호(문자열)")]
Db = Annotated[Session, Depends(get_db)]
Bundles = Annotated[BundleResolver, Depends(get_bundle_resolver)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/categories")
def list_categories(db: Db, bundles: Bundles) -> CategoryList:
    return service.list_categories(db, bundles.resolve(db))


@router.get("/courses")
def list_courses(
    db: Db,
    bundles: Bundles,
    clock: Now,
    q: Annotated[str | None, Query(max_length=100, description="강좌명·강사명 검색어")] = None,
    category_id: Annotated[SerialId | None, Query(alias="categoryId")] = None,
    day: Annotated[Weekday | None, Query()] = None,
    status: Annotated[ReceptionState | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50, description="페이지당 건수. 기본 10건(PRD Q13).")] = 10,
) -> CoursePage:
    return service.list_courses(
        db,
        bundles.resolve(db),
        clock(),
        q=q,
        category_id=category_id,
        day=day,
        status=status,
        page=page,
        size=size,
    )


@router.get("/courses/{course_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_course(course_id: CourseId, db: Db, bundles: Bundles, clock: Now) -> CourseDetail:
    return service.get_course(db, bundles.resolve(db), course_id, clock())


@router.get("/courses/{course_id}/plan", responses=error_responses(ErrorCode.NOT_FOUND))
def get_course_plan(course_id: CourseId, db: Db, bundles: Bundles) -> CoursePlan:
    return service.get_plan(db, bundles.resolve(db), course_id)
