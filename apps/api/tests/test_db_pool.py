# DB 커넥션 풀 설정과 배포 설정(uvicorn 워커 수·MariaDB 최대 연결)의 숫자가 맞는지 확인하는 시험
import re
from pathlib import Path

import pytest

from app.core.config import ConfigError, Settings, load_settings
from app.db.session import create_db_engine

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
BASE = {
    "JORI_DATABASE_URL": "mysql+pymysql://u:p@127.0.0.1:3306/x",
    "JORI_SITE_ID": "t",
    "JORI_SECRET_KEY": "k" * 40,
}


def engine_pool(size: int = 10, overflow: int = 10, timeout: int = 10) -> tuple[int, int, float]:
    settings = Settings(
        database_url=BASE["JORI_DATABASE_URL"],
        site_id="t",
        db_pool_size=size,
        db_max_overflow=overflow,
        db_pool_timeout=timeout,
    )
    engine = create_db_engine(settings)
    pool = engine.pool
    return pool.size(), pool._max_overflow, pool.timeout()  # type: ignore[attr-defined]


def test_풀_크기는_기본값이_명시돼_있다() -> None:
    assert engine_pool() == (10, 10, 10)


def test_풀_크기는_설정값을_따른다() -> None:
    assert engine_pool(3, 1, 7) == (3, 1, 7)


def test_환경변수로_풀_크기를_바꾼다() -> None:
    settings = load_settings(
        {**BASE, "JORI_DB_POOL_SIZE": "6", "JORI_DB_MAX_OVERFLOW": "2", "JORI_DB_POOL_TIMEOUT": "5"}
    )
    assert (settings.db_pool_size, settings.db_max_overflow, settings.db_pool_timeout) == (6, 2, 5)
    default = load_settings(BASE)
    assert (default.db_pool_size, default.db_max_overflow, default.db_pool_timeout) == (10, 10, 10)


@pytest.mark.parametrize(
    "name,value", [("JORI_DB_POOL_SIZE", "0"), ("JORI_DB_POOL_SIZE", "-1"), ("JORI_DB_POOL_TIMEOUT", "0")]
)
def test_풀_크기와_대기시간은_양수여야_한다(name: str, value: str) -> None:
    with pytest.raises(ConfigError):
        load_settings({**BASE, name: value})


def test_풀_초과_허용은_0이_될_수_있고_음수는_거절한다() -> None:
    assert load_settings({**BASE, "JORI_DB_MAX_OVERFLOW": "0"}).db_max_overflow == 0
    with pytest.raises(ConfigError):
        load_settings({**BASE, "JORI_DB_MAX_OVERFLOW": "-1"})


def _env_example() -> dict[str, str]:
    values = {}
    for line in (DEPLOY / "env/jori.env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_예시_설정이_풀_크기를_명시하고_MariaDB_최대_연결_안에_들어온다() -> None:
    env = _env_example()
    settings = load_settings({**env, "JORI_SECRET_KEY": "k" * 40})
    per_process = settings.db_pool_size + settings.db_max_overflow
    # API 프로세스 여럿과 워커 프로세스 하나가 각자 풀을 갖는다. 관리·백업 접속 여유 20을 더한다
    needed = per_process * (int(env["JORI_API_WORKERS"]) + 1) + 20
    cnf = (DEPLOY / "mariadb/jori.cnf").read_text(encoding="utf-8")
    maximum = int(re.search(r"^max_connections\s*=\s*(\d+)$", cnf, re.M).group(1))  # type: ignore[union-attr]
    assert maximum >= needed, f"풀 총합 {needed}이 max_connections {maximum}를 넘는다"
    assert re.search(r"^innodb_buffer_pool_size\s*=\s*\d+[MG]$", cnf, re.M)
