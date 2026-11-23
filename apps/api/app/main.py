# FastAPI 앱 조립. 라우터, 오류 처리기, OpenAPI 설정을 한곳에서 묶는다
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.adapters.pg import build_gateway
from app.adapters.scan import build_scanner
from app.adapters.sms import build_sender
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.openapi import install_openapi
from app.core.ttl_cache import CACHE
from app.routers.admin import admin_router
from app.routers.health import router as health_router
from app.routers.user import user_router
from app.routers.webhook import router as webhook_router


def _operation_id(route: APIRoute) -> str:
    # 함수 이름을 그대로 쓰면 생성되는 TS 클라이언트의 메서드 이름이 읽기 쉽다.
    return route.name


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 운영은 설정과 실제 어댑터 지원 여부를 기동 때 확인한다. 개발의 계약 생성에는 DB 설정이 필요 없다.
    if os.environ.get("JORI_ENVIRONMENT") == "production":
        settings = get_settings()
        build_gateway(settings)
        build_sender(settings)
        build_scanner(settings)
        CACHE.configure(settings.cache_ttl_seconds)
    yield


def create_app() -> FastAPI:
    # 문서 화면과 스키마 URL은 열지 않는다. 계약 파일은 내보내기 도구로 만든다.
    app = FastAPI(
        title="조리읍 주민자치센터 수강시스템 API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    app.include_router(user_router)
    app.include_router(admin_router)
    app.include_router(webhook_router)
    app.include_router(health_router)
    install_openapi(app)
    return app


app = create_app()
