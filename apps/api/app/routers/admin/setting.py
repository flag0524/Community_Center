# 관리자 운영 설정 라우터. 읽기 전용이고 조회 권한은 AU.SITE_W를 후보로 둔다(PRD Q21)
from typing import Annotated

from fastapi import APIRouter, Path, Query, Security

from app.core.errors import ErrorCode, not_implemented
from app.domain.admin.setting_schemas import SettingDetail, SettingPage
from app.domain.admin.setting_types import OperRuleStatus
from app.routers.deps import MEMBER_ERRORS, admin_session, error_responses

router = APIRouter(tags=["admin-setting"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

Serial = Annotated[str, Path(pattern=r"^[0-9]{1,22}$", description="일련번호(문자열)")]


@router.get("/settings")
def list_settings(
    status: OperRuleStatus | None = None,
    q: Annotated[str | None, Query(max_length=100, description="항목명")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SettingPage:
    """운영 기준과 검토 상태. 확정은 실제 기능에 적용되었다는 뜻이 아니다."""
    not_implemented()


@router.get("/settings/{setting_id}", responses=error_responses(ErrorCode.NOT_FOUND))
def get_setting(setting_id: Serial) -> SettingDetail:
    not_implemented()
