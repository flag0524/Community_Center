# 스키마 설계안에서 SQLAlchemy Core 테이블 정의(app/db/tables.py)를 만드는 생성기. 서식은 생성기가 정한다
from app.tools.schema_ddl import sequence_name
from app.tools.schema_doc import Column, SchemaDoc, Table

HEADER = """# 스키마 설계안에서 app.tools.generate_ddl이 만든 SQLAlchemy 테이블 정의. 직접 고치지 않는다
# 기본값(SERVER_NOW, 시퀀스 NEXTVAL)은 DB가 채우므로 여기에 두지 않는다. ZF_* 생성 컬럼도 뺐다.
from sqlalchemy import CHAR, Column, DateTime, MetaData, Numeric, String, Table, Text, text

metadata = MetaData()
"""


def sa_type(logical: str) -> str:
    if logical.startswith("NUMERIC"):
        return logical.replace("NUMERIC", "Numeric", 1).replace(",", ", ")
    if logical.startswith("VARCHAR"):
        return logical.replace("VARCHAR", "String", 1)
    if logical.startswith("CHAR"):
        return logical.replace("CHAR", "CHAR", 1)
    if logical == "DATETIME":
        return "DateTime()"
    if logical == "CLOB":
        return "Text()"
    raise ValueError(f"알 수 없는 타입 {logical}")


def column_source(table: Table, column: Column) -> str:
    primary = column.name in table.primary_key.columns
    parts = [f'"{column.name}"', sa_type(column.type)]
    if primary:
        parts.append("primary_key=True")
        parts.append("autoincrement=False")
        sequence = sequence_name(table)
        if sequence and column.name == table.primary_key.columns[0]:
            parts.append(f'server_default=text("NEXTVAL({sequence})")')  # DB가 시퀀스로 채운다
    else:
        parts.append(f"nullable={not column.required}")
    inner = "".join(f"        {part},\n" for part in parts)
    return f"    Column(\n{inner}    ),"


def render_tables(schema: SchemaDoc) -> str:
    blocks = [HEADER]
    for table in schema.tables:
        lines = [f"{table.name} = Table(", f'    "{table.name}",', "    metadata,"]
        lines += [column_source(table, column) for column in table.columns]
        lines.append(")")
        blocks.append("\n".join(lines) + "\n")
    names = "".join(f'    "{table.name}",\n' for table in schema.tables)
    blocks.append(f"TABLE_NAMES = (\n{names})\n")
    return "\n".join(blocks)
