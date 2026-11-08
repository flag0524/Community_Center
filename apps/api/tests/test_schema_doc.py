# 설계안 파서가 문서의 숫자(45·610·184·코드 182값)와 일치하고 문서 안의 참조가 맞는지 보는 시험
from collections import Counter

import pytest

from app.tools.schema_doc import SchemaDoc, parse_schema_doc, validate


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


def test_문서의_총계와_일치한다(schema: SchemaDoc) -> None:
    assert len(schema.tables) == 45
    assert sum(len(table.columns) for table in schema.tables) == 610
    assert sum(len(table.foreign_keys) for table in schema.tables) == 184
    assert len(schema.listed_tables) == 45
    assert {name for name, _ in schema.listed_tables} == {table.name for table in schema.tables}


def test_키와_인덱스_종류별_개수(schema: SchemaDoc) -> None:
    kinds = Counter(index.kind for table in schema.tables for index in table.indexes)
    assert kinds == {"PK": 45, "UQ": 78, "IX": 103, "UQ_FILTER": 2}


def test_공통코드는_40집합_182값이고_12자_안이다(schema: SchemaDoc) -> None:
    assert len(schema.codes) == 182
    assert len({code.group for code in schema.codes}) == 40
    assert max(len(code.code) for code in schema.codes) <= 12  # TB_COM_CD.COM_CD는 CHAR(12)
    assert len({code.code for code in schema.codes}) == 182
    assert all(code.code.startswith(f"{code.group}.") for code in schema.codes)


def test_Y_N과_코드접두부_규칙을_읽었다(schema: SchemaDoc) -> None:
    assert Counter(check.kind for check in schema.checks) == {"YN": 18, "CD": 36}


def test_문서_안의_참조와_타입이_일관적이다(schema: SchemaDoc) -> None:
    assert validate(schema) == []


def test_조건부_고유키는_둘이고_조건을_담는다(schema: SchemaDoc) -> None:
    filters = {
        index.name: index.condition
        for table in schema.tables
        for index in table.indexes
        if index.kind == "UQ_FILTER"
    }
    assert filters == {
        "UQ_FILTER_ATNLC_APLY_01": "APLY_STTS_CD IN ('ES.WAIT','ES.HOLD','ES.CONFIRM')",
        "UQ_FILTER_STLM_01": "STLM_STTS_CD = 'PS.PAID'",
    }


def test_모든_외래키는_RESTRICT다(schema: SchemaDoc) -> None:
    pairs = {(fk.on_delete, fk.on_update) for table in schema.tables for fk in table.foreign_keys}
    assert pairs == {("RESTRICT", "RESTRICT")}
