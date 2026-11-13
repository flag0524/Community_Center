# 서로 다른 강좌가 같은 강의실의 같은 시간에 동시에 일정을 등록해도 한 곳만 저장되는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.domain.admin import schedule_service
from tests.arena import Arena, Staff, make_course, make_cycle, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    bundle = f.bundle()
    cycle = make_cycle(f, bundle)
    courses = [make_course(f, bundle, cycle, f"강좌{n}") for n in range(3)]
    center = f.make("TB_FCLT", OPER_BNDL_SN=bundle, FCLT_TYPE_CD="FT.CENTER", FCLT_NM="센터", USE_YN="Y")
    room = f.make(
        "TB_FCLT",
        OPER_BNDL_SN=bundle,
        FCLT_TYPE_CD="FT.ROOM",
        UP_FCLT_SN=center["FCLT_SN"],
        FCLT_NM="1강의실",
        USE_YN="Y",
    )
    return bundle, courses, room


def test_같은_강의실_같은_시간에_동시에_등록해도_한_강좌만_저장한다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, courses, room = arena.build(build)
    arena.serve(bundle)
    real = schedule_service._check_schedule

    def slow(*args: Any, **kwargs: Any) -> None:
        real(*args, **kwargs)
        time.sleep(
            0.3
        )  # 겹침 확인을 마치고 저장하기 전의 틈을 넓힌다. 시설 잠금이 없으면 모두 이 틈에 들어온다

    monkeypatch.setattr(schedule_service, "_check_schedule", slow)
    staffs = [arena.staff(bundle, f"s{n}", "AU.CORS_R", "AU.CORS_W") for n in range(3)]

    def post(who: Staff, course: dict[str, Any], n: int) -> Callable[[], Any]:
        payload = {
            "weekday": "MON",
            "startTime": "10:00",
            "endTime": "11:30",
            "facilityId": str(room["FCLT_SN"]),
            "periodStart": "2026-11-02",
            "periodEnd": "2026-12-28",
        }
        return lambda: who.client.post(
            f"{ADMIN}/courses/{course['CORS_SN']}/schedules",
            json=payload,
            headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": f"sch-conc-{n:04d}"},
        )

    responses = parallel([post(s, c, n) for n, (s, c) in enumerate(zip(staffs, courses, strict=True))])
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 422, 422], codes
    assert len(arena.query("SELECT 1 FROM TB_CORS_SCHDL WHERE FCLT_SN=:f", f=room["FCLT_SN"])) == 1
