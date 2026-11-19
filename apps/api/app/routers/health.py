# 운영 감시용 건강 확인. DB 연결과 워커 생존(상태 파일의 마지막 실행)을 보고한다(TDD 7, ADR-027·050)
import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import Clock, get_clock
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.worker.status import is_stale, jobs_healthy, read_state

router = APIRouter()

# 설정 해시에 넣는 값. 비밀키·DB 주소·계정처럼 비밀이거나 배포마다 다른 접속 정보는 넣지 않는다
PUBLIC_SETTINGS = (
    "environment",
    "site_id",
    "cookie_secure",
    "admin_lock_failures",
    "admin_lock_minutes",
    "sms_provider",
    "pg_provider",
    "file_scanner",
    "pbkdf2_iterations",
)


def _digest(text_value: str) -> str:
    return hashlib.sha256(text_value.encode()).hexdigest()


def _jobs(state: dict[str, Any]) -> dict[str, Any]:
    """작업별 마지막 실행 시각과 성공 여부만 보인다. 오류 내용·처리 대상은 담지 않는다."""
    return {
        name: {"lastRun": item.get("lastRun"), "ok": item.get("ok") is True}
        for name, item in state.items()
        if isinstance(item, dict) and "lastRun" in item
    }


@router.get("/api/health/version", include_in_schema=False)
def version(
    db: Annotated[Session, Depends(get_db)], settings: Annotated[Settings, Depends(get_settings)]
) -> JSONResponse:
    """배포 검증용. 커밋 해시·마이그레이션 리비전·코드표 체크섬·설정 해시를 검수 기록과 대조한다(TDD 11장, R24).
    코드표 체크섬은 코드 값 자체만 본다. 담당자가 바꾸는 표시명·순서·사용 여부는 넣지 않는다. 인증 없이 부르며 비밀값은 싣지 않는다."""
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        codes = db.execute(text("SELECT COM_CD FROM TB_COM_CD ORDER BY COM_CD")).scalars().all()
    except Exception:
        return JSONResponse({"status": "degraded", "database": False}, status_code=503)
    public = {name: getattr(settings, name) for name in PUBLIC_SETTINGS}
    body = {
        "commit": settings.build_commit,
        "migration": None if revision is None else str(revision),
        "codeSetChecksum": _digest("\n".join(str(code).strip() for code in codes)),
        "codeCount": len(codes),
        "configHash": _digest(json.dumps(public, sort_keys=True)),
    }
    return JSONResponse(body)


@router.get("/api/health", include_in_schema=False)
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> JSONResponse:
    """DB 연결·워커 생존·작업별 성공과 지연을 함께 확인해 200 또는 503을 준다. 인증 없이 부른다."""
    try:
        db.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    path = Path(settings.worker_status_file)
    state = read_state(path)
    jobs = _jobs(state)
    running = not is_stale(path, clock())
    healthy = database and running and jobs_healthy(state, clock())
    body = {
        "status": "ok" if healthy else "degraded",
        "database": database,
        "worker": {"running": running, "jobs": jobs},
    }
    return JSONResponse(body, status_code=200 if healthy else 503)
