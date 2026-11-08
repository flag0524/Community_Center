# DB 스키마 설계안(마크다운)의 테이블·컬럼·키·외래키·공통코드·무결성규칙 표를 읽어 구조로 바꾸는 파서
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DOC = Path(__file__).resolve().parents[4] / "docs" / "PRJ_2026_002_DB스키마_설계안.md"

_COLUMN = re.compile(
    r"^\| (\d+) \| `(\w+)` \| ([^|]*) \| ([^|]*) \| ([YN]) \| ([^|]*) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$",
    re.MULTILINE,
)
_KEY = re.compile(r"^\| (PK|UQ|UQ_FILTER|IX) \| `(\w+)` \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$", re.MULTILINE)
_FK = re.compile(
    r"^\| `(FK_\w+)` \| ([^|]*) \| `(\w+)` \(([^)]*)\) \| ([YN]) \| ([A-Z]+) / ([A-Z]+) \| ([^|]*) \|$",
    re.MULTILINE,
)
_CODE = re.compile(r"^\| (\w+) \| ([^|]*) \| (\w+\.\w+) \| ([^|]*) \| ([^|]*) \|$", re.MULTILINE)
_RULE = re.compile(r"^\| ((?:YN|CD)-\w+-\w+) \| (TB_\w+) \| ([^|]*) \| ([^|]*) \| ([^|]*) \|$", re.MULTILINE)
_TABLE_LIST = re.compile(
    r"^\| (\d+) \| ([^|]*) \| `(TB_\w+)` \| ([^|]*) \| ([^|]*) \| (\d+) \|$", re.MULTILINE
)


@dataclass(frozen=True)
class Column:
    seq: int
    name: str
    label: str
    type: str
    required: bool
    default: str | None
    key_flags: str
    domain: str


@dataclass(frozen=True)
class Index:
    kind: str  # PK, UQ, UQ_FILTER, IX
    name: str
    columns: tuple[str, ...]
    condition: str | None


@dataclass(frozen=True)
class ForeignKey:
    name: str
    columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]
    nullable: bool
    on_delete: str
    on_update: str


@dataclass(frozen=True)
class Table:
    name: str
    label: str
    scope: str
    declared_columns: int
    columns: tuple[Column, ...]
    indexes: tuple[Index, ...]
    foreign_keys: tuple[ForeignKey, ...]

    def column(self, name: str) -> Column:
        return next(column for column in self.columns if column.name == name)

    @property
    def primary_key(self) -> Index:
        return next(index for index in self.indexes if index.kind == "PK")


@dataclass(frozen=True)
class CodeValue:
    group: str
    group_label: str
    code: str
    label: str
    source: str


@dataclass(frozen=True)
class CheckRule:
    rule_id: str
    table: str
    column: str
    kind: str  # YN(Y/N만 허용) 또는 CD(코드 접두부)
    prefix: str | None


@dataclass(frozen=True)
class SchemaDoc:
    tables: tuple[Table, ...]
    codes: tuple[CodeValue, ...]
    checks: tuple[CheckRule, ...]
    listed_tables: tuple[tuple[str, int], ...] = field(default=())

    def table(self, name: str) -> Table:
        return next(table for table in self.tables if table.name == name)


def _section(doc: str, start: str, end: str) -> str:
    return doc[doc.index(start) : doc.index(end)]


def _names(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _table(text: str) -> Table:
    head = text.split("\n", 1)[0]
    name, label = (part.strip() for part in head.split(" / ", 1))
    meta = re.search(r"범위: ([^.\n]+)\. 컬럼 수: (\d+)\.", text)
    if meta is None:
        raise ValueError(f"{name}: 범위·컬럼 수 줄이 없다")
    columns = tuple(
        Column(
            seq=int(m[1]),
            name=m[2],
            label=m[3].strip(),
            type=m[4].strip(),
            required=m[5] == "Y",
            default=None if m[6].strip() == "없음" else m[6].strip(),
            key_flags=m[7].strip(),
            domain=m[8].strip(),
        )
        for m in _COLUMN.finditer(text)
    )
    indexes = tuple(
        Index(
            kind=m[1],
            name=m[2],
            columns=_names(m[3]),
            condition=None if m[4].strip() == "—" else m[4].strip(),
        )
        for m in _KEY.finditer(text)
    )
    foreign_keys = tuple(
        ForeignKey(
            name=m[1],
            columns=_names(m[2]),
            parent_table=m[3],
            parent_columns=_names(m[4]),
            nullable=m[5] == "Y",
            on_delete=m[6],
            on_update=m[7],
        )
        for m in _FK.finditer(text)
    )
    return Table(name, label, meta[1], int(meta[2]), columns, indexes, foreign_keys)


def parse_schema_doc(path: Path = DEFAULT_DOC) -> SchemaDoc:
    doc = path.read_text(encoding="utf-8")
    detail = _section(doc, "## 4. 전체 테이블 상세", "## 5. 공통코드와 저장·무결성규칙")
    tables = tuple(_table(block) for block in re.split(r"\n### 4\.\d+\. ", detail)[1:])
    codes = tuple(
        CodeValue(m[1], m[2].strip(), m[3], m[4].strip(), m[5].strip())
        for m in _CODE.finditer(_section(doc, "### 5.2 공통코드", "### 5.3 무결성규칙"))
    )
    checks: list[CheckRule] = []
    for m in _RULE.finditer(_section(doc, "### 5.3 무결성규칙", "## 6. 관리자 권한")):
        rule_id, table, text = m[1], m[2], m[4].strip()
        if rule_id.startswith("YN-"):
            yn = re.fullmatch(r"(\w+) IN \('Y','N'\)", text)
            if yn is None:
                raise ValueError(f"{rule_id}: 예상하지 못한 Y/N 규칙 문구 {text!r}")
            checks.append(CheckRule(rule_id, table, yn[1], "YN", None))
        else:
            # 문서의 문구는 두 가지다(23건 "공백 제거값은 'XX.'로 시작", 13건 "XX. 접두부와 ... 존재")
            cd = re.match(r"(\w+)의 공백 제거값은 '(\w+\.)'로 시작해야 한다", text) or re.match(
                r"(\w+)는 (\w+\.) 접두부와 TB_COM_CD 존재를 함께 검사", text
            )
            if cd is None:
                raise ValueError(f"{rule_id}: 예상하지 못한 코드 규칙 문구 {text!r}")
            checks.append(CheckRule(rule_id, table, cd[1], "CD", cd[2]))
    listed = tuple(
        (m[3], int(m[6])) for m in _TABLE_LIST.finditer(_section(doc, "## 2. 전체 테이블 목록", "## 3."))
    )
    return SchemaDoc(tables, codes, tuple(checks), listed)


def validate(schema: SchemaDoc) -> list[str]:
    """문서 안의 숫자와 참조가 서로 맞는지 확인하고 어긋난 곳을 모두 돌려준다. 비어 있으면 일관적이다."""
    problems: list[str] = []
    by_name = {table.name: table for table in schema.tables}
    listed = dict(schema.listed_tables)
    for table in schema.tables:
        if len(table.columns) != table.declared_columns:
            problems.append(
                f"{table.name}: 컬럼 {len(table.columns)}개인데 문서는 {table.declared_columns}개"
            )
        if table.name in listed and listed[table.name] != len(table.columns):
            problems.append(f"{table.name}: 2절 목록의 컬럼 수 {listed[table.name]}와 다름")
        names = {column.name for column in table.columns}
        for index in table.indexes:
            missing = [column for column in index.columns if column not in names]
            if missing:
                problems.append(f"{table.name}.{index.name}: 없는 컬럼 {missing}")
        for fk in table.foreign_keys:
            parent = by_name.get(fk.parent_table)
            if parent is None:
                problems.append(f"{table.name}.{fk.name}: 없는 부모 테이블 {fk.parent_table}")
                continue
            if len(fk.columns) != len(fk.parent_columns):
                problems.append(f"{table.name}.{fk.name}: 자식·부모 컬럼 수가 다름")
                continue
            for child, parent_column in zip(fk.columns, fk.parent_columns, strict=True):
                if child not in names or parent_column not in {c.name for c in parent.columns}:
                    problems.append(f"{table.name}.{fk.name}: 없는 컬럼 {child}→{parent_column}")
                elif table.column(child).type != parent.column(parent_column).type:
                    problems.append(f"{table.name}.{fk.name}: 타입이 다름 {child}→{parent_column}")
            parent_keys = {index.columns for index in parent.indexes if index.kind in ("PK", "UQ")}
            if fk.parent_columns not in parent_keys:
                problems.append(
                    f"{table.name}.{fk.name}: {fk.parent_table}에 {fk.parent_columns} 후보키가 없음"
                )
    for check in schema.checks:
        target = by_name.get(check.table)
        if target is None or check.column not in {column.name for column in target.columns}:
            problems.append(f"{check.rule_id}: 없는 대상 {check.table}.{check.column}")
    return problems
