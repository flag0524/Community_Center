# 설계안에서 만든 DDL이 항목을 빠짐없이 담고 MariaDB가 막는 식을 안 쓰는지, 변조를 검증이 잡는지 보는 시험
import dataclasses
import re

import pytest

from app.tools.schema_checks import narrative_checks
from app.tools.schema_ddl import (
    condition_expression,
    down_statements,
    identifier_problems,
    sequence_name,
    sql_type,
    up_statements,
)
from app.tools.schema_doc import ForeignKey, SchemaDoc, Table, parse_schema_doc, validate


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


@pytest.fixture(scope="module")
def statements(schema: SchemaDoc) -> list[str]:
    return up_statements(schema)


def test_문서의_모든_테이블과_외래키와_검사가_DDL에_나온다(schema: SchemaDoc, statements: list[str]) -> None:
    creates = [s for s in statements if s.startswith("CREATE TABLE")]
    foreign_keys = [s for s in statements if "FOREIGN KEY" in s]
    checks = [s for s in statements if " CHECK (" in s]
    assert len(creates) == 45
    assert len(foreign_keys) == 184
    assert len(checks) == 54 + len(narrative_checks(schema))  # Y/N 18 + 코드 접두부 36 + 서술형·R27
    assert len([s for s in statements if s.startswith("INSERT INTO TB_COM_CD")]) == 1


def test_모든_컬럼과_키가_빠짐없이_나온다(schema: SchemaDoc, statements: list[str]) -> None:
    by_name: dict[str, str] = {}
    for statement in statements:
        match = re.match(r"CREATE TABLE (\w+)", statement)
        if match:
            by_name[match[1]] = statement
    for table in schema.tables:
        sql = by_name[table.name]
        for column in table.columns:
            assert re.search(rf"^  {column.name} ", sql, re.MULTILINE), f"{table.name}.{column.name}"
        for index in table.indexes:
            if index.kind != "PK":
                assert f" {index.name} (" in sql, f"{table.name}.{index.name}"
        assert "PRIMARY KEY (" in sql


def test_일련번호는_단일_숫자_기본키에만_시퀀스를_둔다(schema: SchemaDoc, statements: list[str]) -> None:
    sequences = [s for s in statements if s.startswith("CREATE SEQUENCE")]
    singles = [t for t in schema.tables if sequence_name(t)]
    assert len(sequences) == len(singles)
    assert "SQ_COM_CD" not in " ".join(sequences)  # 코드 기본키는 문자열이라 시퀀스가 없다
    apply = next(s for s in statements if s.startswith("CREATE TABLE TB_ATNLC_APLY"))
    assert "ATNLC_APLY_SN DECIMAL(22,0) NOT NULL DEFAULT NEXTVAL(SQ_ATNLC_APLY)" in apply


def test_일련번호_22자리를_BIGINT로_줄이지_않는다(statements: list[str]) -> None:
    assert not any(" BIGINT" in s or " INT " in s for s in statements if s.startswith("CREATE TABLE"))
    assert sql_type("NUMERIC(22,0)") == "DECIMAL(22,0)"
    assert sql_type("CLOB") == "LONGTEXT"


def test_조건부_UNIQUE는_IN_없이_OR로_푼_생성_컬럼이다(statements: list[str]) -> None:
    apply = next(s for s in statements if s.startswith("CREATE TABLE TB_ATNLC_APLY"))
    assert (
        "ZF_ATNLC_APLY_01 TINYINT AS (CASE WHEN APLY_STTS_CD='ES.WAIT' OR APLY_STTS_CD='ES.HOLD' "
        "OR APLY_STTS_CD='ES.CONFIRM' THEN 1 END) PERSISTENT" in apply
    )
    assert "UNIQUE KEY UQ_FILTER_ATNLC_APLY_01 (OPER_BNDL_SN, CORS_SN, MBR_SN, ZF_ATNLC_APLY_01)" in apply
    assert condition_expression("STLM_STTS_CD = 'PS.PAID'") == "STLM_STTS_CD='PS.PAID'"
    assert not any(re.search(r" AS \(.* IN \(", s) for s in statements)  # MariaDB는 생성 컬럼의 IN을 막는다
    with pytest.raises(ValueError):
        condition_expression("A > 1")


def test_외래키는_테이블을_모두_만든_뒤에_붙이고_순환을_피한다(statements: list[str]) -> None:
    first_alter = next(i for i, s in enumerate(statements) if s.startswith("ALTER TABLE"))
    last_create = max(i for i, s in enumerate(statements) if s.startswith("CREATE TABLE"))
    assert last_create < first_alter
    assert "SELECT" not in "".join(statements[: last_create + 1])


def test_기본값은_타입에_맞게_쓴다(statements: list[str]) -> None:
    apply = next(s for s in statements if s.startswith("CREATE TABLE TB_ATNLC_APLY"))
    assert re.search(r"REG_DT DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP", apply)
    assert re.search(r"RCRD_VER DECIMAL\(10,0\) NOT NULL DEFAULT 1 ", apply)
    assert re.search(r"MDFCN_DT DATETIME NULL DEFAULT NULL", apply)
    member = next(s for s in statements if s.startswith("CREATE TABLE TB_MBR "))
    assert re.search(r"MBR_STTS_CD CHAR\(12\) NOT NULL DEFAULT 'MS.ACTIVE'", member)


def test_공통코드_시드는_182행이고_따옴표를_안전하게_다룬다(statements: list[str]) -> None:
    seed = next(s for s in statements if s.startswith("INSERT INTO TB_COM_CD"))
    assert seed.count("\n  (") == 182
    assert "('MT.GEN', 'MT', '일반회원', 1)" in seed


def test_식별자는_64자_이내이고_이름이_겹치지_않는다(schema: SchemaDoc) -> None:
    assert identifier_problems(schema) == []


def test_되돌리기는_테이블과_시퀀스를_모두_지운다(schema: SchemaDoc) -> None:
    down = down_statements(schema)
    assert down[0] == "SET FOREIGN_KEY_CHECKS=0" and down[-1] == "SET FOREIGN_KEY_CHECKS=1"
    assert len([s for s in down if s.startswith("DROP TABLE")]) == 45
    assert len([s for s in down if s.startswith("DROP SEQUENCE")]) == len(
        [t for t in schema.tables if sequence_name(t)]
    )


def test_검증은_문서를_변조하면_실제로_잡는다(schema: SchemaDoc) -> None:
    first = schema.tables[0]
    broken_count = dataclasses.replace(first, declared_columns=first.declared_columns + 1)
    assert any(
        "컬럼" in problem
        for problem in validate(dataclasses.replace(schema, tables=(broken_count, *schema.tables[1:])))
    )

    target = next(t for t in schema.tables if t.foreign_keys)
    bad_fk = dataclasses.replace(
        target.foreign_keys[0], parent_columns=("NO_SUCH_COLUMN",) * len(target.foreign_keys[0].columns)
    )
    tampered: Table = dataclasses.replace(target, foreign_keys=(bad_fk, *target.foreign_keys[1:]))
    tables = tuple(tampered if t.name == target.name else t for t in schema.tables)
    assert any("없는 컬럼" in problem for problem in validate(dataclasses.replace(schema, tables=tables)))

    wrong_parent = ForeignKey(
        "FK_X", ("OPER_BNDL_SN",), "TB_NOPE", ("OPER_BNDL_SN",), False, "RESTRICT", "RESTRICT"
    )
    tampered = dataclasses.replace(target, foreign_keys=(wrong_parent,))
    tables = tuple(tampered if t.name == target.name else t for t in schema.tables)
    assert any("없는 부모" in problem for problem in validate(dataclasses.replace(schema, tables=tables)))
