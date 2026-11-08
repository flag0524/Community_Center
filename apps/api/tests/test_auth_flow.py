# 회원·관리자 로그인, 세션 쿠키·CSRF, 실패 잠금, 유휴 만료, 로그아웃을 실제 앱과 MariaDB로 확인하는 시험
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.auth import deps as auth_deps
from app.auth import passwords
from app.auth.passwords import hash_password
from app.core.config import Settings
from app.db import tables
from app.db.session import get_db
from app.main import create_app
from app.tools.schema_doc import SchemaDoc, parse_schema_doc
from tests.factory import RowFactory

pytestmark = pytest.mark.db

PASSWORD = "Correct-Horse-9"
ITERATIONS = 1000  # 시험에서는 빠르게. 운영 기본값은 600,000이다.
START = datetime(2026, 11, 9, 9, 0, 0)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


@dataclass
class World:
    client: TestClient
    clock: FakeClock
    db: Session
    factory: RowFactory
    bundle: int
    settings: Settings


@pytest.fixture(scope="module")
def schema() -> SchemaDoc:
    return parse_schema_doc()


def build_world(engine: Engine, schema: SchemaDoc, settings: Settings | None = None) -> Iterator[World]:
    clock = FakeClock()
    settings = settings or Settings(
        database_url="unused", site_id="test-site", secret_key="s" * 40, pbkdf2_iterations=ITERATIONS
    )
    with engine.connect() as connection:
        outer = connection.begin()
        db = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False, autoflush=False
        )
        factory = RowFactory(connection, schema)
        bundle = factory.bundle()
        app = create_app()

        def override_db() -> Iterator[Session]:
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[auth_deps.get_settings] = lambda: settings
        app.dependency_overrides[auth_deps.get_clock] = lambda: clock
        app.dependency_overrides[auth_deps.get_bundle] = lambda: bundle
        # base_url을 https로 해야 Secure 쿠키가 다시 실린다
        client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
        yield World(client, clock, db, factory, bundle, settings)
        db.close()
        outer.rollback()


@pytest.fixture()
def world(migrated_engine: Engine, schema: SchemaDoc) -> Iterator[World]:
    yield from build_world(migrated_engine, schema)


def make_member(w: World, login_id: str = "member1", **values: Any) -> dict[str, Any]:
    return w.factory.make(
        "TB_MBR",
        OPER_BNDL_SN=w.bundle,
        LGN_ID=login_id,
        PSWD_HASH_VL=hash_password(PASSWORD, ITERATIONS),
        MBR_NM="김회원",
        **values,
    )


def make_admin(w: World, login_id: str = "admin1", **values: Any) -> dict[str, Any]:
    return w.factory.make(
        "TB_MNGR",
        LGN_ID=login_id,
        PSWD_HASH_VL=hash_password(PASSWORD, ITERATIONS),
        MNGR_NM="김관리",
        **values,
    )


def anonymous_token(client: TestClient, base: str) -> str:
    """로그인 전 세션 조회가 시드 쿠키와 CSRF 토큰을 내려 준다(프런트가 로그인 전에 하는 일)."""
    body = client.get(f"{base}/auth/session").json()
    assert body["authenticated"] is False
    return str(body["csrfToken"])


def login(w: World, base: str, login_id: str, password: str = PASSWORD, token: str | None = None) -> Any:
    token = token if token is not None else anonymous_token(w.client, base)
    return w.client.post(
        f"{base}/auth/login",
        json={"loginId": login_id, "password": password},
        headers={"X-CSRF-Token": token},
    )


MEMBER = "/api/v1"
ADMIN = "/api/admin/v1"


def cookie_header(response: Any, name: str) -> str:
    """응답에는 쿠키가 여러 개 실린다(세션 쿠키, 로그인 전 시드 쿠키 삭제). 이름으로 정확히 하나를 고른다."""
    matches = [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{name}=")]
    assert len(matches) == 1, (name, response.headers.get_list("set-cookie"))
    return str(matches[0])


# --- 로그인과 세션 ---------------------------------------------------------


def test_회원_로그인은_세션_쿠키와_CSRF_토큰을_주고_세션_조회가_같은_값을_돌려준다(world: World) -> None:
    member = make_member(world)
    response = login(world, MEMBER, "member1")
    assert response.status_code == 200
    body = response.json()
    assert (body["authenticated"], body["member"]["name"], body["idleTimeoutSeconds"]) == (
        True,
        "김회원",
        1800,
    )
    assert body["member"]["memberId"] == str(member["MBR_SN"])
    cookie = cookie_header(response, "jori_session")
    assert "HttpOnly" in cookie and "Secure" in cookie
    assert "; Path=/;" in f"{cookie};"  # 쿠키 경로가 좁혀지지 않았다(화면 경로에서도 실린다)
    assert "samesite=lax" in cookie.lower()
    assert "max-age" not in cookie.lower() and "expires" not in cookie.lower()  # 브라우저를 닫으면 사라진다
    seed = cookie_header(response, "jori_csrf_seed")  # 로그인 전 시드 쿠키는 로그인과 함께 지운다
    assert "max-age=0" in seed.lower() and "HttpOnly" in seed

    again = world.client.get(f"{MEMBER}/auth/session").json()
    assert again["authenticated"] is True and again["csrfToken"] == body["csrfToken"]


def test_세션_토큰_원문은_저장되지_않고_해시만_저장된다(world: World) -> None:
    make_member(world)
    login(world, MEMBER, "member1")
    raw = world.client.cookies.get("jori_session")
    assert raw and len(raw) >= 40  # 256비트 토큰
    stored = world.db.execute(select(tables.TB_LGN_SSN.c.TKN_HASH_VL)).scalars().all()
    assert len(stored) == 1 and stored[0] != raw and len(stored[0]) == 64
    dump = world.db.execute(text("SELECT CONCAT_WS('|', TKN_HASH_VL, DSCD_RSN) FROM TB_LGN_SSN")).scalar_one()
    assert raw not in str(dump)


def test_로그아웃하면_세션이_폐기되고_쿠키가_지워지며_다시_불러도_같은_결과다(world: World) -> None:
    make_member(world)
    token = login(world, MEMBER, "member1").json()["csrfToken"]
    first = world.client.post(f"{MEMBER}/auth/logout", headers={"X-CSRF-Token": token})
    assert first.status_code == 204
    cleared = cookie_header(first, "jori_session")
    assert "max-age=0" in cleared.lower() and "HttpOnly" in cleared and "Secure" in cleared
    assert "; Path=/;" in f"{cleared};"  # 발급할 때와 같은 경로여야 지워진다
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False
    row = world.db.execute(select(tables.TB_LGN_SSN.c.DSCD_DT, tables.TB_LGN_SSN.c.DSCD_RSN)).one()
    assert row.DSCD_DT is not None and row.DSCD_RSN == "LOGOUT"
    again = world.client.post(
        f"{MEMBER}/auth/logout", headers={"X-CSRF-Token": anonymous_token(world.client, MEMBER)}
    )
    assert again.status_code == 204  # 멱등


def test_폐기된_세션_토큰을_다시_써도_인증되지_않는다(world: World) -> None:
    make_member(world)
    token = login(world, MEMBER, "member1").json()["csrfToken"]
    stolen = world.client.cookies.get("jori_session")
    world.client.post(f"{MEMBER}/auth/logout", headers={"X-CSRF-Token": token})
    world.client.cookies.set("jori_session", stolen or "", domain="testserver.local")
    world.client.cookies.set("jori_session", stolen or "")
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False


# --- 실패와 잠금 -----------------------------------------------------------


def fail(w: World, login_id: str = "member1", times: int = 1) -> list[Any]:
    return [login(w, MEMBER, login_id, "wrong-password") for _ in range(times)]


def test_틀린_비밀번호는_401이고_실패_이력이_응답이_오류여도_남는다(world: World) -> None:
    member = make_member(world)
    response = fail(world)[0]
    assert response.status_code == 401 and response.json()["code"] == "LOGIN_FAILED"
    assert "wrong-password" not in response.text
    count = world.db.execute(select(func.count()).select_from(tables.TB_LGN_FAIL_HSTRY)).scalar_one()
    assert count == 1
    saved = world.db.execute(
        select(tables.TB_MBR.c.PSWD_FAIL_NMTM).where(tables.TB_MBR.c.MBR_SN == member["MBR_SN"])
    ).scalar_one()
    assert int(saved) == 1


def test_직전_10분_안에_5번_틀리면_15분_동안_잠기고_맞는_비밀번호도_막는다(world: World) -> None:
    member = make_member(world)
    responses = fail(world, times=5)
    assert [r.status_code for r in responses] == [401, 401, 401, 401, 429]
    assert responses[-1].json()["code"] == "LOGIN_LOCKED"
    locked_until = world.db.execute(
        select(tables.TB_MBR.c.LCK_END_DT).where(tables.TB_MBR.c.MBR_SN == member["MBR_SN"])
    ).scalar_one()
    assert locked_until == START + timedelta(minutes=15)
    assert (
        login(world, MEMBER, "member1", PASSWORD).json()["code"] == "LOGIN_LOCKED"
    )  # 맞는 비밀번호도 막힌다
    world.clock.advance(minutes=14, seconds=59)
    assert login(world, MEMBER, "member1", PASSWORD).status_code == 429
    world.clock.advance(seconds=2)
    ok = login(world, MEMBER, "member1", PASSWORD)
    assert ok.status_code == 200  # 잠금이 끝나면 들어갈 수 있다
    reset = world.db.execute(
        select(tables.TB_MBR.c.PSWD_FAIL_NMTM, tables.TB_MBR.c.LCK_END_DT).where(
            tables.TB_MBR.c.MBR_SN == member["MBR_SN"]
        )
    ).one()
    assert (int(reset.PSWD_FAIL_NMTM), reset.LCK_END_DT) == (0, None)  # 성공하면 횟수가 지워진다


def test_10분이_지난_실패는_세지_않는다(world: World) -> None:
    make_member(world)
    fail(world, times=4)
    world.clock.advance(minutes=10, seconds=1)  # 앞의 4번은 구간 밖
    last = fail(world)[0]
    assert last.status_code == 401  # 5번째가 아니라 구간 안 1번째다
    assert login(world, MEMBER, "member1", PASSWORD).status_code == 200


def test_없는_아이디와_탈퇴_계정은_같은_응답이고_실패_이력도_남기지_않고_같은_계산을_한다(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_member(world, "gone", MBR_STTS_CD="MS.WITHDRAW")
    make_member(world, "real")
    calls: list[str] = []
    original = passwords.verify_password

    def spy(password: str, encoded: str) -> bool:
        calls.append(encoded)
        return original(password, encoded)

    monkeypatch.setattr("app.auth.login.verify_password", spy)
    unknown = login(world, MEMBER, "nobody", "x")
    withdrawn = login(world, MEMBER, "gone", PASSWORD)  # 비밀번호가 맞아도 탈퇴 계정은 들어갈 수 없다
    wrong = login(world, MEMBER, "real", "x")
    assert (unknown.status_code, withdrawn.status_code, wrong.status_code) == (401, 401, 401)
    assert unknown.json()["message"] == withdrawn.json()["message"] == wrong.json()["message"]
    assert len(calls) == 3  # 계정이 없어도 비밀번호 검증 계산을 한다
    assert calls[0].startswith("pbkdf2_sha256$")
    failures = world.db.execute(select(func.count()).select_from(tables.TB_LGN_FAIL_HSTRY)).scalar_one()
    assert failures == 1  # 실제 계정의 실패만 남는다


def test_관리자가_제한한_회원은_로그인할_수_없다(world: World) -> None:
    make_member(world, "restricted", MBR_STTS_CD="MS.LOCKED")
    assert login(world, MEMBER, "restricted").json()["code"] == "LOGIN_LOCKED"


# --- 유휴 만료 ---------------------------------------------------------------


def test_회원_세션은_30분_유휴에_만료되고_조회만으로는_연장되지_않는다(world: World) -> None:
    make_member(world)
    login(world, MEMBER, "member1")
    world.clock.advance(minutes=29, seconds=59)
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is True
    world.clock.advance(seconds=2)  # 조회가 연장했다면 아직 살아 있었을 것이다
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False


def test_계정이_탈퇴하거나_제한되면_살아_있는_세션도_인증되지_않는다(world: World) -> None:
    member = make_member(world)
    login(world, MEMBER, "member1")
    world.db.execute(
        update(tables.TB_MBR)
        .where(tables.TB_MBR.c.MBR_SN == member["MBR_SN"])
        .values(MBR_STTS_CD="MS.WITHDRAW")
    )
    assert world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False


# --- CSRF ------------------------------------------------------------------


def test_CSRF_토큰이_없거나_틀리면_로그인도_로그아웃도_403이다(world: World) -> None:
    make_member(world)
    world.client.get(f"{MEMBER}/auth/session")
    no_header = world.client.post(f"{MEMBER}/auth/login", json={"loginId": "member1", "password": PASSWORD})
    wrong = login(world, MEMBER, "member1", token="0" * 64)
    assert (no_header.status_code, wrong.status_code) == (403, 403)
    assert no_header.json()["code"] == "FORBIDDEN"
    assert (
        world.db.execute(select(func.count()).select_from(tables.TB_LGN_SSN)).scalar_one() == 0
    )  # 세션이 만들어지지 않았다


def test_시드_쿠키_없이_보낸_토큰은_통하지_않는다(world: World) -> None:
    make_member(world)
    token = anonymous_token(world.client, MEMBER)
    world.client.cookies.clear()
    assert (
        login(world, MEMBER, "member1", token=token).status_code == 403
    )  # 더블 서브밋이라 쿠키가 같이 와야 한다


def test_로그인한_뒤_상태_변경은_세션의_CSRF_토큰이_필요하고_다른_세션의_토큰은_통하지_않는다(
    world: World,
) -> None:
    make_member(world, "a")
    make_member(world, "b")
    token_a = login(world, MEMBER, "a").json()["csrfToken"]
    world.client.cookies.clear()
    login(world, MEMBER, "b")
    other = world.client.post(f"{MEMBER}/auth/logout", headers={"X-CSRF-Token": token_a})
    assert other.status_code == 403  # 다른 사람 세션에서 얻은 토큰
    assert (
        world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is True
    )  # 막혔으니 로그아웃되지 않았다


# --- 관리자 ----------------------------------------------------------------


def test_관리자_로그인은_관리자_쿠키를_쓰고_회원_쿠키로는_인증되지_않는다(world: World) -> None:
    make_admin(world)
    response = login(world, ADMIN, "admin1")
    assert response.status_code == 200
    assert response.json()["idleTimeoutSeconds"] == 900 and response.json()["admin"]["name"] == "김관리"
    admin_cookie = cookie_header(response, "jori_admin_session")
    assert "HttpOnly" in admin_cookie and "Secure" in admin_cookie and "samesite=lax" in admin_cookie.lower()
    assert world.client.cookies.get("jori_session") is None  # 주민 쿠키 이름은 쓰지 않는다
    assert (
        world.client.get(f"{MEMBER}/auth/session").json()["authenticated"] is False
    )  # 관리자 세션은 주민 API에서 인증 안 됨


def test_회원_세션은_관리자_API에서_인증되지_않는다(world: World) -> None:
    make_member(world)
    make_admin(world)
    login(world, MEMBER, "member1")
    member_cookie = world.client.cookies.get("jori_session")
    world.client.cookies.clear()
    world.client.cookies.set(
        "jori_admin_session", member_cookie or ""
    )  # 회원 토큰을 관리자 쿠키 이름으로 보내도
    assert world.client.get(f"{ADMIN}/auth/session").json()["authenticated"] is False


def test_관리자_세션은_15분_유휴에_만료되고_연장하면_처음부터_다시_센다(world: World) -> None:
    make_admin(world)
    first = login(world, ADMIN, "admin1").json()
    token = first["csrfToken"]
    world.clock.advance(minutes=14)
    extended = world.client.post(f"{ADMIN}/auth/extend", headers={"X-CSRF-Token": token})
    assert extended.status_code == 200
    assert extended.json()["expiresAt"] > first["expiresAt"]  # 만료 시각이 뒤로 밀린다
    world.clock.advance(minutes=14)  # 연장 없이 처음 로그인 기준이면 이미 만료
    assert world.client.get(f"{ADMIN}/auth/session").json()["authenticated"] is True
    world.clock.advance(minutes=2)
    assert world.client.get(f"{ADMIN}/auth/session").json()["authenticated"] is False


def test_만료된_세션은_연장할_수_없다(world: World) -> None:
    make_admin(world)
    token = login(world, ADMIN, "admin1").json()["csrfToken"]
    world.clock.advance(minutes=16)
    response = world.client.post(f"{ADMIN}/auth/extend", headers={"X-CSRF-Token": token})
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"


def test_관리자_잠금_수치가_정해지지_않았으면_몇_번을_틀려도_잠그지_않는다(world: World) -> None:
    admin = make_admin(world)
    statuses = [login(world, ADMIN, "admin1", "wrong").status_code for _ in range(8)]
    assert set(statuses) == {401}  # Q28 전에는 수치를 지어내지 않는다
    assert login(world, ADMIN, "admin1").status_code == 200
    failures = world.db.execute(
        select(func.count())
        .select_from(tables.TB_LGN_FAIL_HSTRY)
        .where(tables.TB_LGN_FAIL_HSTRY.c.MNGR_SN == admin["MNGR_SN"])
    ).scalar_one()
    assert failures == 8  # 이력은 남긴다


def test_관리자_잠금_수치를_설정하면_그대로_적용한다(migrated_engine: Engine, schema: SchemaDoc) -> None:
    settings = Settings(
        database_url="unused", site_id="s", secret_key="s" * 40, pbkdf2_iterations=ITERATIONS,
        admin_lock_failures=3, admin_lock_minutes=20,
    )  # fmt: skip
    for w in build_world(migrated_engine, schema, settings):
        make_admin(w)
        statuses = [login(w, ADMIN, "admin1", "wrong").status_code for _ in range(3)]
        assert statuses == [401, 401, 429]
        assert login(w, ADMIN, "admin1").status_code == 429
        w.clock.advance(minutes=20, seconds=1)
        assert login(w, ADMIN, "admin1").status_code == 200


def test_사용_중지된_관리자는_로그인할_수_없다(world: World) -> None:
    make_admin(world, "off", USE_YN="N")
    assert login(world, ADMIN, "off").status_code == 401


def test_요청_본문과_로그에_비밀번호가_남지_않는다(world: World, caplog: pytest.LogCaptureFixture) -> None:
    make_member(world)
    import logging

    with caplog.at_level(logging.DEBUG):
        login(world, MEMBER, "member1", "wrong-password")
        login(world, MEMBER, "member1", PASSWORD)
    text_logged = " ".join(r.getMessage() for r in caplog.records)
    assert "wrong-password" not in text_logged and PASSWORD not in text_logged


def test_세션_쿠키_이름과_기본_속성이_계약과_같다() -> None:
    assert auth_deps.COOKIE_NAMES == {"member": "jori_session", "admin": "jori_admin_session"}
    assert auth_deps.SEED_COOKIE_NAMES["member"] != auth_deps.SEED_COOKIE_NAMES["admin"]


def test_로그인_전_시드_쿠키도_HttpOnly_Secure_SameSite이고_회원과_관리자가_다르다(world: World) -> None:
    member = world.client.get(f"{MEMBER}/auth/session")
    seed = cookie_header(member, "jori_csrf_seed")
    assert "HttpOnly" in seed and "Secure" in seed and "samesite=lax" in seed.lower()
    admin = world.client.get(f"{ADMIN}/auth/session")
    assert "HttpOnly" in cookie_header(admin, "jori_admin_csrf_seed")
    assert member.json()["csrfToken"] != admin.json()["csrfToken"]  # 서로의 토큰으로 상대 로그인을 할 수 없다
