# DB 없이 워커 오류 로그의 개인정보 차단과 상태 파일 동시 기록을 검증한다
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import StatementError

from app.worker.runner import Job, run_guarded
from app.worker.status import read_state, record_run

NOW = datetime(2026, 11, 19, 6)


def test_워커_DB_오류_로그에는_SQL과_입력값과_예외_전문이_없다(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(_: Any) -> int:
        raise StatementError(
            "AUDIT-ERROR-TEXT",
            "INSERT INTO PRIVATE_PHONE VALUES (:phone)",
            {"phone": "AUDIT-PRIVATE-PHONE"},
            ValueError("AUDIT-INNER-ERROR"),
        )

    with caplog.at_level(logging.ERROR, logger="app.worker"):
        run_guarded(Job("audit", 10, fail), create_engine("sqlite://"), tmp_path / "s.json", lambda: NOW)
    assert "StatementError" in caplog.text
    for secret in ("PRIVATE_PHONE", "AUDIT-PRIVATE-PHONE", "AUDIT-ERROR-TEXT", "AUDIT-INNER-ERROR"):
        assert secret not in caplog.text
    assert read_state(tmp_path / "s.json")["audit"]["ok"] is False


def test_두_작업이_겹쳐_상태를_써도_모든_결과가_남는다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "status.json"
    entered, release = Event(), Event()
    gate = Lock()
    first = True
    original = Path.write_text

    def delayed_write(target: Path, *args: Any, **kwargs: Any) -> int:
        nonlocal first
        with gate:
            delay, first = first, False
        if delay:
            entered.set()
            assert release.wait(5)
        return original(target, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", delayed_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(record_run, path, "sms_dispatch", ok=True, now=NOW)
        assert entered.wait(5)
        two = pool.submit(record_run, path, "file_scan", ok=False, now=NOW, error="TimeoutError")
        try:
            two.result(timeout=0.1)
        except TimeoutError:
            pass
        finally:
            release.set()
        one.result(timeout=5)
        two.result(timeout=5)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert set(state) == {"sms_dispatch", "file_scan"}
    assert state["sms_dispatch"]["ok"] is True and state["file_scan"]["ok"] is False
