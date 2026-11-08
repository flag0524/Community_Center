# 배포 설정 읽기와 생성된 SQLAlchemy 테이블 정의가 설계안·저장된 파일과 같은지 확인하는 시험(DB 불필요)
import pytest

from app.core.config import ConfigError, load_settings
from app.db import tables
from app.tools.generate_ddl import TABLES, generate
from app.tools.schema_doc import SchemaDoc, parse_schema_doc

KEY = "k" * 40
BASE = {"JORI_DATABASE_URL": "mysql+pymysql://u:secret@h/db", "JORI_SITE_ID": "jori", "JORI_SECRET_KEY": KEY}


def test_설정은_환경변수에서_읽고_없으면_값을_드러내지_않고_멈춘다() -> None:
    settings = load_settings(BASE)
    assert (settings.site_id, settings.secret_key, settings.cookie_secure) == ("jori", KEY, True)
    assert settings.admin_lock_failures is None  # 기관 정책(Q28) 전에는 관리자 잠금 수치를 지어내지 않는다
    for missing in ("JORI_DATABASE_URL", "JORI_SITE_ID", "JORI_SECRET_KEY"):
        env = {name: value for name, value in BASE.items() if name != missing}
        with pytest.raises(ConfigError) as caught:
            load_settings(env)
        assert missing in str(caught.value)
        assert "secret" not in str(caught.value) and KEY not in str(
            caught.value
        )  # 접속 정보·비밀키가 새지 않는다
    with pytest.raises(ConfigError):
        load_settings({})


def test_비밀키는_32자_이상이어야_하고_메시지에_값을_싣지_않는다() -> None:
    with pytest.raises(ConfigError) as caught:
        load_settings({**BASE, "JORI_SECRET_KEY": "short-key"})
    assert "32" in str(caught.value) and "short-key" not in str(caught.value)


def test_관리자_잠금은_횟수와_분을_함께_설정해야_한다() -> None:
    configured = load_settings({**BASE, "JORI_ADMIN_LOCK_FAILURES": "7", "JORI_ADMIN_LOCK_MINUTES": "20"})
    assert (configured.admin_lock_failures, configured.admin_lock_minutes) == (7, 20)
    with pytest.raises(ConfigError):
        load_settings({**BASE, "JORI_ADMIN_LOCK_FAILURES": "7"})
    with pytest.raises(ConfigError):
        load_settings({**BASE, "JORI_ADMIN_LOCK_FAILURES": "abc", "JORI_ADMIN_LOCK_MINUTES": "20"})


def test_선택_설정은_환경변수로_바꾼다() -> None:
    settings = load_settings({**BASE, "JORI_PBKDF2_ITERATIONS": "1234", "JORI_COOKIE_SECURE": "0"})
    assert (settings.pbkdf2_iterations, settings.cookie_secure) == (1234, False)


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
