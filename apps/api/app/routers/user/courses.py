# 강좌 목록·상세·강의계획 조회 라우터
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.errors import ErrorCode, not_implemented
from app.core.schema import SerialId
from app.domain.course.schemas import CourseDetail, CoursePage, CoursePlan
from app.domain.course.types import ReceptionState, Weekday
from app.routers.deps import PUBLIC_ERRORS, error_responses

router = APIRouter(tags=["courses"], responses=PUBLIC_ERRORS)

CourseId = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="강좌 일련번호(문자열)")]


@router.get("/courses")
def list_courses(
    q: Annotated[str | None, Query(max_length=100, description="강좌명·강사명 검색어")] = None,
    category_id: Annotated[SerialId | None, Query(alias="categoryId")] = None,
    day: Annotated[Weekday | None, Query()] = None,
    status: Annotated[ReceptionState | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50, description="페이지당 건수. 기본 10건(PRD Q13).")] = 10,
) -> CoursePage:
    not_implemented()


@router.get("/courses/{course_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_course(course_id: CourseId) -> CourseDetail:
    not_implemented()


@router.get("/courses/{course_id}/plan", responses=error_responses(ErrorCode.NOT_FOUND))
def get_course_plan(course_id: CourseId) -> CoursePlan:
    not_implemented()
