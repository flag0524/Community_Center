# 관리자 개인식별 명단 내보내기 라우터. AU.EXPORT와 대상 목록의 조회 권한·범위를 함께 검사한다
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, Security
from sqlalchemy.orm import Session

from app.auth.admin_access import Admin, require_admin
from app.auth.deps import Clock, get_clock, request_id_of
from app.core.errors import ErrorCode
from app.db.session import get_db
from app.domain.admin import pii_export
from app.domain.admin.export_schemas import PiiExportRequest
from app.routers.deps import MEMBER_ERRORS, IdempotencyKey, admin_session, csrf_header, error_responses

router = APIRouter(tags=["admin-export"], responses=MEMBER_ERRORS, dependencies=[Security(admin_session)])

PII_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "AES-256 암호화 ZIP. 암호는 이 응답의 X-Export-Password 헤더로 한 번만 준다",
        "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        "headers": {
            "X-Export-Password": {
                "description": "ZIP 암호. 서버는 보관하지 않아 다시 받을 수 없다",
                "schema": {"type": "string"},
            }
        },
    }
}


@router.post(
    "/exports/pii",
    response_class=Response,
    responses={
        **error_responses(ErrorCode.RULE_REJECTED, ErrorCode.IDEMPOTENCY_CONFLICT),
        **PII_RESPONSE,
    },
    dependencies=[Depends(csrf_header)],
)
def export_pii(
    request: Request,
    body: PiiExportRequest,
    idempotency_key: IdempotencyKey,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[Admin, Depends(require_admin)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    """요청 한 번에 ZIP을 만들어 바로 내려보내고 파일·암호를 남기지 않는다. 5천 행을 넘으면 거절한다.

    같은 멱등키로 다시 보내도 암호를 다시 줄 수 없으므로 새 파일을 만들지 않고 409다.
    생성 사실(누가·무엇을·몇 건)만 감사기록에 남긴다.
    """
    made = pii_export.export_pii(
        db, admin, now=clock(), request_id=request_id_of(request), idem_key=idempotency_key, body=body
    )
    return Response(
        made.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{made.filename}"',
            "X-Export-Password": made.password,
            "Cache-Control": "no-store",
        },
    )
