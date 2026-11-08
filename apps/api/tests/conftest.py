# 실제 MariaDB가 필요한 시험의 접속 설정과 fixture. DB가 없으면 건너뛰고 JORI_REQUIRE_DB=1이면 실패한다
import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

DEFAULT_CREDENTIALS = Path.home() / "dev-tools" / "mariadb-credentials.json"


def database_url(database: str = "jori_test") -> URL:
    """JORI_TEST_DATABASE_URL이 있으면 그것을, 없으면 개발용 이식형 MariaDB의 비밀번호 파일을 쓴다."""
    explicit = os.environ.get("JORI_TEST_DATABASE_URL")
    if explicit:
        return make_url(explicit)
    path = Path(os.environ.get("JORI_CREDENTIALS_FILE", str(DEFAULT_CREDENTIALS)))
    credentials = json.loads(path.read_text(encoding="utf-8-sig"))
    return URL.create(
        "mysql+pymysql",
        username=credentials["appUser"],
        password=credentials["appPassword"],
        host="127.0.0.1",
        port=credentials["port"],
        database=database,
        query={"charset": "utf8mb4"},
    )


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """시험 전용 DB(jori_test)에 연결한다. 연결할 수 없으면 건너뛰거나 실패시킨다."""
    try:
        engine = create_engine(database_url(), pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        if os.environ.get("JORI_REQUIRE_DB") == "1":
            raise
        pytest.skip(f"MariaDB에 연결할 수 없습니다(scripts/db/mariadb-dev.ps1 start): {type(error).__name__}")
    yield engine
    engine.dispose()


API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_engine(db_engine: Engine) -> Iterator[Engine]:
    """시험 DB를 비운 뒤 Alembic으로 최신 버전까지 올린다. 구조 시험은 모두 이 DB를 읽는다."""
    from alembic import command
    from alembic.config import Config

    with db_engine.connect() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        # MariaDB는 시퀀스를 information_schema.TABLES에 TABLE_TYPE=SEQUENCE로 보여 준다
        for name, kind in connection.execute(
            text(
                "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
            )
        ).all():
            drop = "SEQUENCE" if kind == "SEQUENCE" else "TABLE"
            connection.execute(text(f"DROP {drop} IF EXISTS `{name}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        connection.commit()
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    with db_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    yield db_engine
