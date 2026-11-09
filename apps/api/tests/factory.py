# 시험용 행 생성 도구. 외래키 사슬을 따라 부모 행을 먼저 만들고 남은 필수 컬럼을 타입에 맞는 값으로 채운다
import itertools
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.tools.schema_ddl import sequence_name
from app.tools.schema_doc import Column, SchemaDoc, Table

BUNDLE = "OPER_BNDL_SN"

# 서술형 DB 검사(R05·R08·R09·R21 등)를 만족하는 표 별 기본값. 시험이 같은 컬럼을 넘기면 그 값이 우선한다.
PRESETS: dict[str, dict[str, Any]] = {
    "TB_EDU_CYCL": {"RCPT_END_DT": "2026-02-01 00:00:00"},
    "TB_CORS_SCHDL": {"END_TM": "100000"},
    "TB_ATNLC_APLY": {"RDCT_AMT": 0},
    "TB_JOB_HSTRY": {"ACTR_TYPE_CD": "AK.SYSTEM"},
}
# 문서가 "정확히 하나는 필수"라고 한 구조는 선택 외래키여도 하나를 채워야 한다.
ALSO_REQUIRE: dict[str, tuple[str, ...]] = {
    "TB_PST": ("WRT_MNGR_SN",),
    "TB_FILE": ("PST_SN",),
    "TB_SMS_TRGT": ("MBR_SN",),
    "TB_SMS_DMND": ("DMND_MNGR_SN",),
}
# 첨부파일의 단일 소유자 컬럼(FILE-10). 게시물 외의 소유자를 시험이 지정하면 게시물은 만들지 않는다.
FILE_OWNERS = (
    "CORS_SN",
    "INSTR_SN",
    "SITE_CONTS_SN",
    "ATNLC_APLY_SN",
    "RFND_SN",
    "INSTR_APLY_SN",
    "MBR_STATS_SRC_SN",
    "RDCT_BFHD_SRNG_SN",
    "CORS_DGSTFN_SRC_SN",
)


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
        self._ymd_end = "20260131"

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
        for name, value in PRESETS.get(table_name, {}).items():
            provided.setdefault(name, value)
        if table_name == "TB_COM_CD":  # R01: 코드의 앞부분이 그룹과 같아야 한다
            number = next(self.counter)
            provided.setdefault("CD_GROUP_ID", "ZZ")
            provided.setdefault("COM_CD", f"ZZ.T{number}")
        if (
            BUNDLE in names
            and BUNDLE not in provided
            and table_name != "TB_OPER_BNDL"
            and table.column(BUNDLE).required
        ):
            provided[BUNDLE] = self.bundle()
        for fk in table.foreign_keys:
            if fk.parent_table == "TB_COM_CD" or fk.parent_table == table_name:
                continue
            given = [column in provided for column in fk.columns]
            forced = any(column in ALSO_REQUIRE.get(table_name, ()) for column in fk.columns)
            if table_name == "TB_FILE" and any(owner in provided for owner in FILE_OWNERS):
                forced = False  # 시험이 소유자를 정했으면 게시물을 따로 붙이지 않는다(소유자는 정확히 하나)
            # 선택 외래키는 운영묶음 컬럼을 뺀 나머지가 하나도 안 채워졌을 때만 건너뛴다(묶음은 늘 채워져 있다)
            own_given = any(column in provided for column in fk.columns if column != BUNDLE)
            if all(given) or (fk.nullable and not forced and not own_given):
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
