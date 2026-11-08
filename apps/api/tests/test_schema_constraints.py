# 실제 MariaDB에서 스키마 제약이 동작하는지(조건부 유일성·복합 외래키·검사·RESTRICT·시퀀스) 행을 넣어 확인하는 시험
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.tools.schema_doc import SchemaDoc, parse_schema_doc
from tests.factory import RowFactory

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


@pytest.fixture()
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    """시험마다 트랜잭션을 열고 끝에 되돌려 DB를 깨끗하게 둔다."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture()
def factory(conn: Connection, schema: SchemaDoc) -> RowFactory:
    return RowFactory(conn, schema)


def rejected(conn: Connection, sql: str, params: dict[str, object], code: int) -> None:
    """제약 위반은 그 문장만 실패하고 트랜잭션은 계속 쓸 수 있다. 오류 번호까지 확인한다.

    CHECK 위반(4025)은 PyMySQL이 IntegrityError가 아닌 OperationalError로 올려 DBAPIError로 받는다.
    """
    with pytest.raises(DBAPIError) as caught:
        conn.execute(text(sql), params)
    assert caught.value.orig is not None and caught.value.orig.args[0] == code


def test_45개_테이블_모두에_행을_만들_수_있다(
    conn: Connection, factory: RowFactory, schema: SchemaDoc
) -> None:
    """필수 외래키 사슬과 필수 컬럼 정의가 실제로 만족 가능하다는 총괄 점검."""
    for table in schema.tables:
        row = factory.make(table.name)
        assert set(row) == {column.name for column in table.columns}, table.name


def test_일련번호가_자동으로_늘어나고_22자리_값도_저장한다(conn: Connection, factory: RowFactory) -> None:
    first = factory.make("TB_OPER_BNDL")
    second = factory.make("TB_OPER_BNDL")
    assert second["OPER_BNDL_SN"] > first["OPER_BNDL_SN"]
    big = 1234567890123456789012
    conn.execute(
        text("UPDATE TB_OPER_BNDL SET OPER_BNDL_SN = :big WHERE OPER_BNDL_SN = :old"),
        {"big": big, "old": first["OPER_BNDL_SN"]},
    )
    assert str(
        conn.execute(
            text("SELECT OPER_BNDL_SN FROM TB_OPER_BNDL WHERE OPER_BNDL_SN = :big"), {"big": big}
        ).scalar_one()
    ) == str(big)


def test_같은_강좌의_유효_중복_신청은_막고_취소_건은_몇_개든_허용한다(
    conn: Connection, factory: RowFactory
) -> None:
    member = factory.make("TB_MBR")
    course = factory.make("TB_CORS")
    bundle = member["OPER_BNDL_SN"]
    base = {"OPER_BNDL_SN": bundle, "MBR_SN": member["MBR_SN"], "CORS_SN": course["CORS_SN"]}
    factory.make("TB_ATNLC_APLY", **base, APLY_STTS_CD="ES.HOLD", IDEM_KEY="k1")
    sql = "INSERT INTO TB_ATNLC_APLY (OPER_BNDL_SN, MBR_SN, CORS_SN, APLY_STTS_CD, TTCHG_AMT, RDCT_AMT, STLM_PRNMNT_AMT, IDEM_KEY) VALUES (:b, :m, :c, :s, 1, 0, 1, :k)"
    args = {"b": bundle, "m": member["MBR_SN"], "c": course["CORS_SN"]}
    for number, status in enumerate(("ES.WAIT", "ES.HOLD", "ES.CONFIRM")):
        rejected(conn, sql, {**args, "s": status, "k": f"dup{number}"}, 1062)
    for number in range(3):  # 취소·만료 건은 몇 개든 쌓인다
        conn.execute(text(sql), {**args, "s": "ES.CANCEL", "k": f"c{number}"})
    conn.execute(text("UPDATE TB_ATNLC_APLY SET APLY_STTS_CD = 'ES.CANCEL' WHERE IDEM_KEY = 'k1'"))
    conn.execute(text(sql), {**args, "s": "ES.HOLD", "k": "again"})  # 취소 뒤 재신청은 새 행으로 허용


def test_성공_결제는_신청마다_하나만_허용한다(conn: Connection, factory: RowFactory) -> None:
    apply = factory.make("TB_ATNLC_APLY")
    base = {"OPER_BNDL_SN": apply["OPER_BNDL_SN"], "ATNLC_APLY_SN": apply["ATNLC_APLY_SN"]}
    factory.make("TB_STLM", **base, STLM_STTS_CD="PS.FAIL", IDEM_KEY="p1")
    factory.make("TB_STLM", **base, STLM_STTS_CD="PS.FAIL", IDEM_KEY="p2")
    factory.make("TB_STLM", **base, STLM_STTS_CD="PS.PAID", IDEM_KEY="p3")
    with pytest.raises(IntegrityError) as caught:
        factory.make("TB_STLM", **base, STLM_STTS_CD="PS.PAID", IDEM_KEY="p4")
    assert caught.value.orig is not None and caught.value.orig.args[0] == 1062


def test_복합_외래키가_다른_묶음의_회원과_강좌_연결을_막는다(conn: Connection, factory: RowFactory) -> None:
    other = factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    member = factory.make("TB_MBR")  # 기본 묶음
    course = factory.make("TB_CORS")
    sql = "INSERT INTO TB_ATNLC_APLY (OPER_BNDL_SN, MBR_SN, CORS_SN, APLY_STTS_CD, TTCHG_AMT, RDCT_AMT, STLM_PRNMNT_AMT, IDEM_KEY) VALUES (:b, :m, :c, 'ES.HOLD', 1, 0, 1, :k)"
    rejected(
        conn, sql, {"b": other, "m": member["MBR_SN"], "c": course["CORS_SN"], "k": "x1"}, 1452
    )  # 다른 묶음 + 이 묶음 회원
    rejected(
        conn, sql, {"b": member["OPER_BNDL_SN"], "m": member["MBR_SN"], "c": 999999, "k": "x2"}, 1452
    )  # 없는 강좌


def test_Y_N_검사와_코드_접두부_검사와_코드_외래키가_잘못된_값을_막는다(
    conn: Connection, factory: RowFactory
) -> None:
    bundle = factory.bundle()
    update = "UPDATE {table} SET {column} = :v WHERE {key} = :k"
    rejected(
        conn,
        update.format(table="TB_OPER_BNDL", column="USE_YN", key="OPER_BNDL_SN"),
        {"v": "X", "k": bundle},
        4025,
    )
    member = factory.make("TB_MBR")
    stmt = update.format(table="TB_MBR", column="MBR_STTS_CD", key="MBR_SN")
    rejected(conn, stmt, {"v": "XX.WRONG", "k": member["MBR_SN"]}, 4025)  # 접두부 검사
    rejected(conn, stmt, {"v": "MS.NOPE", "k": member["MBR_SN"]}, 1452)  # 접두부는 맞지만 없는 코드


def test_참조되는_부모_행은_지우거나_번호를_바꿀_수_없다(conn: Connection, factory: RowFactory) -> None:
    member = factory.make("TB_MBR")
    factory.make("TB_ATNLC_APLY", MBR_SN=member["MBR_SN"], OPER_BNDL_SN=member["OPER_BNDL_SN"])
    rejected(conn, "DELETE FROM TB_MBR WHERE MBR_SN = :k", {"k": member["MBR_SN"]}, 1451)
    # 이미 있는 번호와 겹치지 않는 값으로 바꿔야 외래키(1451)만 확인된다
    rejected(conn, "UPDATE TB_MBR SET MBR_SN = 777777777777 WHERE MBR_SN = :k", {"k": member["MBR_SN"]}, 1451)


def test_멱등키는_묶음_안에서만_고유하다(conn: Connection, factory: RowFactory) -> None:
    first = factory.make("TB_ATNLC_APLY", IDEM_KEY="same")
    with pytest.raises(IntegrityError) as caught:
        factory.make("TB_ATNLC_APLY", OPER_BNDL_SN=first["OPER_BNDL_SN"], IDEM_KEY="same")
    assert caught.value.orig is not None and caught.value.orig.args[0] == 1062
    other = factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    factory.make("TB_ATNLC_APLY", OPER_BNDL_SN=other, IDEM_KEY="same")  # 다른 묶음에서는 같은 키가 허용된다
