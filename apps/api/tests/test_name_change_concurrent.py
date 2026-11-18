# 이름 변경 요청과 결정이 동시에 와도 한 건만 저장·결정되는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app import audit
from app.auth.passwords import hash_password
from app.domain.member import name_change_service, profile_service
from tests.arena import Applicant, Arena, parallel
from tests.world import ITERATIONS, PASSWORD

pytestmark = pytest.mark.db

MINE = "/api/v1/me/name-change-requests"
ADMIN = "/api/admin/v1/name-change-requests"


def build(f: Any) -> tuple[int, int]:
    bundle = f.bundle()
    row = f.make(
        "TB_MBR",
        OPER_BNDL_SN=bundle,
        LGN_ID="renamer",
        PSWD_HASH_VL=hash_password(PASSWORD, ITERATIONS),
        MBR_NM="김회원",
        MBL_TELNO="01012345678",
    )
    return bundle, int(row["MBR_SN"])


def ask(who: Applicant, name: str, key: str) -> Any:
    body = {"newName": name, "reason": "개명", "password": PASSWORD}
    return lambda: who.client.post(
        MINE, json=body, headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key}
    )


def test_같은_회원의_동시_요청은_한_건만_저장한다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    real = profile_service._check_password

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)  # 진행 중 요청 검사와 저장 사이를 넓힌다. 회원 행 잠금이 없으면 둘 다 저장한다
        return result

    monkeypatch.setattr(name_change_service, "_check_password", slow)
    one, two = (arena.applicant(member, bundle) for _ in range(2))
    responses = parallel([ask(one, "이새이름", "conc-key-0001"), ask(two, "최새이름", "conc-key-0002")])
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    assert (
        len(
            arena.query(
                "SELECT 1 FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='NAME_CHANGE_REQUEST'", b=bundle
            )
        )
        == 1
    )


def test_같은_키의_동시_요청은_한_건이고_같은_결과를_준다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    real = profile_service._check_password

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)
        return result

    monkeypatch.setattr(name_change_service, "_check_password", slow)
    one, two = (arena.applicant(member, bundle) for _ in range(2))
    responses = parallel([ask(one, "이새이름", "same-key-conc"), ask(two, "이새이름", "same-key-conc")])
    assert [r.status_code for r in responses] == [201, 201], [r.text for r in responses]
    assert len({r.json()["requestId"] for r in responses}) == 1


def test_동시에_승인과_반려를_해도_한_번만_결정하고_이름은_승인일_때만_바뀐다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    who = arena.applicant(member, bundle)
    made = ask(who, "이새이름", "decide-key-01")()
    assert made.status_code == 201, made.text
    sn = made.json()["requestId"]
    real = audit.record_job

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.5)  # 결정 여부 검사와 저장 사이를 넓힌다. 회원 행 잠금이 없으면 둘 다 결정한다
        return real(*args, **kwargs)

    monkeypatch.setattr(name_change_service, "record_job", slow)
    boss1 = arena.staff(bundle, "nc-a", "AU.GRANT_W")
    boss2 = arena.staff(bundle, "nc-b", "AU.GRANT_W")

    def decide(staff: Any, action: str) -> Any:
        return lambda: staff.client.post(
            f"{ADMIN}/{sn}/{action}", json={}, headers={"X-CSRF-Token": staff.csrf}
        )

    responses = parallel([decide(boss1, "approve"), decide(boss2, "reject")])
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    [decided] = arena.query(
        "SELECT CHG_CN c FROM TB_JOB_HSTRY WHERE OPER_BNDL_SN=:b AND JOB_CD='NAME_CHANGE_DECIDE'", b=bundle
    )
    [name] = arena.query("SELECT MBR_NM n FROM TB_MBR WHERE MBR_SN=:m", m=member)
    assert (decided["c"], name["n"]) in {("승인", "이새이름"), ("반려", "김회원")}
