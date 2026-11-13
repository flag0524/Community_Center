# 같은 회원의 동시 신청과 철회 직전의 증빙 올리기가 겹쳐도 한 번만 반영되는지 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.db import versioned
from app.domain.reduction import service
from tests.arena import Applicant, Arena, make_cycle, make_member, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

API = "/api/v1"
PDF = b"%PDF-1.7\n"


def build(f: RowFactory) -> tuple[int, int, int]:
    bundle = f.bundle()
    return bundle, make_member(f, bundle, "applicant"), int(make_cycle(f, bundle)["EDU_CYCL_SN"])


def resident(arena: Arena, member: int) -> None:
    with arena.migrated.begin() as connection:
        connection.execute(
            text("UPDATE TB_MBR SET HAB_RGN_CD='RA.JORI', HAB_IDNTY_STTS_CD='RV.OK' WHERE MBR_SN=:m"),
            {"m": member},
        )


def post(who: Applicant, path: str, key: str, body: dict[str, Any] | None = None) -> Any:
    return who.client.post(
        f"{API}{path}", json=body, headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key}
    )


def same_key(who: Applicant, body: dict[str, Any]) -> Callable[[], Any]:
    return lambda: post(who, "/me/reduction-reviews", "red-conc-same1", body)


def test_같은_회원이_같은_기수에_동시에_신청해도_접수건은_하나만_생긴다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, cycle = arena.build(build)
    resident(arena, member)
    arena.serve(bundle)
    real = service._blocking

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(
            0.5
        )  # 중복이 없다고 확인한 뒤 저장하기 전의 틈을 넓힌다. 회원 행 잠금이 없으면 둘 다 만든다
        return result

    monkeypatch.setattr(service, "_blocking", slow)
    body = {"cycleId": str(cycle), "reductionType": "LIVELIHOOD"}
    one, two = (
        arena.applicant(member, bundle) for _ in range(2)
    )  # 세션이 같으면 이미 한 줄로 서므로 따로 만든다
    responses = parallel(
        [
            lambda: post(one, "/me/reduction-reviews", "red-conc-0001", body),
            lambda: post(two, "/me/reduction-reviews", "red-conc-0002", body),
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_RDCT_BFHD_SRNG WHERE MBR_SN=:m", m=member)) == 1


def test_같은_키의_동시_신청은_같은_접수건을_돌려준다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, member, cycle = arena.build(build)
    resident(arena, member)
    arena.serve(bundle)
    real = service._blocking

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(0.3)
        return result

    monkeypatch.setattr(service, "_blocking", slow)
    body = {"cycleId": str(cycle), "reductionType": "LIVELIHOOD"}
    sessions = [arena.applicant(member, bundle) for _ in range(3)]
    responses = parallel([same_key(s, body) for s in sessions])
    assert [r.status_code for r in responses] == [201] * 3, [r.text for r in responses]
    assert len({r.json()["reviewId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_RDCT_BFHD_SRNG WHERE MBR_SN=:m", m=member)) == 1


def test_철회하는_동안_증빙을_올려도_철회한_심사에는_파일이_남지_않는다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arena.settings = replace(arena.settings, file_root=str(tmp_path))
    bundle, member, cycle = arena.build(build)
    resident(arena, member)
    arena.serve(bundle)
    one, two = (arena.applicant(member, bundle) for _ in range(2))
    review = post(
        one, "/me/reduction-reviews", "red-conc-0003", {"cycleId": str(cycle), "reductionType": "VETERAN"}
    ).json()["reviewId"]
    real = versioned.update_versioned

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.8)  # 철회가 심사 행을 잠근 채 머무는 동안 올리기가 들어오게 한다
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "update_versioned", slow)

    def withdraw() -> Any:
        return post(one, f"/me/reduction-reviews/{review}/withdraw", "unused-0001")

    def upload() -> Any:
        time.sleep(0.3)
        return two.client.post(
            f"{API}/me/reduction-reviews/{review}/files",
            files={"file": ("a.pdf", PDF, "application/octet-stream")},
            headers={"X-CSRF-Token": two.csrf, "Idempotency-Key": "red-conc-file1"},
        )

    withdrawn, uploaded = parallel([withdraw, upload])
    assert withdrawn.status_code == 200, withdrawn.text
    assert uploaded.status_code == 409, uploaded.text
    assert len(arena.query("SELECT 1 FROM TB_FILE WHERE RDCT_BFHD_SRNG_SN=:r", r=review)) == 0
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
