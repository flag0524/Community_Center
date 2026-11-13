# 같은 감면 심사를 두 담당자가 동시에 결정하거나, 같은 회원·기수의 결정된 심사를 동시에 재심사해도 한 번만 반영되는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.domain.admin import reduction_service
from tests.arena import Arena, Staff, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def seed(arena: Arena, statuses: list[str]) -> tuple[int, list[Any]]:
    """한 회원의 같은 기수 심사를 상태별로 만든다."""

    def build(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        return bundle, make_member(f, bundle, "applicant"), int(make_cycle(f, bundle)["EDU_CYCL_SN"])

    bundle, member, cycle = arena.build(build)
    arena.serve(bundle)
    boss = arena.staff(bundle, "seed", "AU.APLY_R", "AU.APLY_W")
    made: list[Any] = []
    with arena.migrated.begin() as connection:
        f = RowFactory(connection, arena.schema)
        for status in statuses:
            extra: dict[str, Any] = {}
            if status != "DS.RECEIVED":
                extra = {"SRNG_MNGR_SN": boss.admin_sn, "SRNG_DT": START, "RJCT_RSN": "사유"}
            made.append(
                f.make(
                    "TB_RDCT_BFHD_SRNG",
                    OPER_BNDL_SN=bundle,
                    MBR_SN=member,
                    EDU_CYCL_SN=cycle,
                    RDCT_TYPE_CD="DR.LIVELIHD",
                    SRNG_STTS_CD=status,
                    APLY_DT=START,
                    **extra,
                )
            )
    return bundle, made


def post(who: Staff, path: str, body: dict[str, Any] | None, key: str | None = None) -> Callable[[], Any]:
    headers = {"X-CSRF-Token": who.csrf, **({"Idempotency-Key": key} if key else {})}
    return lambda: who.client.post(f"{ADMIN}{path}", json=body, headers=headers)


def test_같은_심사를_동시에_결정해도_한_번만_반영한다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, [rev] = seed(arena, ["DS.RECEIVED"])
    one = arena.staff(bundle, "one", "AU.APLY_R", "AU.APLY_W")
    two = arena.staff(bundle, "two", "AU.APLY_R", "AU.APLY_W")
    real = reduction_service._check

    def slow(*args: Any) -> Any:
        result = real(*args)
        time.sleep(0.5)  # 검사를 마치고 저장하기 전의 틈을 넓힌다. 행 잠금이 없으면 둘 다 이 틈에 들어온다
        return result

    monkeypatch.setattr(reduction_service, "_check", slow)
    body = {"decision": "REJECT", "rejectReason": "증빙 불충분", "version": 1}
    path = f"/reductions/{rev['RDCT_BFHD_SRNG_SN']}/decision"
    responses = parallel([post(one, path, body), post(two, path, {**body, "rejectReason": "다른 사유"})])
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    [state] = arena.query("SELECT SRNG_STTS_CD s, RCRD_VER v FROM TB_RDCT_BFHD_SRNG")
    assert (state["s"], state["v"]) == ("DS.REJECTED", 2)
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='RDCT_REVIEW_REJECT'")) == 1


def test_같은_회원_기수를_동시에_재심사해도_접수건은_하나만_생긴다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, [first, second] = seed(arena, ["DS.REJECTED", "DS.REJECTED"])
    one = arena.staff(bundle, "one", "AU.APLY_R", "AU.APLY_W")
    two = arena.staff(bundle, "two", "AU.APLY_R", "AU.APLY_W")
    real = reduction_service._open_sibling

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(
            0.5
        )  # 접수 중인 건이 없다고 확인한 뒤 새 건을 넣기 전의 틈을 넓힌다. 회원 행 잠금이 없으면 둘 다 만든다
        return result

    monkeypatch.setattr(reduction_service, "_open_sibling", slow)
    responses = parallel(
        [
            post(one, f"/reductions/{first['RDCT_BFHD_SRNG_SN']}/re-review", None, "rr-conc-0001"),
            post(two, f"/reductions/{second['RDCT_BFHD_SRNG_SN']}/re-review", None, "rr-conc-0002"),
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_RDCT_BFHD_SRNG WHERE SRNG_STTS_CD='DS.RECEIVED'")) == 1
