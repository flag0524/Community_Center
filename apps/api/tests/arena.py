# 동시성 시험이 함께 쓰는 하네스. 커밋되는 데이터와 요청마다 따로 연 DB 연결로 실제 앱을 돌린다(ADR-038)
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.adapters.pg.mock import MockPaymentGateway
from app.auth import deps as auth_deps
from app.auth.deps import session_csrf
from app.auth.sessions import issue_session
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, get_db, open_session
from app.main import create_app
from app.routers.deps import ADMIN_SESSION_COOKIE_NAME, SESSION_COOKIE_NAME
from tests.factory import RowFactory
from tests.world import ITERATIONS, START, FakeClock, FixedBundle

DAY = timedelta(days=1)
RESIDENT = {"HAB_RGN_CD": "RA.JORI", "HAB_IDNTY_STTS_CD": "RV.OK"}


@dataclass
class Applicant:
    member_sn: int
    client: TestClient
    csrf: str


@dataclass
class Staff:
    admin_sn: int
    client: TestClient
    csrf: str


@dataclass
class Arena:
    """커밋되는 데이터와 실제 요청 단위 세션을 쓰는 앱. 시험이 끝나면 만든 행을 지운다."""

    migrated: Engine
    schema: Any
    settings: Settings
    engine: Engine
    bundles: list[int] = field(default_factory=list)
    admins: list[int] = field(default_factory=list)
    roles: list[int] = field(default_factory=list)
    pg: MockPaymentGateway = field(default_factory=MockPaymentGateway)  # 모든 요청이 같은 PG를 쓴다
    app: Any = None

    def build(self, make: Callable[[RowFactory], Any]) -> Any:
        with self.migrated.begin() as connection:
            factory = RowFactory(connection, self.schema)
            bundle = factory.bundle()
            self.bundles.append(bundle)
            return make(factory)

    def serve(self, bundle: int) -> None:
        app = create_app()

        def real_db() -> Iterator[Session]:
            session = open_session(self.engine)
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise
            finally:
                session.close()

        app.dependency_overrides[get_db] = real_db
        app.dependency_overrides[get_settings] = lambda: self.settings
        app.dependency_overrides[auth_deps.get_clock] = lambda: FakeClock()
        app.dependency_overrides[auth_deps.get_bundle_resolver] = lambda: FixedBundle(bundle)
        app.dependency_overrides[auth_deps.get_payment_gateway] = lambda: self.pg
        self.app = app

    def applicant(self, member_sn: int, bundle: int) -> Applicant:
        with open_session(self.engine) as session:
            token, record = issue_session(
                session, bundle_sn=bundle, member_sn=member_sn, admin_sn=None, now=START
            )
            session.commit()
        client = TestClient(self.app, base_url="https://testserver", raise_server_exceptions=False)
        client.cookies.set(SESSION_COOKIE_NAME, token)
        return Applicant(member_sn, client, session_csrf(self.settings, record))

    def staff(self, bundle: int, login: str, *authorities: str) -> "Staff":
        """묶음 전체 범위에서 주어진 기능권한을 가진 담당자와 그 세션. 시험이 끝나면 함께 지운다."""
        with self.migrated.begin() as connection:
            f = RowFactory(connection, self.schema)
            admin = int(
                f.make("TB_MNGR", LGN_ID=f"{login}-{bundle}"[:20], PSWD_HASH_VL="x" * 20, MNGR_NM=login)[
                    "MNGR_SN"
                ]
            )
            role = f.make("TB_MNGR_ROLE", ROLE_ID=f"{login}-{bundle}"[:40], ROLE_NM=login)
            for code in authorities:
                f.make("TB_ROLE_AUTHRT", ROLE_SN=role["ROLE_SN"], AUTHRT_CD=code)
            f.make(
                "TB_MNGR_SCP",
                MNGR_SN=admin,
                ROLE_SN=role["ROLE_SN"],
                SCP_TYPE_CD="SK.GROUP",
                OPER_BNDL_SN=bundle,
                VLD_BGNG_DT=START - DAY,
                GRNT_MNGR_SN=admin,
            )
        self.admins.append(admin)
        self.roles.append(int(role["ROLE_SN"]))
        with open_session(self.engine) as session:
            token, record = issue_session(session, bundle_sn=None, member_sn=None, admin_sn=admin, now=START)
            session.commit()
        client = TestClient(self.app, base_url="https://testserver", raise_server_exceptions=False)
        client.cookies.set(ADMIN_SESSION_COOKIE_NAME, token)
        return Staff(admin, client, session_csrf(self.settings, record))

    def query(self, sql: str, **params: Any) -> list[Any]:
        with self.migrated.connect() as connection:
            return list(connection.execute(text(sql), params).mappings().all())

    def cleanup(self) -> None:
        names = [t.name for t in self.schema.tables if any(c.name == "OPER_BNDL_SN" for c in t.columns)]
        with self.migrated.begin() as connection:
            connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for bundle in self.bundles:
                for name in names:
                    connection.execute(text(f"DELETE FROM {name} WHERE OPER_BNDL_SN = :b"), {"b": bundle})
                connection.execute(text("DELETE FROM TB_OPER_BNDL WHERE OPER_BNDL_SN = :b"), {"b": bundle})
            for admin in self.admins:
                for table in ("TB_LGN_SSN", "TB_MNGR_SCP", "TB_MNGR"):
                    connection.execute(text(f"DELETE FROM {table} WHERE MNGR_SN = :a"), {"a": admin})
            for role in self.roles:
                connection.execute(text("DELETE FROM TB_ROLE_AUTHRT WHERE ROLE_SN = :r"), {"r": role})
                connection.execute(text("DELETE FROM TB_MNGR_ROLE WHERE ROLE_SN = :r"), {"r": role})
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def build_arena(migrated_engine: Engine, schema_doc: Any) -> Iterator[Arena]:
    """conftest의 arena 픽스처가 부른다. 시험이 끝나면 만든 행을 지운다."""
    settings = Settings(
        database_url=migrated_engine.url.render_as_string(hide_password=False),
        site_id="concurrent",
        secret_key="s" * 40,
        pbkdf2_iterations=ITERATIONS,
    )
    engine = create_db_engine(settings)  # 운영과 같은 설정(READ COMMITTED)으로 만든 엔진
    place = Arena(migrated_engine, schema_doc, settings, engine)
    yield place
    place.cleanup()
    engine.dispose()


def parallel(calls: list[Callable[[], Any]]) -> list[Any]:
    """모든 호출이 문 앞에서 기다렸다가 동시에 출발한다."""
    barrier = threading.Barrier(len(calls))

    def run(call: Callable[[], Any]) -> Any:
        barrier.wait(timeout=30)
        return call()

    with ThreadPoolExecutor(len(calls)) as pool:
        return list(pool.map(run, calls))


def post(who: Applicant, course_sn: int, idem: str) -> Any:
    return who.client.post(
        "/api/v1/me/applications",
        json={"courseId": str(course_sn)},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": idem},
    )


def attempt(who: Applicant, course_sn: int, idem: str) -> Callable[[], Any]:
    return lambda: post(who, course_sn, idem)


def outcome(response: Any) -> str:
    """성공은 201, 실패는 오류 코드로 줄여 비교한다."""
    return "201" if response.status_code == 201 else str(response.json()["code"])


def make_cycle(f: RowFactory, bundle: int, number: int = 4) -> dict[str, Any]:
    return f.make(
        "TB_EDU_CYCL",
        OPER_BNDL_SN=bundle,
        EDU_YR="2026",
        EDU_CYCL=number,
        EDU_CYCL_NM=f"기수{number}",
        EDU_BGNG_YMD="20261101",
        EDU_END_YMD="20261231",
        RCPT_BGNG_DT=START - 10 * DAY,
        RCPT_END_DT=START + 20 * DAY,
    )


def make_course(
    f: RowFactory, bundle: int, cycle: dict[str, Any], name: str, **values: Any
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "OPER_BNDL_SN": bundle,
        "EDU_CYCL_SN": cycle["EDU_CYCL_SN"],
        "CORS_NM": name,
        "CORS_STTS_CD": "CS.OPEN",
        "RCRT_NOPE": 10,
        "WTNG_NOPE": 5,
        "TTCHG": 30000,
        "RCPT_BGNG_DT": START - 5 * DAY,
        "RCPT_END_DT": START + 5 * DAY,
        "EDU_BGNG_YMD": "20261101",
        "EDU_END_YMD": "20261231",
        "STLM_WTNG_MINUTE": 10,
    }
    return f.make("TB_CORS", **{**defaults, **values})


def make_member(f: RowFactory, bundle: int, login: str) -> int:
    row = f.make(
        "TB_MBR",
        OPER_BNDL_SN=bundle,
        LGN_ID=login,
        PSWD_HASH_VL="x" * 20,
        MBR_NM="신청자",
        MBL_TELNO="01012345678",
        **RESIDENT,
    )
    return int(row["MBR_SN"])


def make_application(
    f: RowFactory, bundle: int, member: int, course: dict[str, Any], state: str, seq: int | None = None
) -> int:
    """미리 만들어 둔 신청. 보류는 결제기한이, 대기는 대기순서가 있어야 한다."""
    extra: dict[str, Any] = {}
    if state == "ES.HOLD":
        extra.update(SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START + timedelta(minutes=10))
    if state == "ES.WAIT":
        extra["WTNG_SEQ"] = seq
    if state in ("ES.CANCEL", "ES.EXPIRE"):
        extra.update(RTRCN_DT=START, RTRCN_RSN="취소")
    row = f.make(
        "TB_ATNLC_APLY",
        OPER_BNDL_SN=bundle,
        MBR_SN=member,
        CORS_SN=course["CORS_SN"],
        APLY_STTS_CD=state,
        TTCHG_AMT=30000,
        RDCT_AMT=0,
        STLM_PRNMNT_AMT=30000,
        **extra,
    )
    return int(row["ATNLC_APLY_SN"])


def cancel_call(who: Applicant, application_sn: int) -> Callable[[], Any]:
    return lambda: who.client.post(
        f"/api/v1/me/applications/{application_sn}/cancel", headers={"X-CSRF-Token": who.csrf}
    )
