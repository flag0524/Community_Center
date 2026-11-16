# 두 담당자가 같은 대상에게 같은 역할을 동시에 배정해도 겹치는 배정이 한 건만 생기는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app.domain.admin import role_service
from tests.arena import Arena, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> tuple[int, int, int]:
    bundle = f.bundle()
    who = f.make("TB_MNGR", LGN_ID=f"tg{bundle}", PSWD_HASH_VL="x" * 20, MNGR_NM="대상자")
    r = f.make("TB_MNGR_ROLE", ROLE_ID=f"rl{bundle}", ROLE_NM="신청 조회")
    f.make("TB_ROLE_AUTHRT", ROLE_SN=r["ROLE_SN"], AUTHRT_CD="AU.APLY_R")
    return bundle, int(who["MNGR_SN"]), int(r["ROLE_SN"])


def test_같은_대상에_같은_역할을_동시에_배정해도_겹치는_배정은_한_건만_만든다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, target, role = arena.build(build)
    arena.admins.append(target)
    arena.roles.append(role)
    arena.serve(bundle)
    one = arena.staff(bundle, "one", "AU.GRANT_W", "AU.APLY_R")
    two = arena.staff(bundle, "two", "AU.GRANT_W", "AU.APLY_R")
    real = role_service._delegable

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(
            0.5
        )  # 위임 판정을 마치고 겹침을 확인하기 전의 틈을 넓힌다. 대상 행 잠금이 없으면 둘 다 만든다
        return result

    monkeypatch.setattr(role_service, "_delegable", slow)
    payload = {
        "adminId": str(target),
        "roleId": str(role),
        "scope": "GROUP",
        "dongId": None,
        "validFrom": "2026-11-09",
        "validTo": None,
    }

    def send(who: Any, key: str) -> Any:
        return lambda: who.client.post(
            f"{ADMIN}/role-assignments",
            json=payload,
            headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key},
        )

    responses = parallel([send(one, "role-conc-0001"), send(two, "role-conc-0002")])
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert (
        len(arena.query("SELECT 1 FROM TB_MNGR_SCP WHERE MNGR_SN=:m AND ROLE_SN=:r", m=target, r=role)) == 1
    )
