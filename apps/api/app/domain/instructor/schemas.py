# 공개 강사, 모집공고, 강사 지원 API의 요청·응답 모델
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.instructor.types import InstructorApplyStatus, RecruitmentStatus


class InstructorSummary(ApiModel):
    """승인·공개된 강사만이다. 심사 증빙은 어떤 공개 응답에도 없다(FN-018)."""

    instructor_id: SerialId
    name: str
    category_name: str | None
    course_names: list[str]


class InstructorPage(Page[InstructorSummary]):
    pass


class InstructorDetail(ApiModel):
    instructor_id: SerialId
    name: str
    category_name: str | None
    course_names: list[str]
    career: str | None = Field(description="경력 및 자격. 공식 자료에 없으면 null이다.")


class RecruitmentSummary(ApiModel):
    recruitment_id: SerialId
    title: str
    status: RecruitmentStatus
    period_start: date
    period_end: date
    headcount: int | None = Field(ge=1)


class RecruitmentPage(Page[RecruitmentSummary]):
    pass


class RecruitmentDetail(ApiModel):
    recruitment_id: SerialId
    title: str
    status: RecruitmentStatus
    announced_on: date
    period_start: date
    period_end: date
    headcount: int | None = Field(ge=1)
    field: str
    guide: str | None = Field(description="지원 안내. 공고 원본에 없으면 null이다.")
    can_apply: bool = Field(
        description="모집중이고 온라인 접수가 켜져 있고 아직 지원하지 않았을 때만 true다."
    )


class InstructorApplyWrite(ApiModel):
    """지원서는 텍스트 항목만 받는다. 증빙 파일은 첨부 설계 뒤에 더한다."""

    recruitment_id: SerialId
    desired_course: str = Field(min_length=1, max_length=100)
    category_id: SerialId
    career: str = Field(min_length=1, max_length=2000)


class InstructorApplication(ApiModel):
    application_id: SerialId
    recruitment_id: SerialId
    recruitment_title: str
    desired_course: str
    category_id: SerialId
    category_name: str
    career: str
    status: InstructorApplyStatus
    applied_at: AwareDatetime
    can_edit: bool = Field(description="서류 검토중·보완요청일 때만 고칠 수 있다.")


class InstructorApplicationPage(Page[InstructorApplication]):
    pass
