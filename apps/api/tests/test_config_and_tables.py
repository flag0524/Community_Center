# 배포 설정 읽기와 생성된 SQLAlchemy 테이블 정의가 설계안·저장된 파일과 같은지 확인하는 시험(DB 불필요)
import pytest

from app.core.config import ConfigError, load_settings
from app.db import tables
from app.tools.generate_ddl import TABLES, generate
from app.tools.schema_doc import SchemaDoc, parse_schema_doc


def test_설정은_환경변수에서_읽고_없으면_값을_드러내지_않고_멈춘다() -> None:
    settings = load_settings({"JORI_DATABASE_URL": "mysql+pymysql://u:secret@h/db", "JORI_SITE_ID": "jori"})
    assert settings.site_id == "jori"
    with pytest.raises(ConfigError) as caught:
        load_settings({"JORI_DATABASE_URL": "mysql+pymysql://u:secret@h/db"})
    assert "JORI_SITE_ID" in str(caught.value)
    assert "secret" not in str(caught.value)  # 접속 정보가 메시지에 새지 않는다
    with pytest.raises(ConfigError):
        load_settings({})


def test_저장된_테이블_정의가_설계안에서_만든_결과와_같다() -> None:
    assert TABLES.read_text(encoding="utf-8") == generate()["tables.py"]


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


def test_테이블_정의가_문서의_테이블_컬럼_기본키와_같다(schema: SchemaDoc) -> None:
    assert set(tables.metadata.tables) == {table.name for table in schema.tables}
    assert sum(len(table.columns) for table in tables.metadata.tables.values()) == 610
    for doc in schema.tables:
        built = tables.metadata.tables[doc.name]
        assert [column.name for column in built.columns] == [column.name for column in doc.columns]
        assert [column.name for column in built.primary_key.columns] == list(doc.primary_key.columns)
        for column in doc.columns:
            assert (
                built.c[column.name].nullable == (not column.required)
                or column.name in doc.primary_key.columns
            )


def test_일련번호는_22자리_Numeric이다() -> None:
    column = tables.TB_ATNLC_APLY.c.ATNLC_APLY_SN
    assert (column.type.precision, column.type.scale) == (22, 0)  # type: ignore[attr-defined]
    assert tables.TB_STLM.c.STLM_SN.type.precision == 10  # type: ignore[attr-defined]
