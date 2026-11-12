# 운영 감시용 건강 확인. DB 연결과 워커 생존(상태 파일의 마지막 실행)을 보고한다(TDD 7, ADR-027·050)
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import Clock, get_clock
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.worker.status import is_stale, read_state

router = APIRouter()


def _jobs(state: dict[str, Any]) -> dict[str, Any]:
    """작업별 마지막 실행 시각과 성공 여부만 보인다. 오류 내용·처리 대상은 담지 않는다."""
    return {
        name: {"lastRun": item.get("lastRun"), "ok": item.get("ok") is True}
        for name, item in state.items()
        if isinstance(item, dict)
    }


@router.get("/api/health", include_in_schema=False)
def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> JSONResponse:
    """DB에 닿고 워커가 5분 안에 일했고 마지막 실행이 모두 성공이면 200, 아니면 503이다. 인증 없이 부른다."""
    try:
        db.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    path = Path(settings.worker_status_file)
    jobs = _jobs(read_state(path))
    running = not is_stale(path, clock())
    healthy = database and running and all(job["ok"] for job in jobs.values())
    body = {
        "status": "ok" if healthy else "degraded",
        "database": database,
        "worker": {"running": running, "jobs": jobs},
    }
    return JSONResponse(body, status_code=200 if healthy else 503)
