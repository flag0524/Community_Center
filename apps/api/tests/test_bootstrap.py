# 새 배포의 최초 설정(운영묶음·행정동·최초 관리자)을 실제 앱과 MariaDB로 확인하는 시험(ADR-104)
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.passwords import verify_password
from app.core.config import get_settings
from app.domain.admin.types import AdminAuthority
from app.tools import bootstrap as boot
from app.tools.bootstrap import AdminSpec, BootstrapError, SiteSpec, bootstrap, read_dongs, validate
from tests.world import ADMIN, START, World, login

pytestmark = pytest.mark.db

PASSWORD = "Strong-Pass-1234"
DONGS = ["가동", "나동", "다동"]


def site(world: World, **values: Any) -> SiteSpec:
    """시험 월드의 운영묶음을 쓴다. 배포 설정이 가리키는 묶음이라 로그인까지 이어진다.
    공장이 만든 식별자는 대문자라 설계안 형식(소문자 영숫자·하이픈)으로 바꾸고 설정도 맞춘다."""
    world.db.execute(
        text("UPDATE TB_OPER_BNDL SET SITE_ID='test-site' WHERE OPER_BNDL_SN=:b"), {"b": world.bundle}
    )
    settings = replace(world.settings, site_id="test-site")
    world.client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    base: dict[str, Any] = {
        "site_id": "test-site",
        "bundle_name": "조리읍",
        "site_name": "조리읍 주민자치센터",
        "url": "https://user.example.invalid",
    }
    return SiteSpec(**{**base, **values})


def admin(**values: Any) -> AdminSpec:
    base: dict[str, Any] = {"login_id": "firstadmin", "name": "최초관리자", "password": PASSWORD}
    return AdminSpec(**{**base, **values})


def run(world: World, spec: SiteSpec, who: AdminSpec, dongs: list[str] = DONGS) -> boot.BootstrapResult:
    return bootstrap(world.db, world.settings, spec, who, dongs, now=START, request_id="bootstrap-test")


def rows(world: World, sql: str, **params: Any) -> list[Any]:
    return list(world.db.execute(text(sql), params).mappings().all())


def test_새_사이트면_운영묶음_행정동_관리자_역할_배정_이력을_한꺼번에_만든다(world: World) -> None:
    result = run(world, site(world, site_id="new-site"), admin())
    assert result.bundle_created and result.dong_count == 3
    [bundle] = rows(world, "SELECT * FROM TB_OPER_BNDL WHERE SITE_ID='new-site'")
    assert (bundle["OPER_BNDL_NM"], bundle["TMZN_NM"], bundle["USE_YN"]) == ("조리읍", "Asia/Seoul", "Y")
    dongs = rows(
        world,
        "SELECT DONG_NM n, SORT_SEQ s FROM TB_DONG WHERE OPER_BNDL_SN=:b ORDER BY SORT_SEQ",
        b=result.bundle_sn,
    )
    assert [(d["n"], int(d["s"])) for d in dongs] == [("가동", 1), ("나동", 2), ("다동", 3)]
    [mngr] = rows(world, "SELECT * FROM TB_MNGR WHERE LGN_ID='firstadmin'")
    assert verify_password(PASSWORD, mngr["PSWD_HASH_VL"]) and PASSWORD not in str(mngr)
    granted = {r["a"].strip() for r in rows(world, "SELECT AUTHRT_CD a FROM TB_ROLE_AUTHRT")}
    assert granted == {a.value for a in AdminAuthority}
    scopes = rows(
        world, "SELECT SCP_TYPE_CD k, OPER_BNDL_SN b, GRNT_MNGR_SN g FROM TB_MNGR_SCP ORDER BY MNGR_SCP_SN"
    )
    assert [(s["k"].strip(), s["b"]) for s in scopes] == [("SK.GROUP", result.bundle_sn)]
    assert all(int(s["g"]) == result.admin_sn for s in scopes)
    [job] = rows(
        world, "SELECT ACTR_TYPE_CD a, JOB_CD j, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='BOOTSTRAP'"
    )
    assert job["a"].strip() == "AK.SYSTEM" and "사이트 new-site 생성" in job["c"] and PASSWORD not in job["c"]


def test_이미_있는_사이트를_쓰면_그_묶음에_행정동과_관리자를_더하고_로그인해_업무를_볼_수_있다(
    world: World,
) -> None:
    result = run(world, site(world), admin())
    assert not result.bundle_created and result.bundle_sn == world.bundle
    world.db.commit()
    response = login(world, ADMIN, "firstadmin", PASSWORD)
    assert response.status_code == 200, response.text
    menus = world.client.get(f"{ADMIN}/me/permissions")
    out = menus.json()
    assert menus.status_code == 200 and set(out["authorities"]) == {a.value for a in AdminAuthority}
    assert out["roleNames"] == ["최초 관리자"] and out["menu"], menus.text
    assert world.client.get(f"{ADMIN}/cycles").status_code == 200  # 업무 권한
    assert world.client.get(f"{ADMIN}/role-assignments").status_code == 200  # 운영구조 권한


def test_이미_관리자가_있으면_거부하고_아무것도_더하지_않는다(world: World) -> None:
    run(world, site(world), admin())
    before = rows(world, "SELECT (SELECT COUNT(*) FROM TB_MNGR) m, (SELECT COUNT(*) FROM TB_DONG) d")[0]
    with pytest.raises(BootstrapError, match="이미 관리자가 있는 배포"):
        run(world, site(world), admin(login_id="second"), ["라동"])
    assert (
        rows(world, "SELECT (SELECT COUNT(*) FROM TB_MNGR) m, (SELECT COUNT(*) FROM TB_DONG) d")[0] == before
    )


def test_중지된_사이트는_쓰지_않는다(world: World) -> None:
    world.db.execute(text("UPDATE TB_OPER_BNDL SET USE_YN='N' WHERE OPER_BNDL_SN=:b"), {"b": world.bundle})
    with pytest.raises(BootstrapError, match="중지 상태"):
        run(world, site(world), admin())
    assert rows(world, "SELECT COUNT(*) n FROM TB_MNGR")[0]["n"] == 0


@pytest.mark.parametrize(
    ("spec", "who", "dongs", "message"),
    [
        (SiteSpec("Bad_Site", "a", "b", "https://x"), admin(), DONGS, "사이트 식별자"),
        (SiteSpec("ok", " ", "b", "https://x"), admin(), DONGS, "운영묶음명"),
        (SiteSpec("ok", "a", "b", "http://x"), admin(), DONGS, "https://"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(login_id="1bad"), DONGS, "관리자 아이디"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(name=""), DONGS, "관리자 이름"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(password="Short1!"), DONGS, "비밀번호"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(password="alllowercaseonlyletters"), DONGS, "비밀번호"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(), [], "비어 있습니다"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(), ["가동", "가동"], "같은 이름"),
        (SiteSpec("ok", "a", "b", "https://x"), admin(), ["동" * 41], "40자"),
    ],
)
def test_입력이_틀리면_쓰기_전에_거부한다(
    world: World, spec: SiteSpec, who: AdminSpec, dongs: list[str], message: str
) -> None:
    with pytest.raises(BootstrapError, match=message):
        validate(spec, who, dongs)
    with pytest.raises(BootstrapError, match=message):
        run(world, spec, who, dongs)
    assert rows(
        world,
        "SELECT (SELECT COUNT(*) FROM TB_MNGR) m, (SELECT COUNT(*) FROM TB_OPER_BNDL WHERE SITE_ID='ok') b",
    )[0] == {"m": 0, "b": 0}


def test_이미_있는_행정동_이름은_다시_만들지_않는다(world: World) -> None:
    world.factory.make("TB_DONG", DONG_NM="가동")
    result = run(world, site(world), admin(), ["가동", "나동"])
    assert result.dong_count == 1
    names = [
        r["n"]
        for r in rows(
            world, "SELECT DONG_NM n FROM TB_DONG WHERE OPER_BNDL_SN=:b ORDER BY DONG_SN", b=world.bundle
        )
    ]
    assert names == ["가동", "나동"]


# --- 입력 파일과 명령줄 ----------------------------------------------------------------------


def test_행정동_명단은_빈_줄과_주석을_건너뛰고_BOM을_허용한다(tmp_path: Path) -> None:
    path = tmp_path / "dongs.txt"
    path.write_text("﻿# 기관 제공 명단\n\n가동 \n 나동\n# 끝\n", encoding="utf-8")
    assert read_dongs(path) == ["가동", "나동"]


def args(tmp_path: Path, **override: str) -> list[str]:
    dongs = tmp_path / "dongs.txt"
    dongs.write_text("가동\n나동\n", encoding="utf-8")
    values = {
        "--site-id": "jori",
        "--bundle-name": "조리읍",
        "--site-name": "조리읍 주민자치센터",
        "--url": "https://user.example.invalid",
        "--dongs-file": str(dongs),
        "--admin-id": "firstadmin",
        "--admin-name": "최초관리자",
        **override,
    }
    return ["bootstrap", *[x for pair in values.items() for x in pair]]


def test_명령줄은_비밀번호를_두_번_받아_다르면_만들지_않고_같으면_만든다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    made: list[tuple[SiteSpec, AdminSpec, list[str]]] = []

    def fake_run(settings: Any, spec: SiteSpec, who: AdminSpec, dongs: list[str]) -> boot.BootstrapResult:
        made.append((spec, who, list(dongs)))
        return boot.BootstrapResult(1, 2, len(dongs), True)

    monkeypatch.setattr(boot, "_run", fake_run)
    monkeypatch.setattr(boot, "get_settings", lambda: None)
    answers = iter([PASSWORD, "다른 값", PASSWORD, PASSWORD])
    assert boot.main(args(tmp_path), read_secret=lambda prompt: next(answers)) == 3
    assert made == [] and "서로 다릅니다" in capsys.readouterr().err
    assert boot.main(args(tmp_path), read_secret=lambda prompt: next(answers)) == 0
    out = capsys.readouterr().out
    assert made[0][1].password == PASSWORD and made[0][2] == ["가동", "나동"]
    assert PASSWORD not in out and "비밀번호는 기록하지 않았습니다" in out


def test_명령줄은_입력이_틀리거나_파일이_없으면_3으로_끝나고_비밀번호를_출력하지_않는다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(boot, "_run", lambda *a: (_ for _ in ()).throw(AssertionError("만들면 안 된다")))
    weak = boot.main(args(tmp_path), read_secret=lambda prompt: "short")
    missing = boot.main(
        args(tmp_path, **{"--dongs-file": str(tmp_path / "없음.txt")}), read_secret=lambda prompt: PASSWORD
    )
    assert (weak, missing) == (3, 3)
    err = capsys.readouterr().err
    assert "비밀번호는 12자" in err and "short" not in err
