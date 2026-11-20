# 같은 회원의 동시 지원과 승인 중의 지원서 수정이 겹쳐도 한 번만 반영되는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text

from app.auth.member_phone import sealed_columns
from app.domain.admin import instructor_review_service
from app.domain.instructor import service
from tests.arena import Applicant, Arena, make_member, parallel
from tests.factory import TEST_SECRET, RowFactory
from tests.world import START

pytestmark = pytest.mark.db

API = "/api/v1"
ADMIN = "/api/admin/v1"


def build(f: RowFactory) -> tuple[int, int, int, int]:
    bundle = f.bundle()
    member = make_member(f, bundle, "applicant")
    board = f.make("TB_BBS", OPER_BNDL_SN=bundle)
    writer = f.make("TB_MNGR", LGN_ID=f"w{bundle}", PSWD_HASH_VL="x" * 20, MNGR_NM="작성자")
    pst = f.make(
        "TB_PST",
        OPER_BNDL_SN=bundle,
        BBS_SN=board["BBS_SN"],
        WRT_MNGR_SN=writer["MNGR_SN"],
        PST_TTL="강사 모집",
        PST_CN="본문",
        REG_DT=START,
    )
    rcrt = f.make(
        "TB_INSTR_RCRT",
        OPER_BNDL_SN=bundle,
        PST_SN=pst["PST_SN"],
        RCRT_BGNG_DT=START.replace(day=1),
        RCRT_END_DT=START.replace(day=28),
        RCRT_NOPE=2,
    )
    f.make(
        "TB_CORS_CLSF",
        OPER_BNDL_SN=bundle,
        REG_MNGR_SN=writer["MNGR_SN"],
        CORS_CLSF_NM="생활체육",
        CLSF_NM_KEY="생활체육",
        SORT_SEQ=1,
        USE_YN="Y",
        DEL_YN="N",
    )
    return bundle, member, int(rcrt["INSTR_RCRT_SN"]), int(writer["MNGR_SN"])


def prepare(arena: Arena, member: int, writer: int) -> None:
    """회원에게 휴대전화를 주고, 팩토리가 만든 작성자 관리자를 시험이 끝날 때 지우도록 등록한다."""
    arena.admins.append(writer)
    sealed = sealed_columns(TEST_SECRET, "01055556666")
    with arena.migrated.begin() as connection:
        connection.execute(
            text("UPDATE TB_MBR SET MBL_TELNO_ENCPT_VL=:e, MBL_TELNO_SRCH_HASH_VL=:h WHERE MBR_SN=:m"),
            {"e": sealed["MBL_TELNO_ENCPT_VL"], "h": sealed["MBL_TELNO_SRCH_HASH_VL"], "m": member},
        )


def form(rcrt: int, **values: Any) -> dict[str, Any]:
    return {
        "recruitmentId": str(rcrt),
        "desiredCourse": "요가 기초반",
        "categoryName": "생활체육",
        "career": "요가 지도 10년",
        **values,
    }


def post(who: Applicant, path: str, key: str, payload: dict[str, Any]) -> Callable[[], Any]:
    return lambda: who.client.post(
        f"{API}{path}", json=payload, headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key}
    )


def test_같은_회원이_같은_공고에_다른_키로_동시에_지원해도_한_건만_접수한다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, rcrt, writer = arena.build(build)
    prepare(arena, member, writer)
    arena.serve(bundle)
    real = service._applied

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(
            0.5
        )  # 지원한 적이 없다고 확인한 뒤 저장하기 전의 틈을 넓힌다. 회원 행 잠금이 없으면 둘 다 접수한다
        return result

    monkeypatch.setattr(service, "_applied", slow)
    one, two = (
        arena.applicant(member, bundle) for _ in range(2)
    )  # 세션이 같으면 이미 한 줄로 서므로 따로 만든다
    responses = parallel(
        [
            post(one, "/me/instructor-applications", "inst-conc-0001", form(rcrt)),
            post(two, "/me/instructor-applications", "inst-conc-0002", form(rcrt)),
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_INSTR_APLY WHERE MBR_SN=:m", m=member)) == 1


def test_같은_키의_동시_지원은_같은_접수건을_돌려준다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, member, rcrt, writer = arena.build(build)
    prepare(arena, member, writer)
    arena.serve(bundle)
    real = service._applied

    def slow(*args: Any) -> bool:
        result = bool(real(*args))
        time.sleep(0.3)
        return result

    monkeypatch.setattr(service, "_applied", slow)
    sessions = [arena.applicant(member, bundle) for _ in range(3)]
    responses = parallel(
        [post(s, "/me/instructor-applications", "inst-conc-same1", form(rcrt)) for s in sessions]
    )
    assert [r.status_code for r in responses] == [201] * 3, [r.text for r in responses]
    assert len({r.json()["applicationId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_INSTR_APLY WHERE MBR_SN=:m", m=member)) == 1


def test_관리자가_승인하는_동안_지원서를_고쳐도_승인_뒤에는_바뀌지_않는다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, rcrt, writer = arena.build(build)
    prepare(arena, member, writer)
    arena.serve(bundle)
    who = arena.applicant(member, bundle)
    created = post(who, "/me/instructor-applications", "inst-conc-0003", form(rcrt))().json()
    sn = created["applicationId"]
    boss = arena.staff(bundle, "boss", "AU.INSTR_W")
    real = instructor_review_service._approve_instructor

    def slow(*args: Any) -> int:
        result = int(real(*args))
        time.sleep(0.8)  # 승인이 지원서 행을 잠근 채 머무는 동안 수정이 들어오게 한다
        return result

    monkeypatch.setattr(instructor_review_service, "_approve_instructor", slow)

    def approve() -> Any:
        return boss.client.put(
            f"{ADMIN}/instructor-applications/{sn}",
            json={"status": "APPROVED", "reason": None, "isPublic": False, "memo": None, "version": 1},
            headers={"X-CSRF-Token": boss.csrf},
        )

    def edit() -> Any:
        time.sleep(0.3)
        return who.client.put(
            f"{API}/me/instructor-applications/{sn}",
            json=form(rcrt, career="승인 직전에 바꾼 경력"),
            headers={"X-CSRF-Token": who.csrf},
        )

    approved, edited = parallel([approve, edit])
    assert approved.status_code == 200, approved.text
    assert edited.status_code == 422, edited.text
    [row] = arena.query("SELECT CRR_CN c, SRNG_STTS_CD s FROM TB_INSTR_APLY WHERE INSTR_APLY_SN=:s", s=sn)
    assert (row["c"], row["s"]) == ("요가 지도 10년", "IA.APPROVE")
