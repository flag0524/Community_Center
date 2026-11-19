# 고정된 0001 마이그레이션이 바뀌지 않고 이후 변경이 추가 마이그레이션으로 제공되는지 확인한다
import hashlib
import io

import pytest
from alembic import command
from alembic.config import Config

from app.tools.generate_ddl import MIGRATIONS
from tests.conftest import API_DIR


@pytest.mark.parametrize(
    ("name", "digest"),
    [
        ("up", "661dc788686885ffe85a4c93704f4a78699259ce7bacee129d8af8bbc1fa9606"),
        ("down", "9b097fd7538227f63654319cbe450f0fe59ff60ba516d15824045038baaeb5db"),
    ],
)
def test_기존_0001_SQL을_덮어쓰지_않는다(name: str, digest: str) -> None:
    assert hashlib.sha256((MIGRATIONS / f"0001_initial_schema.{name}.sql").read_bytes()).hexdigest() == digest


def test_0002는_DB에_접속하지_않고_데이터를_유지하는_추가_SQL로_나온다() -> None:
    output = io.StringIO()
    config = Config(str(API_DIR / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(config, "0001:head", sql=True)
    sql = output.getvalue()
    assert "ALTER TABLE `TB_CERT_DMND` ADD COLUMN `TELNO_SRCH_HASH_VL` CHAR(64)" in sql
    assert "IX_CERT_DMND_03" in sql and "OPER_BNDL_SN" in sql and "REG_DT" in sql
    assert "DROP TABLE" not in sql and "DELETE FROM" not in sql and "CREATE TABLE" not in sql


def test_0002를_되돌려도_기존_테이블과_데이터는_지우지_않는다() -> None:
    output = io.StringIO()
    config = Config(str(API_DIR / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    command.downgrade(config, "0002:0001", sql=True)
    sql = output.getvalue()
    assert "DROP INDEX `IX_CERT_DMND_03`" in sql and "DROP COLUMN `TELNO_SRCH_HASH_VL`" in sql
    assert "DROP TABLE" not in sql and "DELETE FROM" not in sql
