# 관리자 권한 배정 API의 요청·응답 모델. 배정 한 행이 역할·범위·유효기간을 함께 정한다 (FN-056, NF-SER-004)
from datetime import date

from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, Page, SerialId
from app.domain.admin.role_types import AssignmentScope, AssignmentStatus
from app.domain.admin.types import AdminAuthority


class RoleAssignmentSummary(ApiModel):
    assignment_id: SerialId
    admin_name: str
    role_name: str
    scope: AssignmentScope
    scope_label: str = Field(description="운영묶음 전체 또는 동 이름")
    valid_from: date
    valid_to: date | None = Field(description="비우면 기간 제한 없음")
    status: AssignmentStatus
    granted_by: str = Field(description="부여한 관리자")


class RoleAssignmentPage(Page[RoleAssignmentSummary]):
    can_grant: bool = Field(description="새 배정을 만들 수 있는지")


class RoleAssignment(RoleAssignmentSummary):
    authorities: list[AdminAuthority] = Field(description="이 역할이 주는 기능 권한")
    granted_at: AwareDatetime
    version: int = Field(ge=1)
    can_revoke: bool = Field(description="유효하거나 시작 전인 배정만, 자기 배정이 아닐 때만 true")


class AssignmentAdminOption(ApiModel):
    id: SerialId
    name: str


class AssignmentRoleOption(ApiModel):
    id: SerialId
    name: str
    scopes: list[AssignmentScope] = Field(description="이 역할을 줄 수 있는 범위 유형")
    authorities: list[AdminAuthority]


class AssignmentDongOption(ApiModel):
    id: SerialId
    name: str


class AssignmentOptions(ApiModel):
    """내가 위임할 수 있는 것만 담는다. 보유 권한·범위·기간을 넘는 역할은 목록에 없다 (R28)."""

    admins: list[AssignmentAdminOption]
    roles: list[AssignmentRoleOption]
    dongs: list[AssignmentDongOption]


class AssignmentCreate(ApiModel):
    admin_id: SerialId
    role_id: SerialId
    scope: AssignmentScope
    dong_id: SerialId | None = Field(default=None, description="DONG일 때만")
    valid_from: date
    valid_to: date | None = None


class AssignmentRevoke(ApiModel):
    version: int = Field(ge=1)
