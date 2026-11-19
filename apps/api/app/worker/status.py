# 작업별 마지막 실행 시각·결과를 상태 파일에 남기고, 정지 여부를 읽는다. 생존 감시는 DB 밖에서 한다(TDD 7, ADR-027)
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from app.worker.schedule import DAILY_HOURS, INTERVAL_SECONDS, next_daily_run

STALE_AFTER = timedelta(minutes=5)  # 5분 넘게 아무 작업도 돌지 않으면 정지로 본다
_WRITE_LOCK = Lock()  # 단일 워커 프로세스 안에서 서로 다른 작업의 파일 갱신을 직렬화한다(ADR-004)


def _write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def initialize_status(path: Path, now: datetime) -> None:
    """재기동 전 기록을 버리고 시작 시각을 남긴다. 일일 작업은 첫 예약 시각까지 기다린다."""
    with _WRITE_LOCK:
        _write(path, {"_worker": {"startedAt": now.replace(tzinfo=UTC).isoformat()}})


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_run(
    path: Path, job: str, *, ok: bool, now: datetime, error: str | None = None, handled: int | None = None
) -> None:
    """작업 한 번의 결과를 덮어쓴다. 임시 파일에 쓴 뒤 바꿔 읽는 쪽이 반쯤 쓴 파일을 보지 않게 한다."""
    with _WRITE_LOCK:
        state = _read(path)
        state[job] = {
            "lastRun": now.replace(tzinfo=UTC).isoformat(),
            "ok": ok,
            "error": error,
            "handled": handled,
        }
        _write(path, state)


def _moment(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def jobs_healthy(state: dict[str, Any], now: datetime) -> bool:
    """주기 작업은 누락·실패·지연을, 일일 작업은 다음 예약 시각을 넘겼는지 검사한다."""
    current = now.replace(tzinfo=UTC)
    for name, seconds in INTERVAL_SECONDS.items():
        row = state.get(name)
        if not isinstance(row, dict) or row.get("ok") is not True:
            return False
        ran = _moment(row.get("lastRun"))
        if ran is None:
            return False
        if not timedelta(0) <= current - ran <= max(STALE_AFTER, timedelta(seconds=seconds * 3)):
            return False
    worker = state.get("_worker")
    started = _moment(worker.get("startedAt")) if isinstance(worker, dict) else None
    for name, hour in DAILY_HOURS.items():
        row = state.get(name)
        if row is None:
            base = started  # 실행한 척하지 않고, 첫 예약 시각까지만 미실행을 허용한다
        else:
            if not isinstance(row, dict) or row.get("ok") is not True:
                return False
            base = _moment(row.get("lastRun"))
        if base is None or base > current or current > next_daily_run(base, hour) + STALE_AFTER:
            return False
    return True


def is_stale(path: Path, now: datetime, max_age: timedelta = STALE_AFTER) -> bool:
    """상태 파일이 없거나 모든 작업의 마지막 실행이 오래됐으면 참이다."""
    state = _read(path)
    runs = [
        ran
        for item in state.values()
        if isinstance(item, dict) and (ran := _moment(item.get("lastRun"))) is not None
    ]
    if not runs:
        return True
    return now.replace(tzinfo=UTC) - max(runs) > max_age


def read_state(path: Path) -> dict[str, Any]:
    """작업별 마지막 실행 상태. 파일이 없거나 깨졌으면 빈 값이다."""
    return _read(path)
