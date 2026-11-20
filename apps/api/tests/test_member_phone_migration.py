# 0005 이행(평문 휴대전화번호를 암호문·검색해시로 바꾸고 평문 컬럼 삭제)과 되돌리기를 실제 DB로 보는 시험
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app.auth.member_phone import reveal, search_hash
from tests.arena import Arena, make_member
from tests.conftest import API_DIR
from tests.factory import TEST_SECRET, RowFactory

pytestmark = pytest.mark.db

PHONE = "01012345678"
LEGACY = "01077778888"
MANAGER_PHONE = "01099990000"


def migrate(arena: Arena, action: str, revision: str) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    with arena.migrated.connect() as connection:
        config.attributes["connection"] = connection
        getattr(command, action)(config, revision)
        connection.commit()


def has_column(arena: Arena, table: str, column: str) -> bool:
    return bool(
        arena.query(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :t AND COLUMN_NAME = :c",
            t=table,
            c=column,
        )
    )


@pytest.fixture()
def keyed(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> Iterator[Arena]:
    """시험이 끝나면 어떤 경우에도 DB를 최신(0005) 버전으로 되돌려 놓는다."""
    monkeypatch.setenv("JORI_SECRET_KEY", TEST_SECRET)
    yield arena
    monkeypatch.setenv("JORI_SECRET_KEY", TEST_SECRET)
    migrate(arena, "upgrade", "head")


def build(arena: Arena) -> tuple[int, int, int]:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        with_phone = make_member(f, bundle, "with-phone")
        no_phone = int(
            f.make("TB_MBR", OPER_BNDL_SN=bundle, LGN_ID="no-phone", PSWD_HASH_VL="x" * 20, MBR_NM="없음")[
                "MBR_SN"
            ]
        )
        manager = int(
            f.make(
                "TB_MNGR", LGN_ID="mig-mgr", PSWD_HASH_VL="x" * 20, MNGR_NM="관리", MBL_TELNO=MANAGER_PHONE
            )["MNGR_SN"]
        )
        arena.admins.append(manager)
        return with_phone, no_phone, manager

    ids: tuple[int, int, int] = arena.build(make)
    return ids


def member(arena: Arena, sn: int, column: str) -> Any:
    return arena.query(f"SELECT {column} v FROM TB_MBR WHERE MBR_SN = :m", m=sn)[0]["v"]


def test_되돌리면_평문이_복원되고_다시_올리면_암호문과_해시로_채워진다(keyed: Arena) -> None:
    with_phone, no_phone, manager = build(keyed)

    migrate(keyed, "downgrade", "0004")
    assert not has_column(keyed, "TB_MBR", "MBL_TELNO_ENCPT_VL")
    assert not has_column(keyed, "TB_MBR", "MBL_TELNO_SRCH_HASH_VL") and not has_column(
        keyed, "TB_MNGR", "MBL_TELNO_ENCPT_VL"
    )
    assert member(keyed, with_phone, "MBL_TELNO") == PHONE and member(keyed, no_phone, "MBL_TELNO") is None
    assert (
        keyed.query("SELECT MBL_TELNO v FROM TB_MNGR WHERE MNGR_SN = :m", m=manager)[0]["v"] == MANAGER_PHONE
    )
    # 이행 전 상태(평문)의 행을 하나 더 만든다
    with keyed.migrated.begin() as connection:
        connection.execute(
            text("UPDATE TB_MBR SET MBL_TELNO = :p WHERE MBR_SN = :m"), {"p": LEGACY, "m": no_phone}
        )

    migrate(keyed, "upgrade", "head")
    assert not has_column(keyed, "TB_MBR", "MBL_TELNO") and not has_column(keyed, "TB_MNGR", "MBL_TELNO")
    for sn, phone in ((with_phone, PHONE), (no_phone, LEGACY)):
        assert (
            reveal(TEST_SECRET, member(keyed, sn, "MBL_TELNO_ENCPT_VL")) == phone
        )  # 앱이 읽는 방식으로 풀린다
        assert member(keyed, sn, "MBL_TELNO_SRCH_HASH_VL") == search_hash(
            TEST_SECRET, phone
        )  # 앱이 찾는 값과 같다
    manager_token = keyed.query("SELECT MBL_TELNO_ENCPT_VL v FROM TB_MNGR WHERE MNGR_SN = :m", m=manager)[0][
        "v"
    ]
    assert reveal(TEST_SECRET, manager_token) == MANAGER_PHONE
    assert keyed.query(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND INDEX_NAME = 'IX_MBR_04' "
        "GROUP BY INDEX_NAME HAVING GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) = "
        "'OPER_BNDL_SN,MBL_TELNO_SRCH_HASH_VL'"
    )


def test_번호가_없는_행은_이행해도_NULL로_남는다(keyed: Arena) -> None:
    _, no_phone, _ = build(keyed)
    migrate(keyed, "downgrade", "0004")
    migrate(keyed, "upgrade", "head")
    assert member(keyed, no_phone, "MBL_TELNO_ENCPT_VL") is None
    assert member(keyed, no_phone, "MBL_TELNO_SRCH_HASH_VL") is None


def test_이행에_쓰는_키가_없으면_아무것도_바꾸지_않고_중단한다(
    keyed: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(keyed)
    migrate(keyed, "downgrade", "0004")
    monkeypatch.delenv("JORI_SECRET_KEY")
    with pytest.raises(RuntimeError, match="JORI_SECRET_KEY"):
        migrate(keyed, "upgrade", "head")
    # 평문이 그대로 있고 새 컬럼은 생기지 않았다(중간에 멈춘 반쪽 상태가 아니다)
    assert has_column(keyed, "TB_MBR", "MBL_TELNO") and not has_column(keyed, "TB_MBR", "MBL_TELNO_ENCPT_VL")
    monkeypatch.setenv("JORI_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="JORI_SECRET_KEY"):
        migrate(keyed, "upgrade", "head")
    assert has_column(keyed, "TB_MBR", "MBL_TELNO")


def test_되돌릴_때도_키가_없으면_암호문을_둔_채_중단한다(
    keyed: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_phone, _, _ = build(keyed)
    monkeypatch.delenv("JORI_SECRET_KEY")
    with pytest.raises(RuntimeError, match="JORI_SECRET_KEY"):
        migrate(keyed, "downgrade", "0004")
    assert has_column(keyed, "TB_MBR", "MBL_TELNO_ENCPT_VL") and not has_column(keyed, "TB_MBR", "MBL_TELNO")
    assert reveal(TEST_SECRET, member(keyed, with_phone, "MBL_TELNO_ENCPT_VL")) == PHONE


def test_틀린_키로는_되돌릴_수_없고_평문을_만들지_않는다(
    keyed: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(keyed)
    monkeypatch.setenv("JORI_SECRET_KEY", "z" * 40)
    with pytest.raises(InvalidTag):
        migrate(keyed, "downgrade", "0004")
    # 복호화를 컬럼 변경 전에 끝내므로 반쪽 상태가 남지 않는다
    assert has_column(keyed, "TB_MBR", "MBL_TELNO_ENCPT_VL") and not has_column(keyed, "TB_MBR", "MBL_TELNO")
    assert not has_column(keyed, "TB_MNGR", "MBL_TELNO")
