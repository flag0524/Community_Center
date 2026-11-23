# 준정적 조회 TTL 캐시의 동작과 주민 화면 조회에서의 적용, 설정값을 확인하는 시험(ADR-114)
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import ConfigError, Settings, load_settings
from app.core.ttl_cache import MAX_ENTRIES, TtlCache
from app.domain.course import service as course_service
from app.domain.site import service as site_service
from tests.test_courses_public import cycle, get
from tests.world import MEMBER, World

BASE = {
    "JORI_DATABASE_URL": "mysql+pymysql://u:p@127.0.0.1:3306/x",
    "JORI_SITE_ID": "t",
    "JORI_SECRET_KEY": "k" * 40,
}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def counting() -> tuple[list[int], Any]:
    calls: list[int] = []

    def loader() -> int:
        calls.append(1)
        return len(calls)

    return calls, loader


# --- 캐시 자체(DB 없이) -------------------------------------------------------------------------


def test_유효_시간_안에는_다시_읽지_않고_지나면_다시_읽는다() -> None:
    clock = Clock()
    cache = TtlCache(clock)
    cache.configure(30)
    calls, loader = counting()
    assert cache.get_or_load("k", loader) == 1
    clock.now += 29.9
    assert cache.get_or_load("k", loader) == 1 and len(calls) == 1
    clock.now += 0.2  # 30.1초
    assert cache.get_or_load("k", loader) == 2 and len(calls) == 2


def test_0이면_꺼져_있어_늘_읽는다() -> None:
    cache = TtlCache(Clock())
    calls, loader = counting()
    assert [cache.get_or_load("k", loader) for _ in range(3)] == [1, 2, 3] and len(calls) == 3
    cache.configure(0)
    assert [cache.get_or_load("k", loader) for _ in range(2)] == [4, 5]


def test_키마다_따로_쥐고_비우면_다시_읽는다() -> None:
    cache = TtlCache(Clock())
    cache.configure(30)
    calls, loader = counting()
    assert (cache.get_or_load("a", loader), cache.get_or_load("b", loader)) == (1, 2)
    assert (cache.get_or_load("a", loader), cache.get_or_load("b", loader)) == (1, 2)
    cache.clear()
    assert cache.get_or_load("a", loader) == 3


def test_실패한_읽기는_담지_않고_없음_값은_담는다() -> None:
    cache = TtlCache(Clock())
    cache.configure(30)
    tries: list[int] = []

    def flaky() -> int:
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("DB 오류")
        return 7

    with pytest.raises(RuntimeError):
        cache.get_or_load("k", flaky)
    assert cache.get_or_load("k", flaky) == 7 and len(tries) == 2  # 실패 뒤 바로 다시 읽었다
    nones: list[int] = []

    def nothing() -> None:
        nones.append(1)

    assert cache.get_or_load("n", nothing) is None and cache.get_or_load("n", nothing) is None
    assert len(nones) == 1  # 값이 없다는 결과도 유효 시간 동안 쥔다


def test_항목이_한도를_넘으면_비워_메모리가_늘지_않는다() -> None:
    cache = TtlCache(Clock())
    cache.configure(30)
    for n in range(MAX_ENTRIES + 5):
        cache.get_or_load(n, lambda n=n: n)  # type: ignore[misc]
    assert len(cache._items) <= MAX_ENTRIES


# --- 설정 ---------------------------------------------------------------------------------------


def test_캐시_유효_시간은_기본_30초이고_환경변수로_바꾸며_음수는_거절한다() -> None:
    assert load_settings(BASE).cache_ttl_seconds == 30
    assert load_settings({**BASE, "JORI_CACHE_TTL_SECONDS": "0"}).cache_ttl_seconds == 0
    assert load_settings({**BASE, "JORI_CACHE_TTL_SECONDS": "120"}).cache_ttl_seconds == 120
    with pytest.raises(ConfigError):
        Settings(database_url=BASE["JORI_DATABASE_URL"], site_id="t", cache_ttl_seconds=-1)


# --- 주민 화면 조회에 적용 -----------------------------------------------------------------------


@pytest.fixture
def cached(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TtlCache, Clock]]:
    clock = Clock()
    cache = TtlCache(clock)
    cache.configure(30)
    monkeypatch.setattr(course_service, "CACHE", cache)
    monkeypatch.setattr(site_service, "CACHE", cache)
    yield cache, clock


@pytest.mark.db
def test_강좌_분류는_유효_시간_안에는_바뀐_값을_못_보고_지나면_본다(
    world: World, cached: tuple[TtlCache, Clock]
) -> None:
    _, clock = cached
    admin = world.factory.make("TB_MNGR", LGN_ID="cat-admin", PSWD_HASH_VL="x" * 20, MNGR_NM="관리")[
        "MNGR_SN"
    ]
    world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="문화", CLSF_NM_KEY="문화", SORT_SEQ=1, REG_MNGR_SN=admin)
    assert [i["name"] for i in get(world, "/categories").json()["items"]] == ["문화"]
    world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="건강", CLSF_NM_KEY="건강", SORT_SEQ=2, REG_MNGR_SN=admin)
    assert [i["name"] for i in get(world, "/categories").json()["items"]] == ["문화"]  # 아직 옛 목록
    clock.now += 31
    assert [i["name"] for i in get(world, "/categories").json()["items"]] == ["문화", "건강"]


@pytest.mark.db
def test_현재_기수는_날짜가_바뀌면_다시_고른다(world: World, cached: tuple[TtlCache, Clock]) -> None:
    cycle(world, "끝난기수", EDU_BGNG_YMD="20260901", EDU_END_YMD="20261108")
    cycle(world, "다음기수", EDU_CYCL=5, EDU_BGNG_YMD="20261110", EDU_END_YMD="20261231")
    now = world.clock.now
    first = course_service.current_cycle(world.db, world.bundle, now)
    assert first.EDU_CYCL_NM == "다음기수"  # 11월 9일 현재 끝나지 않은 기수 중 가장 이른 것
    cached_again = course_service.current_cycle(world.db, world.bundle, now)
    assert cached_again is first  # 같은 날 유효 시간 안에는 같은 값을 쥔다
    world.db.execute(text("UPDATE TB_EDU_CYCL SET USE_YN='N' WHERE EDU_CYCL_NM='다음기수'"))
    assert course_service.current_cycle(world.db, world.bundle, now).EDU_CYCL_NM == "다음기수"
    tomorrow = now + timedelta(days=1)
    assert (
        course_service.current_cycle(world.db, world.bundle, tomorrow).EDU_CYCL_NM == "끝난기수"
    )  # 날짜가 키다


@pytest.mark.db
def test_센터_연락처의_기본_전화는_유효_시간_뒤에_바뀐_값을_본다(
    world: World, cached: tuple[TtlCache, Clock]
) -> None:
    _, clock = cached
    world.db.execute(
        text("UPDATE TB_OPER_BNDL SET TELNO='0311111111' WHERE OPER_BNDL_SN=:b"), {"b": world.bundle}
    )
    assert world.client.get(f"{MEMBER}/site/contact").json()["phone"] == "0311111111"
    world.db.execute(
        text("UPDATE TB_OPER_BNDL SET TELNO='0312222222' WHERE OPER_BNDL_SN=:b"), {"b": world.bundle}
    )
    assert world.client.get(f"{MEMBER}/site/contact").json()["phone"] == "0311111111"
    clock.now += 31
    assert world.client.get(f"{MEMBER}/site/contact").json()["phone"] == "0312222222"


@pytest.mark.db
def test_다른_운영묶음의_분류가_캐시를_통해_섞이지_않는다(
    world: World, cached: tuple[TtlCache, Clock]
) -> None:
    admin = world.factory.make("TB_MNGR", LGN_ID="mix-admin", PSWD_HASH_VL="x" * 20, MNGR_NM="관리")[
        "MNGR_SN"
    ]
    other = world.factory.make("TB_OPER_BNDL")["OPER_BNDL_SN"]
    world.factory.make("TB_CORS_CLSF", CORS_CLSF_NM="우리", CLSF_NM_KEY="우리", REG_MNGR_SN=admin)
    world.factory.make(
        "TB_CORS_CLSF", OPER_BNDL_SN=other, CORS_CLSF_NM="남의", CLSF_NM_KEY="남의", REG_MNGR_SN=admin
    )
    mine = [c.name for c in course_service.list_categories(world.db, world.bundle).items]
    theirs = [c.name for c in course_service.list_categories(world.db, int(other)).items]
    assert (mine, theirs) == (["우리"], ["남의"])
    again = [c.name for c in course_service.list_categories(world.db, world.bundle).items]
    assert again == ["우리"]
