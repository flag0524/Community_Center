# DB와 소켓 없이 작업 누락·지연·실패와 일일 작업의 첫 예약 유예를 건강 응답으로 검증한다
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.routers.health import health
from app.worker.schedule import INTERVAL_SECONDS
from app.worker.status import initialize_status, read_state, record_run

NOW = datetime(2026, 11, 19, 6)


class Connected:
    def execute(self, *_: Any) -> None:
        pass


def fresh(path: Path, now: datetime) -> None:
    for name in INTERVAL_SECONDS:
        record_run(path, name, ok=True, now=now)


def probe(path: Path, now: datetime) -> int:
    db: Any = Connected()
    settings = Settings(database_url="unused", site_id="test", worker_status_file=str(path))
    return health(db, settings, lambda: now).status_code


def test_모든_주기_작업이_성공하면_첫_일일_예약_전에는_정상이다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    initialize_status(path, NOW)
    fresh(path, NOW)
    assert probe(path, NOW) == 200


@pytest.mark.parametrize("name", list(INTERVAL_SECONDS))
def test_다른_작업이_정상이어도_한_작업의_정지를_감지한다(tmp_path: Path, name: str) -> None:
    path = tmp_path / "s.json"
    initialize_status(path, NOW)
    fresh(path, NOW)
    record_run(path, name, ok=True, now=NOW - timedelta(days=2))
    assert probe(path, NOW) == 503


def test_실행_기록이_빠진_작업과_실패한_작업을_거절한다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    initialize_status(path, NOW)
    for name in INTERVAL_SECONDS:
        if name != "file_scan":
            record_run(path, name, ok=True, now=NOW)
    assert probe(path, NOW) == 503
    record_run(path, "file_scan", ok=False, now=NOW, error="TimeoutError")
    assert probe(path, NOW) == 503


def test_일일_작업은_첫_예약_후_5분까지만_미실행을_허용한다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    started = datetime(2026, 11, 18, 17)  # 한국 시각 02:00, 정합성 점검 첫 예약은 03:00이다
    initialize_status(path, started)
    due = started + timedelta(hours=1, minutes=5)
    fresh(path, due)
    assert probe(path, due) == 200
    assert probe(path, due + timedelta(seconds=1)) == 503
    record_run(path, "consistency_check", ok=True, now=due)
    assert probe(path, due + timedelta(seconds=1)) == 200


def test_일일_파기가_누락되면_다른_작업이_정상이어도_감지한다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    started = datetime(2026, 11, 18, 18, 30)  # 한국 시각 03:30
    initialize_status(path, started)
    missed = datetime(2026, 11, 18, 19, 5, 1)  # 한국 시각 04:05:01
    fresh(path, missed)
    assert probe(path, missed) == 503


def test_시각_형식이_깨져도_500_대신_503이다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text('{"sms_dispatch":{"lastRun":"broken","ok":true}}', encoding="utf-8")
    assert probe(path, NOW) == 503


def test_재시작은_이전_프로세스의_작업_성공을_이어받지_않는다(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    record_run(path, "expire_payments", ok=True, now=NOW)
    initialize_status(path, NOW)
    assert set(read_state(path)) == {"_worker"}
    assert probe(path, NOW) == 503
