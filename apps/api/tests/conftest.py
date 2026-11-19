# 실제 MariaDB가 필요한 시험의 접속 설정과 fixture. DB가 없으면 건너뛰고 JORI_REQUIRE_DB=1이면 실패한다
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

DEFAULT_CREDENTIALS = Path.home() / "dev-tools" / "mariadb-credentials.json"


def assert_test_database(url: URL, *, actual_name: str | None = None) -> None:
    """시험 DB만 초기화하며 앱이 쓰는 DB와 같은 연결 대상이면 시험 이름이어도 거절한다."""
    if url.database != "jori_test" or (actual_name is not None and actual_name != "jori_test"):
        raise pytest.UsageError("시험은 jori_test DB에서만 실행할 수 있습니다. 초기화를 거부합니다.")
    app_url = os.environ.get("JORI_DATABASE_URL")
    if app_url:
        app = make_url(app_url)
        local = {"localhost", "127.0.0.1", "::1"}
        app_host, test_host = (app.host or "").lower(), (url.host or "").lower()
        if ("localhost" if app_host in local else app_host, app.port or 3306, app.database) == (
            "localhost" if test_host in local else test_host,
            url.port or 3306,
            url.database,
        ):
            raise pytest.UsageError("앱과 같은 DB에서는 시험할 수 없습니다. 초기화를 거부합니다.")


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
        url = database_url()
        assert_test_database(url)
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as connection:
            assert_test_database(url, actual_name=str(connection.execute(text("SELECT DATABASE()")).scalar()))
    except (OSError, SQLAlchemyError) as error:
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
        assert_test_database(
            db_engine.url, actual_name=str(connection.execute(text("SELECT DATABASE()")).scalar())
        )
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


@pytest.fixture(scope="session")
def schema_doc() -> object:
    from app.tools.schema_doc import parse_schema_doc

    return parse_schema_doc()


@pytest.fixture()
def world(migrated_engine: Engine, schema_doc: Any) -> Iterator[Any]:
    """인증·OTP 시험의 세계. 실제 앱을 시험 트랜잭션·가짜 시계·모의 문자 발송기로 돌린다."""
    from tests.world import build_world

    yield from build_world(migrated_engine, schema_doc)


@pytest.fixture()
def arena(migrated_engine: Engine, schema_doc: Any) -> Iterator[Any]:
    """동시성 시험의 마당. 커밋되는 데이터와 요청마다 따로 연 DB 연결로 실제 앱을 돌린다."""
    from tests.arena import build_arena

    yield from build_arena(migrated_engine, schema_doc)


@pytest.fixture(params=["READ COMMITTED", "REPEATABLE READ"])
def otp_arena(arena: Any, request: pytest.FixtureRequest) -> Iterator[Any]:
    """OTP 경합은 두 격리 수준을 실제 연결에서 확인하고 각각 실행한다."""
    previous = arena.engine
    arena.engine = previous.execution_options(isolation_level=str(request.param))
    try:
        with arena.engine.connect() as connection:
            assert connection.get_isolation_level() == request.param
        yield arena
    finally:
        arena.engine = previous  # 풀은 공유한다. 원본 엔진의 정리는 arena가 맡는다.
