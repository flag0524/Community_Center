# DB 세션 의존성(커밋·롤백), 운영묶음 판정, 낙관적 잠금, 멱등 삽입, 오류 로그를 실제 MariaDB로 확인하는 시험
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode, install_error_handlers
from app.db import session as session_module
from app.db import tables
from app.db.bundle import BundleResolver
from app.db.idempotent import insert_idempotent
from app.db.versioned import update_versioned
from app.tools.schema_doc import SchemaDoc, parse_schema_doc
from tests.factory import RowFactory

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


@pytest.fixture()
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture()
def session(conn: Connection) -> Iterator[Session]:
    """시험 트랜잭션 안에서 도는 세션. SAVEPOINT를 쓰는 코드도 그대로 동작한다."""
    with Session(
        bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False, autoflush=False
    ) as s:
        yield s


@pytest.fixture()
def factory(conn: Connection, schema: SchemaDoc) -> RowFactory:
    return RowFactory(conn, schema)


def codes(error: pytest.ExceptionInfo[ApiError]) -> ErrorCode:
    return error.value.code


def test_시퀀스_기본키는_삽입_뒤_RETURNING으로_돌려받는다(session: Session) -> None:
    created = session.execute(
        insert(tables.TB_OPER_BNDL)
        .values(
            OPER_BNDL_NM="a",
            SITE_NM="a",
            SITE_ID="site-a",
            URL_ADDR="https://a.invalid",
            TMZN_NM="Asia/Seoul",
        )
        .returning(tables.TB_OPER_BNDL.c.OPER_BNDL_SN)
    ).scalar_one()
    assert int(created) > 0


def test_운영묶음은_사이트_식별자로_찾고_한번_찾으면_기억한다(session: Session, factory: RowFactory) -> None:
    row = factory.make("TB_OPER_BNDL", SITE_ID="site-b", USE_YN="Y")
    resolver = BundleResolver("site-b")
    assert resolver.resolve(session) == row["OPER_BNDL_SN"]
    session.execute(tables.TB_OPER_BNDL.delete().where(tables.TB_OPER_BNDL.c.SITE_ID == "site-b"))
    assert resolver.resolve(session) == row["OPER_BNDL_SN"]  # 지워진 뒤에도 기억한 값을 쓴다


def test_없는_사이트나_사용_중지된_사이트는_배포_오류로_멈춘다(session: Session, factory: RowFactory) -> None:
    factory.make("TB_OPER_BNDL", SITE_ID="site-off", USE_YN="N")
    for site in ("site-none", "site-off"):
        with pytest.raises(ApiError) as caught:
            BundleResolver(site).resolve(session)
        assert codes(caught) == ErrorCode.INTERNAL_ERROR


def test_낙관적_잠금은_같은_버전만_고치고_버전을_올린다(session: Session, factory: RowFactory) -> None:
    row = factory.make("TB_DONG")
    key: dict[str, Any] = {"OPER_BNDL_SN": row["OPER_BNDL_SN"], "DONG_SN": row["DONG_SN"]}
    assert (
        update_versioned(session, tables.TB_DONG, key, row["RCRD_VER"], {"DONG_NM": "새 이름"})
        == row["RCRD_VER"] + 1
    )
    saved = session.execute(
        select(tables.TB_DONG.c.DONG_NM, tables.TB_DONG.c.RCRD_VER, tables.TB_DONG.c.MDFCN_DT).where(
            row["DONG_SN"] == tables.TB_DONG.c.DONG_SN
        )
    ).one()
    assert (saved.DONG_NM, int(saved.RCRD_VER)) == ("새 이름", row["RCRD_VER"] + 1)
    assert saved.MDFCN_DT is not None  # 고친 시각이 남는다


def test_낡은_버전은_409이고_값을_바꾸지_않는다(session: Session, factory: RowFactory) -> None:
    row = factory.make("TB_DONG")
    key: dict[str, Any] = {"OPER_BNDL_SN": row["OPER_BNDL_SN"], "DONG_SN": row["DONG_SN"]}
    update_versioned(session, tables.TB_DONG, key, row["RCRD_VER"], {"DONG_NM": "먼저 고침"})
    with pytest.raises(ApiError) as caught:
        update_versioned(session, tables.TB_DONG, key, row["RCRD_VER"], {"DONG_NM": "늦게 고침"})  # 낡은 버전
    assert codes(caught) == ErrorCode.VERSION_CONFLICT
    name = session.execute(
        select(tables.TB_DONG.c.DONG_NM).where(row["DONG_SN"] == tables.TB_DONG.c.DONG_SN)
    ).scalar_one()
    assert name == "먼저 고침"


def test_없는_행과_다른_묶음의_행은_404다(session: Session, factory: RowFactory) -> None:
    row = factory.make("TB_DONG")
    other = factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    with pytest.raises(ApiError) as missing:
        update_versioned(
            session,
            tables.TB_DONG,
            {"OPER_BNDL_SN": row["OPER_BNDL_SN"], "DONG_SN": 987654321},
            1,
            {"DONG_NM": "x"},
        )
    assert codes(missing) == ErrorCode.NOT_FOUND
    with pytest.raises(ApiError) as crossed:  # 묶음 조건이 있어 다른 묶음의 동은 고칠 수 없다
        update_versioned(
            session, tables.TB_DONG, {"OPER_BNDL_SN": other, "DONG_SN": row["DONG_SN"]}, 1, {"DONG_NM": "x"}
        )
    assert codes(crossed) == ErrorCode.NOT_FOUND


def _apply_values(factory: RowFactory, key: str, amount: int = 1) -> dict[str, Any]:
    member = factory.make("TB_MBR")
    course = factory.make("TB_CORS", OPER_BNDL_SN=member["OPER_BNDL_SN"])
    return {
        "OPER_BNDL_SN": member["OPER_BNDL_SN"],
        "MBR_SN": member["MBR_SN"],
        "CORS_SN": course["CORS_SN"],
        "APLY_STTS_CD": "ES.WAIT",
        "TTCHG_AMT": amount,
        "RDCT_AMT": 0,
        "STLM_PRNMNT_AMT": amount,
        "IDEM_KEY": key,
    }


def test_멱등_삽입은_처음에는_만들고_같은_요청은_이전_행을_돌려준다(
    session: Session, factory: RowFactory
) -> None:
    values = _apply_values(factory, "key-1")
    same = lambda row: row["CORS_SN"] == values["CORS_SN"] and row["MBR_SN"] == values["MBR_SN"]  # noqa: E731
    first, replayed_first = insert_idempotent(session, tables.TB_ATNLC_APLY, values, same)
    again, replayed_again = insert_idempotent(session, tables.TB_ATNLC_APLY, values, same)
    assert (replayed_first, replayed_again) == (False, True)
    assert first["ATNLC_APLY_SN"] == again["ATNLC_APLY_SN"]
    count = session.execute(
        select(tables.TB_ATNLC_APLY.c.ATNLC_APLY_SN).where(tables.TB_ATNLC_APLY.c.IDEM_KEY == "key-1")
    ).all()
    assert len(count) == 1  # 재전송이 행을 늘리지 않는다


def test_같은_키로_다른_요청이면_409이고_재전송_뒤에도_트랜잭션을_계속_쓴다(
    session: Session, factory: RowFactory
) -> None:
    values = _apply_values(factory, "key-2")
    insert_idempotent(session, tables.TB_ATNLC_APLY, values, lambda row: True)
    with pytest.raises(ApiError) as caught:
        insert_idempotent(session, tables.TB_ATNLC_APLY, values, lambda row: False)
    assert codes(caught) == ErrorCode.IDEMPOTENCY_CONFLICT
    session.execute(
        select(tables.TB_OPER_BNDL.c.OPER_BNDL_SN)
    ).first()  # 실패한 삽입이 트랜잭션을 망가뜨리지 않는다


def test_멱등키가_아닌_다른_유일키가_막으면_재전송으로_보지_않고_그대로_올린다(
    session: Session, factory: RowFactory
) -> None:
    values = _apply_values(factory, "key-3")
    insert_idempotent(session, tables.TB_ATNLC_APLY, values, lambda row: True)
    from sqlalchemy.exc import IntegrityError

    duplicate_user = {**values, "IDEM_KEY": "key-4"}  # 키는 새것이지만 같은 회원·강좌의 유효 신청이 이미 있다
    with pytest.raises(IntegrityError):
        insert_idempotent(session, tables.TB_ATNLC_APLY, duplicate_user, lambda row: True)


def _app_with_db(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """실제 get_db 의존성을 그대로 쓴다. 엔진만 시험 DB로 바꾼다."""
    monkeypatch.setattr(session_module, "get_engine", lambda: engine)
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/create/{site}")
    def create(site: str, db: Session = Depends(session_module.get_db)) -> dict[str, str]:  # noqa: B008
        db.execute(
            insert(tables.TB_OPER_BNDL).values(
                OPER_BNDL_NM=site,
                SITE_NM=site,
                SITE_ID=site,
                URL_ADDR="https://x.invalid",
                TMZN_NM="Asia/Seoul",
            )
        )
        if site.startswith("fail"):
            raise ApiError(ErrorCode.RULE_REJECTED)
        return {"ok": site}

    return app


def test_요청_세션은_성공하면_커밋하고_예외가_나면_되돌린다(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_app_with_db(migrated_engine, monkeypatch), raise_server_exceptions=False)
    try:
        assert client.post("/create/commit-site").status_code == 200
        assert client.post("/create/fail-site").status_code == 422
        with migrated_engine.connect() as check:
            sites = {row[0] for row in check.execute(select(tables.TB_OPER_BNDL.c.SITE_ID)).all()}
        assert "commit-site" in sites
        assert "fail-site" not in sites  # 실패한 요청의 쓰기는 남지 않는다
    finally:
        with migrated_engine.begin() as cleanup:
            cleanup.execute(
                tables.TB_OPER_BNDL.delete().where(tables.TB_OPER_BNDL.c.SITE_ID == "commit-site")
            )


def test_재전송을_받아도_같은_트랜잭션의_앞선_쓰기는_남는다(session: Session, factory: RowFactory) -> None:
    """중복 삽입이 실패해도 그 앞에서 한 쓰기를 되돌리지 않는다(저장점 없이도 InnoDB가 보장)."""
    marker = factory.make("TB_OPER_BNDL", SITE_ID="before-replay")
    values = _apply_values(factory, "key-5")
    insert_idempotent(session, tables.TB_ATNLC_APLY, values, lambda row: True)
    _, replayed = insert_idempotent(session, tables.TB_ATNLC_APLY, values, lambda row: True)
    assert replayed
    still = session.execute(
        select(tables.TB_OPER_BNDL.c.SITE_ID).where(tables.TB_OPER_BNDL.c.SITE_ID == "before-replay")
    ).scalar_one()
    assert still == "before-replay"
    assert marker["OPER_BNDL_SN"] > 0


def test_엔진은_접속마다_UTC로_고정하도록_만든다(monkeypatch: pytest.MonkeyPatch) -> None:
    """서버 기본이 UTC가 아닌 배포를 막으려는 접속 설정이 엔진에 전달되는지 본다."""
    captured: dict[str, Any] = {}

    def fake_create_engine(url: str, **kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)
    session_module.create_db_engine(Settings(database_url="mysql+pymysql://u:p@h/db", site_id="x"))
    assert captured["connect_args"]["init_command"] == "SET time_zone = '+00:00'"
    assert captured["pool_pre_ping"] is True


def test_실제_연결의_세션_시간대는_UTC다(migrated_engine: Engine) -> None:
    from sqlalchemy import text

    engine = session_module.create_db_engine(
        Settings(database_url=migrated_engine.url.render_as_string(hide_password=False), site_id="x")
    )
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT @@session.time_zone")).scalar_one() == "+00:00"
    finally:
        engine.dispose()


def test_예상하지_못한_오류는_응답에_내용을_싣지_않고_로그에도_값을_남기지_않는다(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("SELECT * FROM TB_MBR WHERE PHONE='010-1234-5678'")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        response = client.get("/boom")
    assert response.status_code == 500
    assert "SELECT" not in response.text and "010-1234" not in response.text
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in logged  # 무슨 종류인지와 요청 번호만 남긴다
    assert response.headers["X-Request-ID"] in logged
    assert "010-1234" not in logged and "TB_MBR" not in logged
