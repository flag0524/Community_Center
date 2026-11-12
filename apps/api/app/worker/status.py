# 작업별 마지막 실행 시각·결과를 상태 파일에 남기고, 정지 여부를 읽는다. 생존 감시는 DB 밖에서 한다(TDD 7, ADR-027)
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

STALE_AFTER = timedelta(minutes=5)  # 5분 넘게 아무 작업도 돌지 않으면 정지로 본다


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
    state = _read(path)
    state[job] = {
        "lastRun": now.replace(tzinfo=UTC).isoformat(),
        "ok": ok,
        "error": error,
        "handled": handled,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def is_stale(path: Path, now: datetime, max_age: timedelta = STALE_AFTER) -> bool:
    """상태 파일이 없거나 모든 작업의 마지막 실행이 오래됐으면 참이다."""
    state = _read(path)
    runs = [
        datetime.fromisoformat(item["lastRun"])
        for item in state.values()
        if isinstance(item, dict) and "lastRun" in item
    ]
    if not runs:
        return True
    return now.replace(tzinfo=UTC) - max(runs) > max_age


def read_state(path: Path) -> dict[str, Any]:
    """작업별 마지막 실행 상태. 파일이 없거나 깨졌으면 빈 값이다."""
    return _read(path)
