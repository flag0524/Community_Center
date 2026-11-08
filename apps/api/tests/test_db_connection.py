# 개발용 MariaDB가 운영 기준(10.11, utf8mb4, UTC, InnoDB)대로 켜져 있는지 확인하는 시험
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.db


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def test_운영과_같은_10_11_계열이다(db_engine: Engine) -> None:
    version = str(scalar(db_engine, "SELECT VERSION()"))
    assert version.startswith("10.11."), version
    assert "MariaDB" in version


def test_문자셋과_정렬규칙은_utf8mb4이고_시각은_UTC다(db_engine: Engine) -> None:
    assert scalar(db_engine, "SELECT @@character_set_server") == "utf8mb4"
    assert scalar(db_engine, "SELECT @@collation_server") == "utf8mb4_unicode_ci"
    assert scalar(db_engine, "SELECT @@global.time_zone") == "+00:00"
    assert scalar(db_engine, "SELECT @@character_set_database") == "utf8mb4"


def test_기본_엔진은_InnoDB이고_엄격_모드다(db_engine: Engine) -> None:
    assert scalar(db_engine, "SELECT @@default_storage_engine") == "InnoDB"
    assert "STRICT_TRANS_TABLES" in str(scalar(db_engine, "SELECT @@sql_mode"))


def test_한글_저장이_깨지지_않고_NUMERIC_22가_문자열로_온다(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS tmp_b0_probe"))
        connection.execute(
            text("CREATE TABLE tmp_b0_probe (SN NUMERIC(22,0) NOT NULL PRIMARY KEY, NM VARCHAR(20) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO tmp_b0_probe VALUES (1234567890123456789012, '조리읍주민자치센터')")
        )
        row = connection.execute(text("SELECT SN, NM FROM tmp_b0_probe")).one()
        connection.execute(text("DROP TABLE tmp_b0_probe"))
    assert str(row[0]) == "1234567890123456789012"  # BIGINT로 줄이지 않는다(스키마 1.2)
    assert row[1] == "조리읍주민자치센터"
