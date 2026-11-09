# 인증·OTP 시험이 함께 쓰는 세계 구성(시계, 시험 DB 세션, 설정, 회원·관리자 생성, 로그인 도우미)
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.sms.mock import MockSmsSender
from app.auth import deps as auth_deps
from app.auth.passwords import hash_password
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
from app.tools.schema_doc import SchemaDoc
from tests.factory import RowFactory

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


class FixedBundle:
    """시험이 정한 운영묶음을 돌려주는 해석기. 사이트 식별자로 찾는 실제 해석은 별도로 시험한다."""

    def __init__(self, bundle_sn: int) -> None:
        self.bundle_sn = bundle_sn

    def resolve(self, db: Session) -> int:
        return self.bundle_sn


@dataclass
class World:
    client: TestClient
    clock: FakeClock
    db: Session
    factory: RowFactory
    bundle: int
    settings: Settings
    sms: MockSmsSender  # 보낸 문자를 담는다. 인증번호는 여기서만 읽을 수 있다(DB에는 남지 않는다)


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
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[auth_deps.get_clock] = lambda: clock
        app.dependency_overrides[auth_deps.get_bundle_resolver] = lambda: FixedBundle(bundle)
        sms = MockSmsSender()
        app.dependency_overrides[auth_deps.get_sms_sender] = lambda: sms
        # base_url을 https로 해야 Secure 쿠키가 다시 실린다
        client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
        yield World(client, clock, db, factory, bundle, settings, sms)
        db.close()
        outer.rollback()


def make_member(w: World, login_id: str = "member1", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": w.bundle,
        "LGN_ID": login_id,
        "PSWD_HASH_VL": hash_password(PASSWORD, ITERATIONS),
        "MBR_NM": "김회원",
    }
    return w.factory.make("TB_MBR", **{**defaults, **values})  # 시험이 넘긴 값이 기본값을 이긴다


def make_admin(w: World, login_id: str = "admin1", **values: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "LGN_ID": login_id,
        "PSWD_HASH_VL": hash_password(PASSWORD, ITERATIONS),
        "MNGR_NM": "김관리",
    }
    return w.factory.make("TB_MNGR", **{**defaults, **values})


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
