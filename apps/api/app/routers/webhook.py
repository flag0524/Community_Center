# PG 통보(웹훅) 수신. 대행사가 부르므로 세션·CSRF가 아니라 서명으로 인증한다(ADR-009, TDD 5.4.2)
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.adapters.pg.base import PaymentGateway, WebhookRejected
from app.auth.deps import Clock, get_bundle_resolver, get_clock, get_payment_gateway, request_id_of
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, ErrorCode
from app.db.bundle import BundleResolver
from app.db.session import get_db
from app.domain.payment import service

# 프런트 계약(OpenAPI)에 넣지 않는다. 호출하는 쪽이 브라우저가 아니다.
router = APIRouter(prefix="/api/pg", include_in_schema=False)
security_log = logging.getLogger("app.security")


@router.post("/webhook/{provider}")
async def receive_webhook(
    provider: Annotated[str, Path(min_length=1, max_length=40)],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    bundles: Annotated[BundleResolver, Depends(get_bundle_resolver)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> dict[str, str]:
    if provider != settings.pg_provider:  # 이 배포가 쓰는 대행사의 통보만 받는다
        raise ApiError(ErrorCode.NOT_FOUND)
    body = await request.body()
    request_id = request_id_of(request)
    try:
        result = await run_in_threadpool(
            service.receive_webhook,
            db,
            settings,
            gateway,
            bundle_sn=bundles.resolve(db),
            headers=dict(request.headers),
            body=body,
            request_id=request_id,
            clock=clock,
        )
    except WebhookRejected:
        # 서명이 틀린 통보는 저장하지 않고 보안 로그에만 남긴다. 본문과 서명 값은 기록하지 않는다
        security_log.warning("PG 통보 서명 검증 실패 request_id=%s", request_id)
        raise ApiError(ErrorCode.UNAUTHENTICATED) from None
    return {"result": result.value}
