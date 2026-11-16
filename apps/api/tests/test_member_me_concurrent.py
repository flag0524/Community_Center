# 같은 회원의 탈퇴 요청이 동시에 와도 한 번만 처리되고 탈퇴일이 늘어나지 않는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app.auth.passwords import hash_password
from app.domain.member import profile_service
from tests.arena import Applicant, Arena, parallel
from tests.world import ITERATIONS, PASSWORD

pytestmark = pytest.mark.db

API = "/api/v1"


def build(f: Any) -> tuple[int, int]:
    bundle = f.bundle()
    row = f.make(
        "TB_MBR",
        OPER_BNDL_SN=bundle,
        LGN_ID="leaver",
        PSWD_HASH_VL=hash_password(PASSWORD, ITERATIONS),
        MBR_NM="탈퇴자",
        MBL_TELNO="01012345678",
    )
    return bundle, int(row["MBR_SN"])


def send(who: Applicant) -> Any:
    return who.client.post(
        f"{API}/me/withdraw", json={"password": PASSWORD}, headers={"X-CSRF-Token": who.csrf}
    )


def test_탈퇴를_동시에_두_번_보내도_한_번만_처리한다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:

    bundle, member = arena.build(build)
    arena.serve(bundle)
    real = profile_service._has_open_work

    def slow(*args: Any) -> Any:
        time.sleep(0.5)  # 검사와 저장 사이를 넓힌다. 회원 행 잠금과 상태 확인이 없으면 둘 다 성공한다
        return real(*args)

    monkeypatch.setattr(profile_service, "_has_open_work", slow)
    one, two = (arena.applicant(member, bundle) for _ in range(2))
    responses = parallel([lambda: send(one), lambda: send(two)])
    assert sorted(r.status_code for r in responses) == [204, 401], [r.text for r in responses]
    [row] = arena.query("SELECT MBR_STTS_CD s FROM TB_MBR WHERE MBR_SN=:m", m=member)
    assert str(row["s"]).strip() == "MS.WITHDRAW"
