# 관리자 로그인 세션과 권한 응답(메뉴 포함)의 요청·응답 모델
from pydantic import AwareDatetime, Field

from app.core.schema import ApiModel, SerialId, ServerTimed
from app.domain.admin.types import AdminAuthority


class AdminLoginRequest(ApiModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class AdminBrief(ApiModel):
    admin_id: SerialId
    name: str
    login_id: str


class AdminSession(ServerTimed):
    authenticated: bool
    csrf_token: str | None = Field(default=None, description="상태 변경 요청의 X-CSRF-Token 헤더에 넣는 값")
    admin: AdminBrief | None = None
    idle_timeout_seconds: int | None = Field(default=None, description="유휴 만료 시간. 관리자 900초.")
    expires_at: AwareDatetime | None = Field(
        default=None, description="지금 활동이 없으면 세션이 끝나는 서버 시각. 연장하면 뒤로 밀린다."
    )


class MenuItem(ApiModel):
    key: str = Field(max_length=40)
    label: str = Field(max_length=40)
    path: str = Field(pattern=r"^/[a-z0-9/-]*$", description="관리자 앱 안의 경로")


class MenuGroup(ApiModel):
    key: str = Field(max_length=40)
    title: str = Field(max_length=40)
    items: list[MenuItem] = Field(min_length=1)


class AdminPermissions(ApiModel):
    """로그인한 관리자의 현재 유효 배정에서 나온 권한. 메뉴는 이 응답으로만 구성한다(FN-056)."""

    role_names: list[str] = Field(description="유효한 배정의 역할 이름")
    scope_label: str = Field(description="배정 범위의 표시 이름(예: 운영묶음 이름)")
    authorities: list[AdminAuthority]
    menu: list[MenuGroup]
