# 관리자 환불 검토·집행(범위·권한, 보류·승인·반려, 한도, PG 취소 집행·재처리, 수동 이체, 대리 접수)을 실제 앱과 MariaDB로 확인하는 시험
import itertools
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.pg.base import CancelOutcome
from app.auth.crypto import encrypt
from app.auth.deps import session_csrf
from app.auth.sessions import issue_session
from app.routers.deps import ADMIN_SESSION_COOKIE_NAME
from tests.test_admin_access import assign, dong, role
from tests.test_applications_read import RESIDENT, application, payment
from tests.test_applications_read import open_course as _open_course
from tests.world import ADMIN, START, World, make_admin, make_member

pytestmark = pytest.mark.db

_keys = itertools.count(1)
DAY = timedelta(days=1)


class Actor:
    def __init__(self, row: dict[str, Any], token: str, csrf: str) -> None:
        self.row, self.token, self.csrf = row, token, csrf

    @property
    def sn(self) -> int:
        return int(self.row["MNGR_SN"])


def staff(w: World, login: str, *codes: str, kind: str = "SK.GROUP", dong_sn: Any = None) -> Actor:
    """역할 하나와 배정 하나를 가진 담당자. 세션은 바로 발급한다(로그인 흐름은 별도 시험)."""
    row = make_admin(w, login)
    assign(w, row, role(w, f"r-{login}", *codes), kind, dong_sn=dong_sn)
    token, record = issue_session(
        w.db, bundle_sn=None, member_sn=None, admin_sn=int(row["MNGR_SN"]), now=START
    )
    return Actor(row, token, session_csrf(w.settings, record))


def use(w: World, who: Actor) -> None:
    w.client.cookies.set(ADMIN_SESSION_COOKIE_NAME, who.token)
    w.db.commit()  # 만든 데이터를 고정한다. 오류 응답의 롤백이 그 앞에 만든 행까지 되돌리지 않게 한다
    w.current = who  # type: ignore[attr-defined]


def call(w: World, method: str, path: str, body: dict[str, Any] | None = None, **headers: str) -> Any:
    who: Actor = w.current  # type: ignore[attr-defined]
    sent = {"X-CSRF-Token": who.csrf, **headers}
    return w.client.request(method, f"{ADMIN}{path}", json=body, headers=sent)


def course(w: World, **values: Any) -> dict[str, Any]:
    return _open_course(w, **{"EDU_BGNG_YMD": "20261201", "EDU_END_YMD": "20261231", **values})


def refund(
    w: World,
    *,
    status: str = "RS.REQUEST",
    amount: int = 30000,
    paid: int = 30000,
    row: dict[str, Any] | None = None,
    by_member: bool = True,
    approver: Actor | None = None,
    **values: Any,
) -> dict[str, Any]:
    """접수된 환불 한 건. 접수하면 신청은 취소돼 있으므로 신청은 ES.CANCEL로 만든다."""
    row = row or course(w)
    member = make_member(w, f"m{next(_keys)}", MBR_NM="홍길동", **RESIDENT)
    app = application(w, member, row, "ES.CANCEL", TTCHG_AMT=paid, STLM_PRNMNT_AMT=paid)
    paid_row = payment(w, app, "PS.PAID", STLM_AMT=paid)
    extra: dict[str, Any] = {}
    if status == "RS.HOLD":
        extra["HLDOF_RSN"] = "서류 확인"
    if status == "RS.REJECT":
        extra["RJCT_RSN"] = "불가"
    if approver is not None:
        extra.update(APRV_MNGR_SN=approver.sn, APRV_DT=START)
    if by_member:
        extra["DMND_MBR_SN"] = member["MBR_SN"]
    made = w.factory.make(
        "TB_RFND",
        STLM_SN=paid_row["STLM_SN"],
        RFND_AMT=amount,
        RFND_STTS_CD=status,
        **{"RFND_DMND_DT": START, **extra, **values},
    )
    made["STLM_NO"] = paid_row["STLM_NO"]
    return made


def state(w: World, r: dict[str, Any]) -> Any:
    return w.db.execute(text("SELECT * FROM TB_RFND WHERE RFND_SN=:r"), {"r": r["RFND_SN"]}).mappings().one()


def version(w: World, r: dict[str, Any]) -> int:
    return int(state(w, r)["RCRD_VER"])


def jobs(w: World, r: dict[str, Any]) -> list[str]:
    rows = w.db.execute(
        text(
            "SELECT JOB_CD FROM TB_JOB_HSTRY WHERE TRGT_TBL_NM='TB_RFND' AND TRGT_KEY_VL=:k ORDER BY JOB_HSTRY_SN"
        ),
        {"k": str(r["RFND_SN"])},
    )
    return [str(x[0]) for x in rows]


# --- 인증·권한·범위 -----------------------------------------------------------------------------


def test_로그인하지_않으면_401이고_권한이_없으면_403이다(world: World) -> None:
    assert world.client.get(f"{ADMIN}/refunds").status_code == 401
    nobody = staff(world, "nobody", "AU.STLM_R")
    use(world, nobody)
    assert call(world, "GET", "/refunds").status_code == 403


def test_사용중지된_계정은_세션이_있어도_인증되지_않는다(world: World) -> None:
    who = staff(world, "off", "AU.RFND_A")
    world.db.execute(text("UPDATE TB_MNGR SET USE_YN='N' WHERE MNGR_SN=:a"), {"a": who.sn})
    use(world, who)
    assert call(world, "GET", "/refunds").status_code == 401


def test_상태를_바꾸는_요청은_CSRF가_없으면_403이다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    response = world.client.put(
        f"{ADMIN}/refunds/{target['RFND_SN']}/hold", json={"reason": "확인", "version": 1}
    )
    assert response.status_code == 403
    assert state(world, target)["RFND_STTS_CD"] == "RS.REQUEST"


def test_동_담당자는_자기_동_강좌의_환불만_보고_다른_동은_404이다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    who = staff(world, "d1", "AU.RFND_A", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    visible = refund(world, row=course(world, DONG_SN=mine["DONG_SN"]))
    hidden = refund(world, row=course(world, CORS_NM="다른동", DONG_SN=other["DONG_SN"]))
    common = refund(world, row=course(world, CORS_NM="공통"))  # 동이 없는 묶음 공통 강좌
    use(world, who)
    listed = call(world, "GET", "/refunds").json()
    assert [i["refundId"] for i in listed["items"]] == [str(visible["RFND_SN"])]
    assert call(world, "GET", f"/refunds/{visible['RFND_SN']}").status_code == 200
    for target in (hidden, common):
        assert call(world, "GET", f"/refunds/{target['RFND_SN']}").status_code == 404
        r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/hold", {"reason": "x", "version": 1})
        assert r.status_code == 404
        assert state(world, target)["RFND_STTS_CD"] == "RS.REQUEST"


def test_목록은_승인_권한만_열고_상세는_승인이나_집행_권한으로_본다(world: World) -> None:
    only_x = staff(world, "x", "AU.RFND_X")
    target = refund(world)
    use(world, only_x)
    assert call(world, "GET", "/refunds").status_code == 403
    assert call(world, "GET", f"/refunds/{target['RFND_SN']}").status_code == 200


def test_승인_권한만으로는_집행할_수_없다(world: World) -> None:
    only_a = staff(world, "a", "AU.RFND_A")
    target = refund(world, status="RS.APPROVE", approver=staff(world, "other", "AU.RFND_A"))
    use(world, only_a)
    r = call(world, "POST", f"/refunds/{target['RFND_SN']}/execute", {"version": version(world, target)})
    assert r.status_code == 403 and world.pg.cancel_calls == []


# --- 목록·상세 ----------------------------------------------------------------------------------


def test_검토할_건을_오래된_순으로_먼저_보이고_나머지는_최신순이다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A", "AU.RFND_X")
    done = refund(world, status="RS.DONE", RFND_DMND_DT=START, RFND_DT=START)
    new_req = refund(world, RFND_DMND_DT=START - 1 * DAY)
    old_hold = refund(world, status="RS.HOLD", RFND_DMND_DT=START - 5 * DAY)
    reject = refund(world, status="RS.REJECT", RFND_DMND_DT=START - 2 * DAY)
    use(world, who)
    body = call(world, "GET", "/refunds").json()
    ids = [i["refundId"] for i in body["items"]]
    assert ids == [str(r["RFND_SN"]) for r in (old_hold, new_req, done, reject)] and body["total"] == 4


def test_목록은_상태와_요청자와_기간으로_거른다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    member_req = refund(world, RFND_DMND_DT=START)
    admin_req = refund(world, by_member=False, DMND_MNGR_SN=who.sn, RFND_DMND_DT=START - 10 * DAY)
    use(world, who)

    def ids(query: str) -> list[str]:
        return [i["refundId"] for i in call(world, "GET", f"/refunds?{query}").json()["items"]]

    assert ids("requester=ADMIN") == [str(admin_req["RFND_SN"])]
    assert ids("requester=MEMBER") == [str(member_req["RFND_SN"])]
    assert ids("status=ON_HOLD") == []
    assert ids("from=2026-11-09") == [str(member_req["RFND_SN"])]
    assert ids("to=2026-11-08") == [str(admin_req["RFND_SN"])]
    assert len(ids("from=2026-10-30&to=2026-11-09")) == 2


@pytest.mark.parametrize(
    ("days_ago", "business_days", "overdue"),
    [(6, 4, True), (7, 5, True), (5, 3, False), (4, 2, False), (2, 1, False)],  # 오늘은 월요일이다
    ids=["화요일_접수", "월요일_접수", "수요일_접수", "목요일_접수", "토요일_접수_주말은_세지_않음"],
)
def test_심사_목표_3영업일을_넘기면_지연이다(
    world: World, days_ago: int, business_days: int, overdue: bool
) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    refund(world, RFND_DMND_DT=START - days_ago * DAY)
    use(world, who)
    item = call(world, "GET", "/refunds").json()["items"][0]
    assert (item["elapsedBusinessDays"], item["overdue"]) == (business_days, overdue)


def test_지연은_검토_중인_건에만_붙는다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    refund(world, status="RS.DONE", RFND_DMND_DT=START - 20 * DAY, RFND_DT=START)
    use(world, who)
    assert call(world, "GET", "/refunds").json()["items"][0]["overdue"] is False


def test_상세는_산정_근거와_예약액과_이력을_보인다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A", "AU.RFND_X")
    first = refund(world, status="RS.DONE", amount=10000, paid=30000, RFND_DT=START)
    target = refund(world)
    # 같은 결제에 완료 환불이 있어 예약액이 잡힌다
    world.db.execute(
        text("UPDATE TB_RFND SET STLM_SN=:s WHERE RFND_SN=:r"),
        {"s": state(world, first)["STLM_SN"], "r": target["RFND_SN"]},
    )
    use(world, who)
    body = call(world, "GET", f"/refunds/{target['RFND_SN']}").json()
    assert (body["paidAmount"], body["reservedAmount"], body["remainingAmount"]) == (30000, 10000, 20000)
    assert body["baselineAmount"] == 30000 and body["baselineRule"] == "BEFORE_START"
    assert body["requesterName"] == "홍*동" and body["executionMethod"] == "CANCEL_PAYMENT"
    assert body["canReview"] is True and body["canExecute"] is False and body["version"] == 1
    assert body["manualAccount"] is None and body["evidenceCount"] == 0


# --- 보류·승인·반려 -----------------------------------------------------------------------------


def test_보류하고_해제하면_상태와_버전이_바뀌고_이력이_남는다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    held = call(world, "PUT", f"/refunds/{target['RFND_SN']}/hold", {"reason": "서류 확인", "version": 1})
    assert held.status_code == 200 and held.json()["status"] == "ON_HOLD"
    assert held.json()["decisionReason"] == "서류 확인" and held.json()["version"] == 2
    released = call(world, "POST", f"/refunds/{target['RFND_SN']}/release-hold", {"version": 2})
    assert released.json()["status"] == "REQUESTED" and released.json()["decisionReason"] is None
    assert jobs(world, target) == ["RFND_HOLD", "RFND_RELEASE"]
    assert [h["status"] for h in released.json()["history"]] == ["ON_HOLD", "REQUESTED"]


def test_화면이_읽은_버전과_다르면_409이고_바뀌지_않는다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/hold", {"reason": "x", "version": 7})
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    assert state(world, target)["RFND_STTS_CD"] == "RS.REQUEST"


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("hold", {"reason": "x", "version": 1}, "RS.HOLD"),
        ("release-hold", {"version": 1}, "RS.REQUEST"),
        ("approve", {"amount": 1000, "version": 1}, "RS.HOLD"),
        ("reject", {"reason": "x", "version": 1}, "RS.HOLD"),
        ("hold", {"reason": "x", "version": 1}, "RS.DONE"),
        ("approve", {"amount": 1000, "version": 1}, "RS.REJECT"),
    ],
    ids=[
        "보류를_또_보류",
        "접수건_보류해제",
        "보류건_바로승인",
        "보류건_바로반려",
        "완료건_보류",
        "반려건_승인",
    ],
)
def test_현재_상태에서_할_수_없는_전이는_409이다(
    world: World, path: str, body: dict[str, Any], status: str
) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world, status=status)
    use(world, who)
    method = "POST" if path == "release-hold" else "PUT"
    r = call(world, method, f"/refunds/{target['RFND_SN']}/{path}", body)
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT_STATE"
    assert state(world, target)["RFND_STTS_CD"] == status


def test_승인하면_승인자가_남고_한도가_예약된다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/approve", {"amount": 30000, "version": 1})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert (r.json()["approvedAmount"], r.json()["decidedBy"]) == (30000, "김관리")
    row = state(world, target)
    assert row["APRV_MNGR_SN"] == who.sn and row["APRV_DT"] == START
    assert jobs(world, target) == ["RFND_APPROVE"]


def test_요청액보다_적게는_승인하고_많게는_승인하지_못한다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    low, high = refund(world, amount=20000), refund(world, amount=20000)
    use(world, who)
    over = call(world, "PUT", f"/refunds/{high['RFND_SN']}/approve", {"amount": 20001, "version": 1})
    assert over.status_code == 422 and over.json()["code"] == "RULE_REJECTED"
    ok = call(world, "PUT", f"/refunds/{low['RFND_SN']}/approve", {"amount": 15000, "version": 1})
    assert ok.status_code == 200 and state(world, low)["RFND_AMT"] == 15000


def test_승인액이_승인_시점의_반환_기준액을_넘으면_거절한다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    # 개강 후 2개월 차의 90,000원 결제(월 30,000원). 11월 시작, 오늘 11월 → 경과 1개월 → 기준액 60,000원
    row = course(world, EDU_BGNG_YMD="20261101", EDU_END_YMD="20270131")
    ok = refund(world, row=row, paid=90000, amount=60000)
    over = refund(world, row=row, paid=90000, amount=70000)
    use(world, who)
    r = call(world, "PUT", f"/refunds/{over['RFND_SN']}/approve", {"amount": 70000, "version": 1})
    assert r.status_code == 422 and r.json()["code"] == "RFND_LIMIT_EXCEEDED"
    assert state(world, over)["RFND_STTS_CD"] == "RS.REQUEST"
    assert (
        call(world, "PUT", f"/refunds/{ok['RFND_SN']}/approve", {"amount": 60000, "version": 1}).status_code
        == 200
    )


def test_승인액은_기준액과_같으면_되고_1원이라도_넘으면_거절한다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    row = course(world, EDU_BGNG_YMD="20261101", EDU_END_YMD="20270131")  # 90,000원 결제의 기준액은 60,000원
    edge, over = (
        refund(world, row=row, paid=90000, amount=60001),
        refund(world, row=row, paid=90000, amount=60001),
    )
    use(world, who)
    r = call(world, "PUT", f"/refunds/{over['RFND_SN']}/approve", {"amount": 60001, "version": 1})
    assert r.status_code == 422 and r.json()["code"] == "RFND_LIMIT_EXCEEDED"
    ok = call(world, "PUT", f"/refunds/{edge['RFND_SN']}/approve", {"amount": 60000, "version": 1})
    assert ok.status_code == 200


@pytest.mark.parametrize(
    ("other_status", "holds"),
    [
        ("RS.APPROVE", True),
        ("RS.PENDING", True),
        ("RS.DONE", True),
        ("RS.FAIL", True),
        ("RS.REQUEST", False),
        ("RS.HOLD", False),
        ("RS.REJECT", False),
    ],
)
def test_승인_PENDING_완료_실패_환불만_한도를_차지한다(world: World, other_status: str, holds: bool) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    other = refund(world, status=other_status, amount=20000)
    target = refund(world, amount=20000)
    world.db.execute(
        text("UPDATE TB_RFND SET STLM_SN=:s WHERE RFND_SN=:r"),
        {"s": state(world, other)["STLM_SN"], "r": target["RFND_SN"]},
    )
    use(world, who)
    r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/approve", {"amount": 20000, "version": 1})
    assert (r.status_code == 422) is holds


def test_같은_결제의_다른_환불이_차지한_금액과_합쳐_한도를_넘으면_거절한다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    first = refund(world, status="RS.APPROVE", amount=20000, approver=who)
    second = refund(world, amount=20000)
    world.db.execute(
        text("UPDATE TB_RFND SET STLM_SN=:s WHERE RFND_SN=:r"),
        {"s": state(world, first)["STLM_SN"], "r": second["RFND_SN"]},
    )
    use(world, who)
    r = call(world, "PUT", f"/refunds/{second['RFND_SN']}/approve", {"amount": 20000, "version": 1})
    assert r.status_code == 422 and r.json()["code"] == "RFND_LIMIT_EXCEEDED"
    small = call(world, "PUT", f"/refunds/{second['RFND_SN']}/approve", {"amount": 10000, "version": 1})
    assert small.status_code == 200


def test_반려하면_사유가_남고_신청은_되살리지_않는다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/reject", {"reason": "대상 아님", "version": 1})
    assert (
        r.status_code == 200
        and r.json()["status"] == "REJECTED"
        and r.json()["decisionReason"] == "대상 아님"
    )
    app = world.db.execute(text("SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")).scalars().all()
    assert app == ["ES.CANCEL"] and jobs(world, target) == ["RFND_REJECT"]


def test_사유가_없는_보류와_반려는_400이다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    target = refund(world)
    use(world, who)
    for path in ("hold", "reject"):
        r = call(world, "PUT", f"/refunds/{target['RFND_SN']}/{path}", {"reason": "", "version": 1})
        assert r.status_code == 400
    assert state(world, target)["RFND_STTS_CD"] == "RS.REQUEST"


# --- 집행 ---------------------------------------------------------------------------------------


def two(world: World) -> tuple[Actor, Actor]:
    return staff(world, "approver", "AU.RFND_A"), staff(world, "executor", "AU.RFND_X")


def execute(w: World, r: dict[str, Any], **headers: str) -> Any:
    return call(w, "POST", f"/refunds/{r['RFND_SN']}/execute", {"version": version(w, r)}, **headers)


def test_승인한_담당자가_아닌_사람이_집행하면_PG_취소가_한_번_나가고_완료된다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    use(world, executor)
    r = execute(world, target)
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    assert r.json()["executedBy"] == "김관리" and r.json()["executionResult"] == "환불 완료"
    [only] = world.pg.cancel_calls
    assert (only.order_no, only.amount) == (target["STLM_NO"], 30000)
    assert only.idempotency_key == f"RFND-{world.bundle}-{target['RFND_SN']}"
    row = state(world, target)
    assert row["RFND_DT"] == START and row["IMPL_MNGR_SN"] == executor.sn and row["PG_RFND_ID"]
    assert jobs(world, target) == ["RFND_EXECUTE", "RFND_DONE"]
    assert (
        world.db.execute(text("SELECT STLM_STTS_CD FROM TB_STLM")).scalar() == "PS.PAID"
    )  # 원결제는 덮어쓰지 않는다


def test_승인한_담당자는_집행할_수_없다(world: World) -> None:
    both = staff(world, "both", "AU.RFND_A", "AU.RFND_X")
    target = refund(world, status="RS.APPROVE", approver=both)
    use(world, both)
    shown = call(world, "GET", f"/refunds/{target['RFND_SN']}").json()
    assert shown["canExecute"] is False and "승인한 담당자" in shown["executeNote"]
    r = execute(world, target)
    assert r.status_code == 422 and r.json()["code"] == "RULE_REJECTED"
    assert world.pg.cancel_calls == [] and state(world, target)["RFND_STTS_CD"] == "RS.APPROVE"


def test_집행할_수_있는_담당자에게는_집행_가능으로_보인다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    use(world, executor)
    assert call(world, "GET", f"/refunds/{target['RFND_SN']}").json()["canExecute"] is True


@pytest.mark.parametrize("status", ["RS.REQUEST", "RS.HOLD", "RS.REJECT", "RS.DONE", "RS.PENDING"])
def test_승인_또는_실패가_아니면_집행할_수_없다(world: World, status: str) -> None:
    approver, executor = two(world)
    target = refund(world, status=status, approver=approver)
    use(world, executor)
    r = execute(world, target)
    assert r.status_code == 409 and world.pg.cancel_calls == []


def test_PG가_거절하면_실패로_남고_같은_키로_재처리한다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    world.pg.next_cancel = CancelOutcome.REJECTED
    use(world, executor)
    failed = execute(world, target)
    assert failed.json()["status"] == "FAILED" and failed.json()["executionResult"] == "MOCK_CANCEL_REJECTED"
    assert failed.json()["canExecute"] is True
    retry = execute(world, target)
    assert retry.json()["status"] == "DONE"
    keys = {c.idempotency_key for c in world.pg.cancel_calls}
    assert len(world.pg.cancel_calls) == 2 and keys == {f"RFND-{world.bundle}-{target['RFND_SN']}"}
    assert jobs(world, target) == ["RFND_EXECUTE", "RFND_FAIL", "RFND_EXECUTE", "RFND_DONE"]


def test_응답이_유실돼도_같은_키로_조회해_완료로_확정한다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    world.pg.cancel_raises = True  # PG는 취소했는데 응답만 유실
    use(world, executor)
    r = execute(world, target)
    assert r.json()["status"] == "DONE" and len(world.pg.cancel_calls) == 1
    assert world.pg.cancel_lookups == [f"RFND-{world.bundle}-{target['RFND_SN']}"]


def test_PG를_부르는_사이_다른_곳에서_이미_정리한_환불은_다시_반영하지_않는다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    original = world.pg.cancel

    def settled_elsewhere(**kwargs: Any) -> Any:
        # 호출하는 사이 다른 경로(재조회 워커 등)가 먼저 완료로 정리했다
        world.db.execute(
            text(
                "UPDATE TB_RFND SET RFND_STTS_CD='RS.DONE', RFND_DT=:t, RCRD_VER=RCRD_VER+1 WHERE RFND_SN=:r"
            ),
            {"t": START, "r": target["RFND_SN"]},
        )
        return original(**kwargs)

    world.pg.cancel = settled_elsewhere  # type: ignore[method-assign]
    use(world, executor)
    r = execute(world, target)
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    assert jobs(world, target) == ["RFND_EXECUTE"]  # 완료 이력이나 사건을 한 번 더 남기지 않는다
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_STLM_EVENT")).scalar() == 0


def test_결과를_끝내_알_수_없으면_처리_중으로_두고_재집행을_막는다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    world.pg.next_cancel = CancelOutcome.UNKNOWN
    use(world, executor)
    r = execute(world, target)
    assert r.status_code == 200 and r.json()["status"] == "PENDING" and r.json()["canExecute"] is False
    again = execute(world, target)
    assert again.status_code == 409 and len(world.pg.cancel_calls) == 1


def test_PG가_다른_금액을_취소했다고_하면_완료로_보지_않고_확인_필요_사건을_남긴다(world: World) -> None:
    approver, executor = two(world)
    target = refund(world, status="RS.APPROVE", approver=approver)
    world.pg.answer_cancel_amount = 29000
    use(world, executor)
    r = execute(world, target)
    assert r.json()["status"] == "PENDING"
    event = (
        world.db.execute(text("SELECT PRCS_STTS_CD, FAIL_RSN, RFND_SN FROM TB_STLM_EVENT")).mappings().one()
    )
    assert event["PRCS_STTS_CD"] == "EP.FAIL" and "불일치" in event["FAIL_RSN"]
    assert event["RFND_SN"] == target["RFND_SN"] and state(world, target)["RFND_DT"] is None


def test_재처리도_한도를_다시_검사한다(world: World) -> None:
    approver, executor = two(world)
    failed = refund(world, status="RS.FAIL", amount=20000, approver=approver)
    other = refund(world, status="RS.DONE", amount=20000, RFND_DT=START)
    world.db.execute(
        text("UPDATE TB_RFND SET STLM_SN=:s WHERE RFND_SN=:r"),
        {"s": state(world, failed)["STLM_SN"], "r": other["RFND_SN"]},
    )
    use(world, executor)
    r = execute(world, failed)
    assert r.status_code == 422 and r.json()["code"] == "RFND_LIMIT_EXCEEDED" and world.pg.cancel_calls == []


# --- 수동 계좌환불 ------------------------------------------------------------------------------


def manual(w: World, approver: Actor) -> dict[str, Any]:
    secret = w.settings.secret_key
    return refund(
        w,
        status="RS.APPROVE",
        approver=approver,
        RFND_BANK_CD="004",
        RFND_ACTNO_ENCPT_VL=encrypt(secret, "110123456789"),
        RFND_DPSTR_ENCPT_VL=encrypt(secret, "홍길동"),
    )


def test_수동_계좌환불은_계좌를_가려서_보이고_집행은_PG를_부르지_않는다(world: World) -> None:
    approver, executor = two(world)
    target = manual(world, approver)
    use(world, executor)
    shown = call(world, "GET", f"/refunds/{target['RFND_SN']}").json()
    assert shown["executionMethod"] == "MANUAL_TRANSFER"
    assert shown["manualAccount"] == {
        "bankName": "004",
        "holderMasked": "홍*동",
        "accountMasked": "********6789",
    }
    assert "110123456789" not in str(shown)
    r = execute(world, target)
    assert r.json()["status"] == "PENDING" and r.json()["canConfirmTransfer"] is True
    assert world.pg.cancel_calls == []


def test_이체_완료를_확인해야_환불완료가_된다(world: World) -> None:
    approver, executor = two(world)
    target = manual(world, approver)
    use(world, executor)
    execute(world, target)
    r = call(world, "POST", f"/refunds/{target['RFND_SN']}/confirm-done", {"version": version(world, target)})
    assert r.status_code == 200 and r.json()["status"] == "DONE"
    assert state(world, target)["RFND_DT"] == START and jobs(world, target)[-1] == "RFND_DONE"


def test_승인한_담당자는_이체_완료도_확인할_수_없다(world: World) -> None:
    both = staff(world, "both", "AU.RFND_A", "AU.RFND_X")
    target = manual(world, both)
    world.db.execute(
        text("UPDATE TB_RFND SET RFND_STTS_CD='RS.PENDING' WHERE RFND_SN=:r"), {"r": target["RFND_SN"]}
    )
    use(world, both)
    r = call(world, "POST", f"/refunds/{target['RFND_SN']}/confirm-done", {"version": version(world, target)})
    assert r.status_code == 422 and state(world, target)["RFND_STTS_CD"] == "RS.PENDING"


def test_PG_취소_건과_처리_중이_아닌_건은_이체_확인을_할_수_없다(world: World) -> None:
    approver, executor = two(world)
    pg_pending = refund(world, status="RS.PENDING", approver=approver)
    not_pending = manual(world, approver)
    use(world, executor)
    for target in (pg_pending, not_pending):
        r = call(
            world, "POST", f"/refunds/{target['RFND_SN']}/confirm-done", {"version": version(world, target)}
        )
        assert r.status_code == 409


# --- 대리 접수 ----------------------------------------------------------------------------------


def key() -> str:
    return f"adm-{next(_keys):08d}"


def create(w: World, app_sn: Any, amount: int = 30000, idem: str | None = None) -> Any:
    return call(
        w,
        "POST",
        "/refunds",
        {"applicationNo": str(app_sn), "requestedAmount": amount, "reason": "방문 접수"},
        **{"Idempotency-Key": idem or key()},
    )


def paid_app(w: World, row: dict[str, Any], paid: int = 30000) -> dict[str, Any]:
    member = make_member(w, f"m{next(_keys)}", **RESIDENT)
    app = application(w, member, row, "ES.CONFIRM", TTCHG_AMT=paid, STLM_PRNMNT_AMT=paid)
    payment(w, app, "PS.PAID", STLM_AMT=paid)
    return app


def test_대리_접수하면_담당자_접수로_남고_신청은_취소되어_자리가_대기자에게_넘어간다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    row = course(world, RCRT_NOPE=1, WTNG_NOPE=5)
    app = paid_app(world, row)
    waiter = application(
        world, make_member(world, "w1", MBL_TELNO="01012345678", **RESIDENT), row, "ES.WAIT", WTNG_SEQ=1
    )
    use(world, who)
    r = create(world, app["ATNLC_APLY_SN"])
    assert r.status_code == 201 and r.json()["requester"] == "ADMIN" and r.json()["status"] == "REQUESTED"
    assert r.json()["requesterName"] == "김관리"
    rows = world.db.execute(text("SELECT ATNLC_APLY_SN, APLY_STTS_CD FROM TB_ATNLC_APLY")).mappings().all()
    assert {int(x["ATNLC_APLY_SN"]): x["APLY_STTS_CD"] for x in rows} == {
        int(app["ATNLC_APLY_SN"]): "ES.CANCEL",
        int(waiter["ATNLC_APLY_SN"]): "ES.HOLD",
    }
    saved = world.db.execute(text("SELECT DMND_MBR_SN, DMND_MNGR_SN FROM TB_RFND")).mappings().one()
    assert saved["DMND_MBR_SN"] is None and saved["DMND_MNGR_SN"] == who.sn
    assert jobs(world, {"RFND_SN": r.json()["refundId"]}) == ["RFND_REQUEST"]


def test_대리_접수는_원결제액을_넘는_금액과_진행_중_환불을_막는다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    app = paid_app(world, course(world))
    use(world, who)
    over = create(world, app["ATNLC_APLY_SN"], 30001)
    assert over.status_code == 422 and over.json()["code"] == "RFND_LIMIT_EXCEEDED"
    assert world.db.execute(text("SELECT APLY_STTS_CD FROM TB_ATNLC_APLY")).scalar() == "ES.CONFIRM"


def test_대리_접수_뒤_같은_신청에_다시_접수할_수_없다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    app = paid_app(world, course(world))
    use(world, who)
    assert create(world, app["ATNLC_APLY_SN"], 10000).status_code == 201
    again = create(world, app["ATNLC_APLY_SN"], 10000)
    assert again.status_code == 422 and again.json()["code"] == "RULE_REJECTED"


def test_대리_접수의_같은_키는_이전_결과이고_다른_신청이면_충돌이다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    row = course(world)
    first, second = paid_app(world, row), paid_app(world, row)
    use(world, who)
    idem = key()
    a, b = (
        create(world, first["ATNLC_APLY_SN"], 10000, idem),
        create(world, first["ATNLC_APLY_SN"], 10000, idem),
    )
    assert a.status_code == 201 and b.status_code == 201 and a.json()["refundId"] == b.json()["refundId"]
    clash = create(world, second["ATNLC_APLY_SN"], 10000, idem)
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_대리_접수는_담당_범위_밖이거나_없는_신청이면_404이다(world: World) -> None:
    mine, other = dong(world, "가동"), dong(world, "나동")
    who = staff(world, "d1", "AU.RFND_A", kind="SK.DONG", dong_sn=mine["DONG_SN"])
    outside = paid_app(world, course(world, DONG_SN=other["DONG_SN"]))
    inside = paid_app(world, course(world, CORS_NM="내강좌", DONG_SN=mine["DONG_SN"]))
    use(world, who)
    assert create(world, outside["ATNLC_APLY_SN"]).status_code == 404
    assert create(world, "99999999").status_code == 404
    assert create(world, "abc").status_code == 404
    assert world.db.execute(text("SELECT COUNT(*) FROM TB_RFND")).scalar() == 0
    assert create(world, inside["ATNLC_APLY_SN"]).status_code == 201


def test_대리_접수는_결제하지_않았거나_확정이_아니면_거절한다(world: World) -> None:
    who = staff(world, "boss", "AU.RFND_A")
    free = application(
        world,
        make_member(world, "f1", **RESIDENT),
        course(world),
        "ES.CONFIRM",
        TTCHG_AMT=0,
        STLM_PRNMNT_AMT=0,
    )
    use(world, who)
    r = create(world, free["ATNLC_APLY_SN"])
    assert r.status_code == 422 and r.json()["code"] == "RULE_REJECTED"


def test_접수_권한이_없으면_대리_접수가_403이다(world: World) -> None:
    only_x = staff(world, "x", "AU.RFND_X")
    app = paid_app(world, course(world))
    use(world, only_x)
    assert create(world, app["ATNLC_APLY_SN"]).status_code == 403
