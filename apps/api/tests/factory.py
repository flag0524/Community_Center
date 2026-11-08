# 시험용 행 생성 도구. 외래키 사슬을 따라 부모 행을 먼저 만들고 남은 필수 컬럼을 타입에 맞는 값으로 채운다
import itertools
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.tools.schema_ddl import sequence_name
from app.tools.schema_doc import Column, SchemaDoc, Table

BUNDLE = "OPER_BNDL_SN"


class RowFactory:
    """한 연결(시험 트랜잭션) 안에서 행을 만든다. 같은 factory가 만드는 행은 기본으로 한 운영묶음에 속한다."""

    def __init__(self, connection: Connection, schema: SchemaDoc) -> None:
        self.connection = connection
        self.schema = schema
        self.counter = itertools.count(1)
        self.groups = {code.group for code in schema.codes}
        self.first_code: dict[str, str] = {}
        for code in schema.codes:
            self.first_code.setdefault(code.group, code.code)
        self.yn_columns = {(check.table, check.column) for check in schema.checks if check.kind == "YN"}
        self._bundle: int | None = None

    def bundle(self) -> int:
        if self._bundle is None:
            self._bundle = int(self.make("TB_OPER_BNDL")[BUNDLE])
        return self._bundle

    def make(self, table_name: str, **values: Any) -> dict[str, Any]:
        return self._make(table_name, dict(values), ())

    def _make(self, table_name: str, provided: dict[str, Any], stack: tuple[str, ...]) -> dict[str, Any]:
        if table_name in stack and table_name != "TB_OPER_BNDL":
            raise RuntimeError(f"필수 외래키가 순환한다: {' > '.join((*stack, table_name))}")
        table = self.schema.table(table_name)
        names = {column.name for column in table.columns}
        if BUNDLE in names and BUNDLE not in provided and table_name != "TB_OPER_BNDL":
            provided[BUNDLE] = self.bundle()
        for fk in table.foreign_keys:
            if fk.parent_table == "TB_COM_CD" or fk.parent_table == table_name:
                continue
            given = [column in provided for column in fk.columns]
            if all(given) or (fk.nullable and not any(given)):
                continue
            parent_values = {
                parent: provided[child]
                for child, parent in zip(fk.columns, fk.parent_columns, strict=True)
                if child in provided
            }
            parent = self._make(fk.parent_table, parent_values, (*stack, table_name))
            for child, parent_column in zip(fk.columns, fk.parent_columns, strict=True):
                provided.setdefault(child, parent[parent_column])
        sequence = sequence_name(table)
        unique = {
            name
            for index in table.indexes
            if index.kind in ("PK", "UQ", "UQ_FILTER")
            for name in index.columns
        }
        for column in table.columns:
            if column.name in provided or not column.required or column.default is not None:
                continue
            if sequence and column.name == table.primary_key.columns[0]:
                continue
            provided[column.name] = self._value(table, column, column.name in unique)
        names_sql = ", ".join(provided)
        marks = ", ".join(f":{name}" for name in provided)
        self.connection.execute(text(f"INSERT INTO {table_name} ({names_sql}) VALUES ({marks})"), provided)
        return self._fetch(table, provided, sequence)

    def _value(self, table: Table, column: Column, unique: bool) -> Any:
        kind = column.type
        if kind.startswith("NUMERIC"):
            if not unique:
                return 1
            precision, scale = (int(part) for part in kind[kind.index("(") + 1 : -1].split(","))
            return (
                next(self.counter) % (10 ** (precision - scale) - 1) + 1
            )  # 자릿수가 작은 컬럼도 범위를 넘지 않게 돌려 쓴다
        if kind == "DATETIME":
            return "2026-01-01 00:00:00"
        if kind == "CLOB":
            return "x"
        length = int(kind[kind.index("(") + 1 : -1])
        for token in (part.strip() for part in column.key_flags.split("/")):
            if token in self.groups:
                return self.first_code[token]
        if (table.name, column.name) in self.yn_columns or column.domain.startswith("여부"):
            return "Y"
        if column.name.endswith("_YMD"):
            return "20260101"
        if column.name.endswith("_TM"):
            return "090000"
        return f"{column.name[:8]}{next(self.counter)}"[:length]

    def _fetch(self, table: Table, provided: dict[str, Any], sequence: str | None) -> dict[str, Any]:
        columns = ", ".join(column.name for column in table.columns)
        key = table.primary_key.columns
        if sequence and key[0] not in provided:
            provided[key[0]] = self.connection.execute(text(f"SELECT LASTVAL({sequence})")).scalar_one()
        where = " AND ".join(f"{name} = :{name}" for name in key)
        row = (
            self.connection.execute(
                text(f"SELECT {columns} FROM {table.name} WHERE {where}"),
                {name: provided[name] for name in key},
            )
            .mappings()
            .one()
        )
        return {name: (int(value) if isinstance(value, Decimal) else value) for name, value in row.items()}
