# 스키마 설계안에서 MariaDB 10.11 물리 DDL(시퀀스·테이블·키·외래키·검사·코드 시드)을 만드는 생성기
import re

from app.tools.schema_doc import CheckRule, CodeValue, Column, ForeignKey, Index, SchemaDoc, Table

CHARSET = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
MAX_IDENTIFIER = 64  # MariaDB 식별자 길이 한도


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_type(logical: str) -> str:
    """문서의 논리 타입을 MariaDB 타입으로 바꾼다. 일련번호 NUMERIC(22,0)은 줄이지 않는다(스키마 1.2)."""
    if logical.startswith("NUMERIC"):
        return logical.replace("NUMERIC", "DECIMAL", 1)
    if logical == "CLOB":
        return "LONGTEXT"
    if re.fullmatch(r"(VARCHAR|CHAR)\(\d+\)|DATETIME", logical):
        return logical
    raise ValueError(f"알 수 없는 타입 {logical}")


def sequence_name(table: Table) -> str | None:
    """단일 숫자 기본키에만 시퀀스를 둔다(ADR-029). 연결 테이블의 복합키와 코드 기본키는 값을 직접 넣는다."""
    pk = table.primary_key.columns
    if len(pk) == 1 and table.column(pk[0]).type.startswith("NUMERIC"):
        return f"SQ_{table.name.removeprefix('TB_')}"
    return None


def column_sql(table: Table, column: Column) -> str:
    parts = [column.name, sql_type(column.type), "NOT NULL" if column.required else "NULL"]
    sequence = sequence_name(table)
    if sequence and column.name == table.primary_key.columns[0]:
        parts.append(f"DEFAULT NEXTVAL({sequence})")
    elif column.default == "SERVER_NOW":
        parts.append("DEFAULT CURRENT_TIMESTAMP")  # 서버 시간대가 UTC라 곧 UTC 시각이다(스키마 N07)
    elif column.default is not None:
        parts.append(
            f"DEFAULT {column.default}"
            if column.type.startswith("NUMERIC")
            else f"DEFAULT {quote(column.default)}"
        )
    elif not column.required:
        parts.append("DEFAULT NULL")
    parts.append(f"COMMENT {quote(column.label)}")
    return " ".join(parts)


def condition_expression(condition: str) -> str:
    """조건부 UNIQUE의 조건을 생성 컬럼용 식으로 바꾼다. MariaDB는 생성 컬럼의 IN 목록을 막는다."""
    in_list = re.fullmatch(r"(\w+) IN \((.+)\)", condition)
    if in_list:
        values = re.findall(r"'([^']*)'", in_list[2])
        return " OR ".join(f"{in_list[1]}={quote(value)}" for value in values)
    if re.fullmatch(r"\w+ = '[^']*'", condition):
        return condition.replace(" = ", "=")
    raise ValueError(f"지원하지 않는 조건 {condition!r}")


def filter_column(index: Index) -> str:
    return f"ZF_{index.name.removeprefix('UQ_FILTER_')}"


def create_table(table: Table) -> str:
    lines = [f"  {column_sql(table, column)}" for column in table.columns]
    for index in table.indexes:
        if index.kind == "UQ_FILTER":
            assert index.condition is not None
            expression = condition_expression(index.condition)
            lines.append(
                f"  {filter_column(index)} TINYINT AS (CASE WHEN {expression} THEN 1 END) PERSISTENT"
            )
    for index in table.indexes:
        columns = ", ".join(index.columns)
        if index.kind == "PK":
            lines.append(f"  PRIMARY KEY ({columns})")
        elif index.kind == "UQ":
            lines.append(f"  UNIQUE KEY {index.name} ({columns})")
        elif index.kind == "UQ_FILTER":
            lines.append(f"  UNIQUE KEY {index.name} ({columns}, {filter_column(index)})")
        else:
            lines.append(f"  KEY {index.name} ({columns})")
    body = ",\n".join(lines)
    return f"CREATE TABLE {table.name} (\n{body}\n) {CHARSET} COMMENT={quote(table.label)}"


def add_foreign_key(table: Table, fk: ForeignKey) -> str:
    return (
        f"ALTER TABLE {table.name} ADD CONSTRAINT {fk.name} FOREIGN KEY ({', '.join(fk.columns)}) "
        f"REFERENCES {fk.parent_table} ({', '.join(fk.parent_columns)}) "
        f"ON DELETE {fk.on_delete} ON UPDATE {fk.on_update}"
    )


def add_check(rule: CheckRule) -> str:
    name = "CK_" + rule.rule_id.replace("-", "_")
    if rule.kind == "YN":
        expression = f"{rule.column} IN ('Y','N')"
    else:
        expression = f"TRIM({rule.column}) LIKE {quote((rule.prefix or '') + '%')}"
    return f"ALTER TABLE {rule.table} ADD CONSTRAINT {name} CHECK ({expression})"


def seed_codes(codes: tuple[CodeValue, ...]) -> str:
    """공통코드 초기값. 정렬순서는 문서의 나열 순서(그룹 안 1부터)다."""
    seen: dict[str, int] = {}
    rows = []
    for code in codes:
        seen[code.group] = seen.get(code.group, 0) + 1
        rows.append(f"  ({quote(code.code)}, {quote(code.group)}, {quote(code.label)}, {seen[code.group]})")
    return "INSERT INTO TB_COM_CD (COM_CD, CD_GROUP_ID, CD_NM, SORT_SEQ) VALUES\n" + ",\n".join(rows)


def up_statements(schema: SchemaDoc) -> list[str]:
    statements = [
        f"CREATE SEQUENCE {name} START WITH 1 INCREMENT BY 1 CACHE 1000 NOCYCLE"
        for name in (sequence_name(table) for table in schema.tables)
        if name
    ]
    statements += [create_table(table) for table in schema.tables]
    statements += [add_foreign_key(table, fk) for table in schema.tables for fk in table.foreign_keys]
    statements += [add_check(rule) for rule in schema.checks]
    statements.append(seed_codes(schema.codes))
    return statements


def down_statements(schema: SchemaDoc) -> list[str]:
    statements = ["SET FOREIGN_KEY_CHECKS=0"]
    statements += [f"DROP TABLE IF EXISTS {table.name}" for table in reversed(schema.tables)]
    statements += [
        f"DROP SEQUENCE IF EXISTS {name}"
        for name in (sequence_name(table) for table in reversed(schema.tables))
        if name
    ]
    statements.append("SET FOREIGN_KEY_CHECKS=1")
    return statements


def render(statements: list[str]) -> str:
    return "".join(f"{statement};\n\n" for statement in statements)


def identifier_problems(schema: SchemaDoc) -> list[str]:
    """MariaDB 식별자 길이 한도와 이름 중복을 확인한다."""
    problems: list[str] = []
    fk_names: set[str] = set()
    names = [table.name for table in schema.tables]
    names += [name for name in (sequence_name(table) for table in schema.tables) if name]
    for table in schema.tables:
        names += [index.name for index in table.indexes]
        names += [column.name for column in table.columns]
        for index in table.indexes:
            if index.kind == "UQ_FILTER":
                names.append(filter_column(index))
        for fk in table.foreign_keys:
            if fk.name in fk_names:
                problems.append(f"외래키 이름 중복 {fk.name}")
            fk_names.add(fk.name)
            names.append(fk.name)
        index_names = [index.name for index in table.indexes]
        if len(index_names) != len(set(index_names)):
            problems.append(f"{table.name}: 인덱스 이름 중복")
    names += ["CK_" + rule.rule_id.replace("-", "_") for rule in schema.checks]
    problems += [
        f"식별자가 {MAX_IDENTIFIER}자를 넘음: {name}" for name in names if len(name) > MAX_IDENTIFIER
    ]
    return problems
