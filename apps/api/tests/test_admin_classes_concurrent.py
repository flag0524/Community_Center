# 분류 비활성·삭제와 강좌 등록이 겹쳐도 비활성 분류에 강좌가 남지 않고, 같은 이름의 동시 등록이 한 번만 되는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.domain.admin import class_service, education_service
from tests.arena import Arena, Staff, make_cycle, make_member, parallel
from tests.factory import RowFactory
from tests.world import START

pytestmark = pytest.mark.db

ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> tuple[int, dict[str, Any], dict[str, Any], int]:
    bundle = f.bundle()
    dong = f.make("TB_DONG", OPER_BNDL_SN=bundle)
    return bundle, make_cycle(f, bundle), dong, make_member(f, bundle, "teacher")


def post(who: Staff, path: str, body: dict[str, Any], key: str) -> Callable[[], Any]:
    return lambda: who.client.post(
        f"{ADMIN}{path}", json=body, headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key}
    )


def test_같은_이름을_동시에_등록해도_한_분류만_만든다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    real = class_service._key_free

    def slow(*args: Any, **kwargs: Any) -> None:
        real(*args, **kwargs)
        time.sleep(0.3)  # 중복 확인을 마치고 저장하기 전의 틈을 넓힌다. 잠금이 없으면 모두 이 틈에 들어온다

    monkeypatch.setattr(class_service, "_key_free", slow)
    bundle, *_ = arena.build(build)
    arena.serve(bundle)
    staffs = [arena.staff(bundle, f"s{n}", "AU.CORS_R", "AU.CORS_W") for n in range(4)]
    responses = parallel(
        [
            post(s, "/course-classes", {"name": " 요가 ", "sortSeq": 1}, f"clsf-conc-{n:04d}")
            for n, s in enumerate(staffs)
        ]
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 422, 422, 422], codes
    assert len(arena.query("SELECT 1 FROM TB_CORS_CLSF WHERE OPER_BNDL_SN=:b", b=bundle)) == 1


def test_강좌_등록_중에_분류를_비활성하려_해도_비활성_분류에_강좌가_남지_않는다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, cycle, dong, teacher = arena.build(build)
    arena.serve(bundle)
    boss = arena.staff(bundle, "boss", "AU.CORS_R", "AU.CORS_W", "AU.CONF_W")
    other = arena.staff(bundle, "other", "AU.CORS_R", "AU.CORS_W")
    made = post(boss, "/course-classes", {"name": "체육", "sortSeq": 1}, "clsf-conc-0001")().json()
    with arena.migrated.begin() as connection:
        instructor = RowFactory(connection, arena.schema).make(
            "TB_INSTR",
            OPER_BNDL_SN=bundle,
            MBR_SN=teacher,
            INSTR_STTS_CD="IS.APPROVE",
            RLS_YN="Y",
            APRV_DT=START,
            APRV_MNGR_SN=boss.admin_sn,
        )
    real = education_service._approved_instructor

    def slow(*args: Any) -> bool:
        time.sleep(0.8)  # 분류를 확인한 뒤 저장하기 전의 틈을 넓힌다. 이 동안 분류 행을 잡고 있다
        return bool(real(*args))

    monkeypatch.setattr(education_service, "_approved_instructor", slow)
    course_body = {
        "cycleId": str(cycle["EDU_CYCL_SN"]),
        "dongId": str(dong["DONG_SN"]),
        "classId": made["classId"],
        "name": "건강요가",
        "instructorId": str(instructor["INSTR_SN"]),
        "capacity": 10,
        "waitCapacity": 3,
        "tuition": 30000,
        "receptionStart": "2026-11-08T00:00:00+00:00",
        "receptionEnd": "2026-11-28T00:00:00+00:00",
        "outsideReceptionStart": None,
        "educationStart": "2026-11-15",
        "educationEnd": "2026-12-20",
        "description": "설명",
    }
    create_course = post(boss, "/courses", course_body, "course-conc-0001")

    def deactivate() -> Any:
        time.sleep(0.3)  # 강좌 등록이 분류를 확인한 뒤에 비활성 요청이 들어오게 한다
        return other.client.post(
            f"{ADMIN}/course-classes/{made['classId']}/deactivate",
            json={"version": 1},
            headers={"X-CSRF-Token": other.csrf},
        )

    course_response, off_response = parallel([create_course, deactivate])
    assert course_response.status_code == 201, course_response.text
    assert off_response.status_code == 422, off_response.text  # 연결 강좌가 생기고서야 센다
    [state] = arena.query("SELECT USE_YN u FROM TB_CORS_CLSF WHERE CORS_CLSF_SN=:s", s=made["classId"])
    assert state["u"] == "Y"
    assert len(arena.query("SELECT 1 FROM TB_CORS WHERE CORS_CLSF_SN=:s", s=made["classId"])) == 1
