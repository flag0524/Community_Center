# 개발용 주민 계정 도구가 로그인되는 계정을 만들고 잘못된 입력·운영 환경·중복은 막는지 확인(ADR-116)
import io
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.member_phone import reveal, search_hash
from app.auth.passwords import verify_password
from app.core.config import Settings, get_settings
from app.tools import dev_member as tool
from app.tools.dev_member import DevMemberError, MemberSpec, create_member
from tests.world import MEMBER, START, World, login

pytestmark = pytest.mark.db

PASSWORD = "Dev-Member-1234"
PHONE = "01012345678"


def configured(world: World, **values: Any) -> Settings:
    """시험 월드의 운영묶음을 배포 설정이 가리키게 한다. 공장이 만든 식별자는 대문자라 소문자로 바꾼다."""
    world.db.execute(
        text("UPDATE TB_OPER_BNDL SET SITE_ID='test-site' WHERE OPER_BNDL_SN=:b"), {"b": world.bundle}
    )
    settings = replace(world.settings, site_id="test-site", **values)
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    return settings


def spec(**values: Any) -> MemberSpec:
    base: dict[str, Any] = {"login_id": "devmember", "name": "개발회원", "password": PASSWORD}
    return MemberSpec(**{**base, **values})


def make(world: World, settings: Settings, who: MemberSpec) -> tool.Created:
    return create_member(world.db, settings, who, now=START, request_id="dev-member-test")


def count(world: World, table: str) -> int:
    return int(world.db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def production_settings(world: World) -> Settings:
    return replace(
        world.settings,
        site_id="test-site",
        environment="production",
        pg_provider="live",
        sms_provider="live",
        file_scanner="clamd",
        cookie_secure=True,
    )


def test_만든_계정은_실제로_로그인되고_번호는_암호문과_검색해시로만_저장된다(world: World) -> None:
    settings = configured(world)
    created = make(world, settings, spec(phone=PHONE, email="dev@example.invalid"))
    world.db.commit()
    [row] = world.db.execute(text("SELECT * FROM TB_MBR WHERE LGN_ID='devmember'")).mappings().all()
    assert int(row["MBR_SN"]) == created.member_sn and int(row["OPER_BNDL_SN"]) == world.bundle
    assert (row["MBR_NM"], row["EML_ADDR"]) == ("개발회원", "dev@example.invalid")
    assert verify_password(PASSWORD, row["PSWD_HASH_VL"]) and PASSWORD not in str(row)
    assert PHONE not in str(row)  # 평문 번호는 어느 컬럼에도 없다
    assert reveal(settings.secret_key, row["MBL_TELNO_ENCPT_VL"]) == PHONE
    assert row["MBL_TELNO_SRCH_HASH_VL"] == search_hash(settings.secret_key, PHONE)
    ok = login(world, MEMBER, "devmember", PASSWORD)
    assert ok.status_code == 200 and ok.json()["member"]["name"] == "개발회원"
    world.client.cookies.clear()  # 로그인 상태로는 익명 토큰을 다시 받을 수 없다
    wrong = login(world, MEMBER, "devmember", "wrong-password")
    assert wrong.status_code == 401


def test_전화번호와_이메일은_없어도_만들고_이력에는_비밀값이_없다(world: World) -> None:
    settings = configured(world)
    created = make(world, settings, spec())
    [row] = world.db.execute(text("SELECT * FROM TB_MBR WHERE LGN_ID='devmember'")).mappings().all()
    assert (row["MBL_TELNO_ENCPT_VL"], row["MBL_TELNO_SRCH_HASH_VL"], row["EML_ADDR"]) == (None, None, None)
    [job] = world.db.execute(text("SELECT * FROM TB_JOB_HSTRY WHERE JOB_CD='DEV_MEMBER'")).mappings().all()
    assert job["ACTR_TYPE_CD"].strip() == "AK.SYSTEM" and job["TRGT_TBL_NM"] == "TB_MBR"
    # 시스템 행위자는 회원 칸이 비어야 한다(CK_R21_ACTOR). 회원 번호는 대상 키에 남는다
    assert (job["MBR_SN"], job["TRGT_KEY_VL"]) == (None, str(created.member_sn))
    assert PASSWORD not in str(job) and "devmember" not in str(job["CHG_CN"])


def test_같은_아이디는_거절하고_계정도_이력도_더하지_않는다(world: World) -> None:
    settings = configured(world)
    make(world, settings, spec())
    members, jobs = count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")
    with pytest.raises(DevMemberError, match="이미 있는 아이디"):
        make(world, settings, spec(name="다른사람", password="Another-Pass-99"))
    assert (count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")) == (members, jobs)


@pytest.mark.parametrize(
    "values",
    [
        {"login_id": "Upper-Case"},
        {"login_id": "abc"},
        {"login_id": "a" * 21},
        {"login_id": "1abcdef"},
        {"name": "   "},
        {"name": "가" * 101},
        {"password": "short-pw9"},
        {"password": "p" * 65},
        {"phone": "0212345678"},
        {"phone": "010-1234-5678"},
        {"email": "not-an-email"},
    ],
)
def test_입력이_틀리면_쓰기_전에_거절한다(world: World, values: dict[str, Any]) -> None:
    settings = configured(world)
    members, jobs = count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")
    with pytest.raises(DevMemberError):
        make(world, settings, spec(**values))
    assert (count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")) == (members, jobs)


def test_운영묶음이_없으면_최초_설정을_먼저_하라고_알리고_만들지_않는다(world: World) -> None:
    settings = replace(configured(world), site_id="other-site")
    members = count(world, "TB_MBR")
    with pytest.raises(DevMemberError, match="bootstrap"):
        make(world, settings, spec())
    assert count(world, "TB_MBR") == members


def test_운영_환경에서는_거절하고_아무것도_만들지_않는다(world: World) -> None:
    configured(world)
    members, jobs = count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")
    with pytest.raises(DevMemberError, match="운영 환경"):
        make(world, production_settings(world), spec())
    assert (count(world, "TB_MBR"), count(world, "TB_JOB_HSTRY")) == (members, jobs)


# --- 명령줄(DB 없이 진입점만) -----------------------------------------------------------------------


def args(**override: str) -> list[str]:
    values = {"--login-id": "devmember", "--name": "개발회원", **override}
    return ["dev_member", *[x for pair in values.items() for x in pair]]


def test_명령줄은_비밀번호를_두_번_받아_다르면_만들지_않고_같으면_만든다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], world: World
) -> None:
    made: list[MemberSpec] = []

    def fake_run(settings: Settings, who: MemberSpec) -> tool.Created:
        made.append(who)
        return tool.Created(7, who.login_id)

    monkeypatch.setattr(tool, "_run", fake_run)
    monkeypatch.setattr(tool, "get_settings", lambda: world.settings)
    answers = iter([PASSWORD, "다른 값", PASSWORD, PASSWORD])
    assert tool.main(args(), read_secret=lambda prompt: next(answers)) == 3
    assert made == [] and "서로 다릅니다" in capsys.readouterr().err
    assert tool.main(args(**{"--phone": PHONE}), read_secret=lambda prompt: next(answers)) == 0
    out = capsys.readouterr().out
    assert made[0].password == PASSWORD and made[0].phone == PHONE
    assert "devmember" in out and PASSWORD not in out and PHONE not in out


def test_명령줄은_입력이_틀리면_3으로_끝나고_비밀번호를_출력하지_않는다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], world: World
) -> None:
    monkeypatch.setattr(tool, "_run", lambda *a: (_ for _ in ()).throw(AssertionError("만들면 안 된다")))
    monkeypatch.setattr(tool, "get_settings", lambda: world.settings)
    assert tool.main(args(), read_secret=lambda prompt: "short") == 3
    assert "비밀번호는 10~64자" in capsys.readouterr().err


def test_명령줄은_운영_환경이면_비밀번호를_묻기_전에_3으로_끝난다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], world: World
) -> None:
    def must_not_ask(prompt: str) -> str:
        raise AssertionError("운영 환경에서는 비밀번호를 묻지 않아야 한다")

    monkeypatch.setattr(tool, "_run", lambda *a: (_ for _ in ()).throw(AssertionError("만들면 안 된다")))
    monkeypatch.setattr(tool, "get_settings", lambda: production_settings(world))
    assert tool.main(args(), read_secret=must_not_ask) == 3
    assert "운영 환경" in capsys.readouterr().err


def test_표준입력_옵션은_프롬프트_없이_한_줄을_비밀번호로_받는다(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    made: list[MemberSpec] = []

    def fake_run(settings: Settings, who: MemberSpec) -> tool.Created:
        made.append(who)
        return tool.Created(1, who.login_id)

    monkeypatch.setattr(tool, "_run", fake_run)
    monkeypatch.setattr(tool, "get_settings", lambda: world.settings)
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\r\n"))

    def must_not_ask(prompt: str) -> str:
        raise AssertionError("표준입력 옵션이면 프롬프트를 쓰지 않는다")

    assert tool.main([*args(), "--password-stdin"], read_secret=must_not_ask) == 0
    assert made[0].password == PASSWORD
