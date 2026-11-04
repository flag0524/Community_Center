# FastAPI 앱 조립. 라우터, 오류 처리기, OpenAPI 설정을 한곳에서 묶는다
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.errors import install_error_handlers
from app.core.openapi import install_openapi
from app.routers.admin import admin_router
from app.routers.user import user_router


def _operation_id(route: APIRoute) -> str:
    # 함수 이름을 그대로 쓰면 생성되는 TS 클라이언트의 메서드 이름이 읽기 쉽다.
    return route.name


def create_app() -> FastAPI:
    # 문서 화면과 스키마 URL은 열지 않는다. 계약 파일은 내보내기 도구로 만든다.
    app = FastAPI(
        title="조리읍 주민자치센터 수강시스템 API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        generate_unique_id_function=_operation_id,
    )
    install_error_handlers(app)
    app.include_router(user_router)
    app.include_router(admin_router)
    install_openapi(app)
    return app


app = create_app()
