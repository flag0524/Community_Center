# Alembic으로 적용한 실제 MariaDB를 다시 읽어 스키마 설계안과 대조하는 시험(테이블·컬럼·키·외래키·검사·시드)
import re

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.tools.schema_checks import narrative_checks
from app.tools.schema_ddl import filter_column, sequence_name, sql_type
from app.tools.schema_doc import SchemaDoc, parse_schema_doc

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


def rows(engine: Engine, sql: str) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql)).all()]


def test_문서의_45개_테이블이_정확히_만들어졌다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    names = {
        row[0]
        for row in rows(
            migrated_engine,
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'",
        )
    }
    assert names == {table.name for table in schema.tables} | {"alembic_version"}


def test_모든_테이블은_InnoDB_utf8mb4다(migrated_engine: Engine) -> None:
    found = rows(
        migrated_engine,
        "SELECT DISTINCT ENGINE, TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'TB\\_%'",
    )
    assert found == [("InnoDB", "utf8mb4_unicode_ci")]


def test_컬럼의_이름_타입_널여부가_문서와_같다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    actual = {
        (table, column): (ctype, nullable)
        for table, column, ctype, nullable in rows(
            migrated_engine,
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'TB\\_%'",
        )
    }
    expected: dict[tuple[str, str], tuple[str, str]] = {}
    for table in schema.tables:
        for column in table.columns:
            expected[(table.name, column.name)] = (
                sql_type(column.type).lower(),
                "NO" if column.required else "YES",
            )
        for index in table.indexes:
            if index.kind == "UQ_FILTER":
                expected[(table.name, filter_column(index))] = ("tinyint(4)", "YES")
    assert len(expected) == 610 + 2  # 문서 컬럼 610 + 조건부 UNIQUE용 생성 컬럼 2
    assert actual == expected


def test_일련번호는_22자리_십진수로_저장된다(migrated_engine: Engine) -> None:
    types = {
        row[0]
        for row in rows(
            migrated_engine,
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'ATNLC_APLY_SN'",
        )
    }
    assert types == {"decimal(22,0)"}


def test_기본키와_고유키와_인덱스가_문서의_컬럼_순서로_있다(
    migrated_engine: Engine, schema: SchemaDoc
) -> None:
    actual: dict[tuple[str, str], tuple[tuple[str, ...], bool]] = {}
    for table, name, unique, cols in rows(
        migrated_engine,
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'TB\\_%' GROUP BY TABLE_NAME, INDEX_NAME, NON_UNIQUE",
    ):
        actual[(str(table), str(name))] = (tuple(str(cols).split(",")), unique == 0)
    for table in schema.tables:
        for index in table.indexes:
            key = (table.name, "PRIMARY" if index.kind == "PK" else index.name)
            columns = (*index.columns, filter_column(index)) if index.kind == "UQ_FILTER" else index.columns
            assert key in actual, key
            assert actual[key] == (columns, index.kind != "IX"), key


def test_외래키_184개가_문서의_자식_부모_컬럼과_RESTRICT로_있다(
    migrated_engine: Engine, schema: SchemaDoc
) -> None:
    actual: dict[str, tuple[str, str, str, str, str]] = {}
    for table, name, parent, cols, parent_cols, delete_rule, update_rule in rows(
        migrated_engine,
        "SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.REFERENCED_TABLE_NAME, GROUP_CONCAT(k.COLUMN_NAME ORDER BY k.ORDINAL_POSITION), GROUP_CONCAT(k.REFERENCED_COLUMN_NAME ORDER BY k.ORDINAL_POSITION), r.DELETE_RULE, r.UPDATE_RULE FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA = DATABASE() AND k.REFERENCED_TABLE_NAME IS NOT NULL GROUP BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.REFERENCED_TABLE_NAME, r.DELETE_RULE, r.UPDATE_RULE",
    ):
        actual[str(name)] = (
            str(table),
            str(parent),
            str(cols),
            str(parent_cols),
            f"{delete_rule}/{update_rule}",
        )
    expected = {
        fk.name: (
            table.name,
            fk.parent_table,
            ",".join(fk.columns),
            ",".join(fk.parent_columns),
            "RESTRICT/RESTRICT",
        )
        for table in schema.tables
        for fk in table.foreign_keys
    }
    assert len(expected) == 184
    assert actual == expected


def test_검사_제약이_문서의_규칙_수만큼_있다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    names = [
        str(row[0])
        for row in rows(
            migrated_engine,
            "SELECT CONSTRAINT_NAME FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME LIKE 'CK\\_%'",
        )
    ]
    narrative = narrative_checks(schema)
    assert sum(name.startswith("CK_YN_") for name in names) == 18
    assert sum(name.startswith("CK_CD_") for name in names) == 36
    assert sorted(names) == sorted(
        [f"CK_{rule.rule_id.replace('-', '_')}" for rule in schema.checks]
        + [check.constraint for check in narrative]
    )
    assert len(names) == 54 + len(narrative)


def test_시퀀스는_단일_숫자_기본키_테이블마다_하나다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    names = {
        str(row[0])
        for row in rows(
            migrated_engine,
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'SEQUENCE'",
        )
    }
    assert names == {name for name in (sequence_name(table) for table in schema.tables) if name}


def test_공통코드_시드가_문서와_같다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    actual = {
        (str(c), str(g), str(n))
        for c, g, n in rows(migrated_engine, "SELECT COM_CD, CD_GROUP_ID, CD_NM FROM TB_COM_CD")
    }
    assert actual == {(code.code, code.group, code.label) for code in schema.codes}
    assert len({group for _, group, _ in actual}) == 40
    assert re.fullmatch(r"\d+", str(rows(migrated_engine, "SELECT COUNT(*) FROM TB_COM_CD")[0][0]))


def test_마이그레이션_버전은_0001이다(migrated_engine: Engine) -> None:
    assert rows(migrated_engine, "SELECT version_num FROM alembic_version") == [("0001",)]


def test_되돌리면_테이블과_시퀀스가_모두_사라지고_다시_올릴_수_있다(migrated_engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    from tests.conftest import API_DIR

    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    left = "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME <> 'alembic_version'"
    with migrated_engine.connect() as connection:
        config.attributes["connection"] = connection
        try:
            command.downgrade(config, "base")
            connection.commit()
            assert connection.execute(text(left)).scalar_one() == 0
        finally:
            command.upgrade(config, "head")  # 다른 시험을 위해 반드시 다시 올려 둔다
            connection.commit()
        assert connection.execute(text(left)).scalar_one() == 45 + 41  # 테이블 45 + 시퀀스 41
