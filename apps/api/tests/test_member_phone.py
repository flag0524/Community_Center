# 휴대전화번호 암호문·검색해시 변환과 가입한 번호가 DB에 평문으로 남지 않는지 보는 시험(스키마 v0.8)
import pytest
from sqlalchemy import select, text

from app.auth.crypto import DecryptError
from app.auth.member_phone import ENCRYPTED, SEARCH_HASH, reveal, sealed_columns, search_hash
from app.auth.otp import phone_hash
from app.db.tables import TB_MBR
from tests.factory import TEST_SECRET
from tests.test_join_recovery import agreements, issue_join, join, publish_defaults
from tests.test_otp import PHONE
from tests.world import World

SECRET = "k" * 40


# --- 변환 함수(DB 없이) -------------------------------------------------------------------------


def test_봉한_번호는_평문이_보이지_않고_되돌리면_같은_번호다() -> None:
    sealed = sealed_columns(SECRET, "01012345678")
    assert set(sealed) == {ENCRYPTED, SEARCH_HASH}
    assert "01012345678" not in str(sealed[ENCRYPTED]) and "01012345678" not in str(sealed[SEARCH_HASH])
    assert reveal(SECRET, sealed[ENCRYPTED]) == "01012345678"


def test_같은_번호도_암호문은_매번_다르고_검색해시는_늘_같다() -> None:
    first, second = sealed_columns(SECRET, "01012345678"), sealed_columns(SECRET, "01012345678")
    assert first[ENCRYPTED] != second[ENCRYPTED]
    assert first[SEARCH_HASH] == second[SEARCH_HASH] == search_hash(SECRET, "01012345678")
    assert len(first[SEARCH_HASH]) == 64


def test_다른_번호와_다른_비밀키는_다른_검색해시를_만든다() -> None:
    assert search_hash(SECRET, "01012345678") != search_hash(SECRET, "01012345679")
    assert search_hash(SECRET, "01012345678") != search_hash("j" * 40, "01012345678")


def test_회원_검색해시는_OTP_검색해시와_통하지_않는다() -> None:
    # 용도별 파생키라서 한쪽 테이블의 값을 다른 쪽과 대조해 번호를 알아낼 수 없다
    assert search_hash(SECRET, "01012345678") != phone_hash(SECRET, "01012345678")


@pytest.mark.parametrize("empty", [None, ""])
def test_번호가_없으면_암호문도_해시도_없다(empty: str | None) -> None:
    assert sealed_columns(SECRET, empty) == {ENCRYPTED: None, SEARCH_HASH: None}
    assert reveal(SECRET, empty) is None


def test_다른_키로는_풀리지_않고_변조된_값은_거절한다() -> None:
    token = str(sealed_columns(SECRET, "01012345678")[ENCRYPTED])
    with pytest.raises(DecryptError):
        reveal("j" * 40, token)
    with pytest.raises(DecryptError):
        reveal(SECRET, token[:-4] + "AAAA")


# --- 실제 앱과 MariaDB -------------------------------------------------------------------------


@pytest.mark.db
def test_가입한_번호는_회원_행의_어느_컬럼에도_평문으로_없다(world: World) -> None:
    publish_defaults(world)
    cert, code = issue_join(world)
    assert join(world, cert, code, agreements=agreements()).status_code == 201
    row = world.db.execute(select(TB_MBR).where(TB_MBR.c.LGN_ID == "newbie")).one()
    assert PHONE not in " ".join(str(value) for value in row)
    assert search_hash(TEST_SECRET, PHONE) == row.MBL_TELNO_SRCH_HASH_VL
    assert reveal(TEST_SECRET, row.MBL_TELNO_ENCPT_VL) == PHONE


@pytest.mark.db
def test_회원과_관리자_테이블에_평문_전화번호_컬럼이_없다(world: World) -> None:
    columns = {
        (table, column)
        for table, column in world.db.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME LIKE 'MBL\\_TELNO%'"
            )
        ).all()
    }
    assert columns == {
        ("TB_MBR", "MBL_TELNO_ENCPT_VL"),
        ("TB_MBR", "MBL_TELNO_SRCH_HASH_VL"),
        ("TB_MNGR", "MBL_TELNO_ENCPT_VL"),
    }
