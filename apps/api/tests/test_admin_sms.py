# 관리자 문자 발송(대상 산정·미리보기·최종 확인·멱등·이력)과 워커 발송으로 이어지는 흐름을 실제 앱과 MariaDB로 확인하는 시험
import hashlib
import itertools
from typing import Any

import pytest
from sqlalchemy import text

from app.adapters.sms.base import SendOutcome
from app.auth.crypto import decrypt, encrypt
from app.domain.admin import sms_service
from app.worker import jobs
from tests.test_admin_access import dong
from tests.test_admin_refunds import call, staff, use
from tests.test_applications_read import RESIDENT, application, open_course
from tests.world import START, World, make_member

pytestmark = pytest.mark.db

_n = itertools.count(1)


def person(
    w: World, name: str = "홍길동", phone: str | None = "01012345678", **values: Any
) -> dict[str, Any]:
    return make_member(w, f"sm{next(_n)}", MBR_NM=name, MBL_TELNO=phone, **{**RESIDENT, **values})


def enroll(
    w: World, c: dict[str, Any], state: str = "ES.CONFIRM", who: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    who = who or person(w, **kw)
    extra: dict[str, Any] = {}
    if state == "ES.WAIT":
        extra["WTNG_SEQ"] = next(_n)
    if state == "ES.HOLD":
        extra.update(SEAT_ALTMNT_DT=START, STLM_DDLN_DT=START)
    application(w, who, c, state, **extra)
    return who


def sender(w: World, *codes: str, **kw: Any) -> Any:
    who = staff(w, f"sn{next(_n)}", "AU.SMS_SEND", *codes, **kw)
    use(w, who)
    return who


def audience(**values: Any) -> dict[str, Any]:
    return {
        "scope": "CENTER",
        "courseIds": [],
        "statuses": ["CONFIRMED"],
        "content": "[조리읍] 수강 안내입니다.",
        **values,
    }


def send_body(count: int, **values: Any) -> dict[str, Any]:
    return {**audience(**values), "confirmed": True, "expectedRecipientCount": count}


def post_send(w: World, payload: dict[str, Any], key: str | None = None) -> Any:
    return call(w, "POST", "/sms", payload, **{"Idempotency-Key": key or f"sms-key-{next(_n):06d}"})


def rows(w: World, sql: str, **params: Any) -> list[Any]:
    return list(w.db.execute(text(sql), params).mappings())


# --- 권한·입력 ----------------------------------------------------------------------------------


def test_로그인이_없으면_401이고_발송_권한이_없으면_403이다(world: World) -> None:
    world.db.commit()
    assert world.client.get("/api/admin/v1/sms").status_code == 401
    use(world, staff(world, "x", "AU.POST_W", "AU.STAT_R"))
    for method, path, payload in (
        ("GET", "/sms", None),
        ("GET", "/sms/1", None),
        ("POST", "/sms/preview", audience()),
        ("POST", "/sms", send_body(1)),
    ):
        assert call(world, method, path, payload, **{"Idempotency-Key": "sms-key-0001"}).status_code == 403, (
            path
        )


def test_대상_조건이_틀리면_422이고_센터_전체는_센터_전체_범위만_쓴다(world: World) -> None:
    a = dong(world, "가동")
    mine = open_course(world, CORS_NM="가동 강좌", DONG_SN=a["DONG_SN"])
    other = open_course(world, CORS_NM="다른 강좌")
    sender(world)
    for payload, field in (
        (audience(scope="EVENT"), "scope"),
        (audience(courseIds=[str(mine["CORS_SN"])]), "courseIds"),  # 센터 전체에는 강좌를 고르지 않는다
        (audience(scope="COURSE"), "courseIds"),
        (audience(scope="COURSE", courseIds=["999999999"]), "courseIds"),
        (audience(content="   "), "content"),
        (audience(content="가" * 46), "content"),  # 한글 46자는 92바이트
        (audience(content="행사 안내 \U0001f600"), "content"),  # 문자로 보낼 수 없는 글자
    ):
        res = call(world, "POST", "/sms/preview", payload)
        assert res.status_code == 422 and field in res.json()["fields"], payload
    assert call(world, "POST", "/sms/preview", audience(statuses=[])).status_code in (400, 422)
    assert call(world, "POST", "/sms/preview", audience(content="가" * 45)).status_code == 200  # 90바이트까지
    sender(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    assert (
        call(world, "POST", "/sms/preview", audience()).status_code == 403
    )  # 센터 전체는 센터 전체 범위가 필요하다
    ok = call(world, "POST", "/sms/preview", audience(scope="COURSE", courseIds=[str(mine["CORS_SN"])]))
    assert ok.status_code == 200
    out = call(world, "POST", "/sms/preview", audience(scope="COURSE", courseIds=[str(other["CORS_SN"])]))
    assert out.status_code == 422 and "courseIds" in out.json()["fields"]  # 다른 동 강좌는 고를 수 없다


# --- 미리보기 -----------------------------------------------------------------------------------


def test_미리보기는_회원_한_명을_한_번만_세고_제외_대상을_뺀다(world: World) -> None:
    c1, c2 = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    both = enroll(world, c1, name="홍길동")
    enroll(world, c2, "ES.WAIT", who=both)  # 같은 회원이 두 강좌
    enroll(world, c1, "ES.HOLD", name="박다라")
    enroll(world, c1, "ES.CANCEL", name="취소자")
    enroll(world, c1, name="무번호", phone=None)
    enroll(world, c1, name="탈퇴자", MBR_STTS_CD="MS.WITHDRAW", WHDWL_DT=START)
    sender(world)
    all_three = audience(statuses=["CONFIRMED", "WAITING", "PAYMENT_PENDING"])
    out = call(world, "POST", "/sms/preview", all_three).json()
    assert (out["recipientCount"], out["duplicateRemoved"], out["courseCount"]) == (2, 1, 2)
    assert out["byteLength"] == len("[조리읍] 수강 안내입니다.".encode("cp949")) and out["centerName"]
    assert sorted((r["name"], r["phone"]) for r in out["recipients"]) == [
        ("박*라", "010-****-5678"),
        ("홍*동", "010-****-5678"),
    ]
    assert "홍길동" not in str(out) and "01012345678" not in str(out)
    one = call(world, "POST", "/sms/preview", audience(statuses=["CONFIRMED"])).json()
    assert (one["recipientCount"], one["duplicateRemoved"], one["courseCount"]) == (1, 0, 1)
    picked = call(
        world,
        "POST",
        "/sms/preview",
        audience(scope="COURSE", courseIds=[str(c2["CORS_SN"])], statuses=["WAITING"]),
    ).json()
    assert (picked["recipientCount"], picked["courseCount"]) == (1, 1)
    empty = call(
        world,
        "POST",
        "/sms/preview",
        audience(statuses=["PAYMENT_PENDING"], scope="COURSE", courseIds=[str(c2["CORS_SN"])]),
    ).json()
    assert empty["recipientCount"] == 0 and empty["recipients"] == []
    assert rows(world, "SELECT COUNT(*) n FROM TB_SMS_DMND")[0]["n"] == 0  # 미리보기는 저장하지 않는다


def test_미리보기의_수신자_목록은_오십_명까지만_담는다(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    c = open_course(world)
    for _ in range(4):
        enroll(world, c)
    monkeypatch.setattr(sms_service, "PREVIEW_RECIPIENTS", 3)
    sender(world)
    out = call(world, "POST", "/sms/preview", audience()).json()
    assert (out["recipientCount"], len(out["recipients"])) == (4, 3)


# --- 발송 요청 ----------------------------------------------------------------------------------


def test_발송을_요청하면_요청·강좌·명단을_저장하고_워커가_보낸다(world: World) -> None:
    c1, c2 = open_course(world, CORS_NM="요가"), open_course(world, CORS_NM="서예")
    kim = enroll(world, c1, name="김회원", phone="01011112222")
    enroll(world, c2, name="박회원", phone="01033334444")
    enroll(world, open_course(world, CORS_NM="제외 강좌"), name="제외", phone="01055556666")
    me = sender(world)
    payload = send_body(2, scope="COURSE", courseIds=[str(c1["CORS_SN"]), str(c2["CORS_SN"])])
    res = post_send(world, payload)
    assert res.status_code == 201, res.text
    out = res.json()
    assert (
        out["kind"],
        out["scope"],
        out["targetCount"],
        out["sent"],
        out["failed"],
        out["unknown"],
        out["requestedBy"],
    ) == (
        "MANUAL",
        "COURSE",
        2,
        0,
        0,
        0,
        me.row["MNGR_NM"],
    )
    assert (out["content"], out["courseNames"], out["targetsTruncated"]) == (
        "[조리읍] 수강 안내입니다.",
        ["서예", "요가"],
        False,
    )
    assert sorted((t["name"], t["phone"], t["state"], t["attempts"]) for t in out["targets"]) == [
        ("김*원", "010-****-2222", "WAIT", 0),
        ("박*원", "010-****-4444", "WAIT", 0),
    ]
    [req] = rows(world, "SELECT * FROM TB_SMS_DMND")
    assert (
        req["DMND_TYPE_CD"].strip(),
        req["TRGT_TYPE_CD"].strip(),
        req["DMND_MNGR_SN"],
        req["DSPTCH_TELNO"],
        req["SRC_EVENT_ID"],
    ) == (
        "SM.MANUAL",
        "SG.COURSE",
        me.sn,
        world.settings.sms_sender_number,
        None,
    )
    assert req["DMND_HASH_VL"] and req["IDEM_KEY"].startswith(f"a{me.sn}-")
    assert sorted(r["CORS_SN"] for r in rows(world, "SELECT CORS_SN FROM TB_SMS_DMND_CORS")) == sorted(
        [c1["CORS_SN"], c2["CORS_SN"]]
    )
    stored = rows(world, "SELECT MBR_SN, RCPTN_TELNO_ENCPT_VL, TRGT_STTS_CD, RCRD_VER FROM TB_SMS_TRGT")
    assert {(r["TRGT_STTS_CD"].strip(), r["RCRD_VER"]) for r in stored} == {("SS.WAIT", 1)}
    phones = {int(r["MBR_SN"]): decrypt(world.settings.secret_key, r["RCPTN_TELNO_ENCPT_VL"]) for r in stored}
    assert phones[int(kim["MBR_SN"])] == "01011112222" and "01011112222" not in out["content"]
    [job] = rows(world, "SELECT MNGR_SN m, CHG_CN c FROM TB_JOB_HSTRY WHERE JOB_CD='SMS_SEND'")
    assert job["m"] == me.sn and "0101" not in job["c"] and "수강 안내" not in job["c"]
    # 커밋 뒤 워커가 보낸다
    world.db.commit()
    assert jobs.dispatch_sms(world.db, world.settings, world.sms, world.bundle, world.clock) == 2
    assert sorted(m.to for m in world.sms.outbox) == ["01011112222", "01033334444"]
    assert {m.text for m in world.sms.outbox} == {"[조리읍] 수강 안내입니다."}
    after = call(world, "GET", f"/sms/{out['smsId']}").json()
    assert (after["sent"] + after["unknown"], after["failed"]) == (2, 0) and {
        t["attempts"] for t in after["targets"]
    } == {1}


def test_센터_전체_발송은_강좌_연결을_만들지_않는다(world: World) -> None:
    enroll(world, open_course(world))
    sender(world)
    res = post_send(world, send_body(1))
    assert res.status_code == 201 and (res.json()["scope"], res.json()["courseNames"]) == ("CENTER", [])
    assert rows(world, "SELECT COUNT(*) n FROM TB_SMS_DMND_CORS")[0]["n"] == 0


def test_최종_확인이_없거나_대상이_없거나_수가_바뀌면_저장하지_않는다(world: World) -> None:
    c = open_course(world)
    enroll(world, c)
    enroll(world, c)
    sender(world)
    unchecked = post_send(world, {**send_body(2), "confirmed": False})
    assert unchecked.status_code == 422 and "confirmed" in unchecked.json()["fields"]
    changed = post_send(world, send_body(5))
    assert (
        changed.status_code == 409
        and changed.json()["code"] == "CONFLICT_STATE"
        and "2명" in changed.json()["message"]
    )
    none = post_send(world, send_body(0, statuses=["WAITING"]))
    assert none.status_code == 422
    assert (
        rows(world, "SELECT COUNT(*) n FROM TB_SMS_DMND")[0]["n"] == 0
        and rows(world, "SELECT COUNT(*) n FROM TB_SMS_TRGT")[0]["n"] == 0
    )
    assert post_send(world, send_body(2, content="가" * 46)).status_code == 422


def test_같은_키로_다시_보내면_같은_요청이고_내용이_다르면_409다(world: World) -> None:
    c = open_course(world)
    enroll(world, c)
    enroll(world, c)
    sender(world)
    first = post_send(world, send_body(2), "sms-key-same01").json()
    again = post_send(world, send_body(2), "sms-key-same01")
    assert again.status_code == 201 and again.json()["smsId"] == first["smsId"]
    # 대상이 바뀐 뒤에 다시 보내도 처음 요청을 돌려준다
    enroll(world, c)
    late = post_send(world, send_body(2), "sms-key-same01")
    assert late.status_code == 201 and late.json()["smsId"] == first["smsId"]
    assert (
        rows(world, "SELECT COUNT(*) n FROM TB_SMS_DMND")[0]["n"] == 1
        and rows(world, "SELECT COUNT(*) n FROM TB_SMS_TRGT")[0]["n"] == 2
    )
    other = post_send(world, send_body(3, content="다른 문안입니다."), "sms-key-same01")
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert call(world, "POST", "/sms", send_body(3)).status_code in (400, 422)  # 키 필수


def test_다른_담당자가_같은_키를_써도_따로_만든다(world: World) -> None:
    enroll(world, open_course(world))
    sender(world)
    one = post_send(world, send_body(1), "sms-key-shared").json()["smsId"]
    sender(world)
    two = post_send(world, send_body(1), "sms-key-shared").json()["smsId"]
    assert one != two


# --- 이력 ---------------------------------------------------------------------------------------


def request(
    w: World,
    kind: str = "SM.AUTO",
    scope: str = "SG.EVENT",
    by: int | None = None,
    body: str = "[조리읍] 알림입니다.",
    event: str | None = "EV:1",
    **values: Any,
) -> dict[str, Any]:
    n = next(_n)
    return w.factory.make(
        "TB_SMS_DMND",
        DMND_TYPE_CD=kind,
        TRGT_TYPE_CD=scope,
        DMND_MNGR_SN=by,
        DSPTCH_TELNO="0319400000",
        SMS_CN=body,
        IDEM_KEY=f"seed-{n}",
        DMND_HASH_VL=hashlib.sha256(f"{n}".encode()).hexdigest(),
        SRC_EVENT_ID=event,
        **values,
    )


def target(
    w: World, req: dict[str, Any], state: str = "SS.WAIT", phone: str = "01012345678", name: str = "홍길동"
) -> dict[str, Any]:
    return w.factory.make(
        "TB_SMS_TRGT",
        SMS_DMND_SN=req["SMS_DMND_SN"],
        MBR_SN=person(w, name)["MBR_SN"],
        RCPTN_TELNO_ENCPT_VL=encrypt(w.settings.secret_key, phone),
        TRGT_STTS_CD=state,
    )


def test_이력은_종류로_나누고_결과_수를_세며_인증번호_문자는_뺀다(world: World) -> None:
    auto = request(
        world, body="[조리읍] 자리가 났습니다. 결제해 주세요. 마감은 10분 뒤입니다.", event="PROMO:1"
    )
    for state in ("SS.SENT", "SS.SENT", "SS.FAIL", "SS.UNKNOWN", "SS.SENDING", "SS.WAIT"):
        target(world, auto, state)
    otp = request(world, body="[조리읍] 인증번호는 {code}입니다.", event="CERT:77")
    target(world, otp, "SS.SENT")
    manual = request(world, "SM.MANUAL", "SG.CENTER", by=sender(world).sn, event=None)
    target(world, manual, "SS.SENT")
    world.db.commit()
    autos = call(world, "GET", "/sms").json()
    assert autos["total"] == 1 and [i["smsId"] for i in autos["items"]] == [str(auto["SMS_DMND_SN"])]
    item = autos["items"][0]
    assert (
        item["kind"],
        item["scope"],
        item["targetCount"],
        item["sent"],
        item["failed"],
        item["unknown"],
        item["requestedBy"],
    ) == (
        "AUTO",
        "EVENT",
        6,
        2,
        1,
        2,
        "SYSTEM",
    )
    assert item["summary"] == "[조리읍] 자리가 났습니다. 결제해 주세요. 마감은 10분 뒤입니다."[:30]
    manuals = call(world, "GET", "/sms?kind=MANUAL").json()
    assert [i["smsId"] for i in manuals["items"]] == [str(manual["SMS_DMND_SN"])] and manuals["items"][0][
        "scope"
    ] == "CENTER"
    assert (
        call(world, "GET", f"/sms/{otp['SMS_DMND_SN']}").status_code == 404
    )  # 인증번호 문자는 보이지 않는다
    assert call(world, "GET", "/sms?kind=NOPE").status_code in (400, 422)


def test_이력은_최근_순이고_쪽을_나눈다(world: World) -> None:
    sender(world)
    made = [request(world, event=f"EV:{n}", REG_DT=START.replace(hour=h)) for n, h in enumerate((1, 3, 2))]
    world.db.commit()
    ids = [i["smsId"] for i in call(world, "GET", "/sms").json()["items"]]
    assert ids == [str(made[1]["SMS_DMND_SN"]), str(made[2]["SMS_DMND_SN"]), str(made[0]["SMS_DMND_SN"])]
    assert [len(call(world, "GET", f"/sms?size=2&page={p}").json()["items"]) for p in (1, 2, 3)] == [2, 1, 0]


def test_상세는_건별_결과와_실패_사유를_가려서_준다(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    req = request(world, "SM.MANUAL", "SG.CENTER", by=sender(world).sn, event=None)
    failed = target(world, req, "SS.FAIL", "01099998888", "김실패")
    done = target(world, req, "SS.SENT", name="박성공")
    broken = target(world, req, "SS.WAIT", name="깨짐")
    world.db.execute(
        text("UPDATE TB_SMS_TRGT SET RCPTN_TELNO_ENCPT_VL='not-encrypted' WHERE SMS_TRGT_SN=:t"),
        {"t": broken["SMS_TRGT_SN"]},
    )
    for seq, status, code, reason in (
        (1, "SS.UNKNOWN", None, None),
        (2, "SS.FAIL", "MOCK_REJECTED", "수신 거부"),
    ):
        world.factory.make(
            "TB_SMS_SNDNG_HSTRY",
            SMS_TRGT_SN=failed["SMS_TRGT_SN"],
            SNDNG_SEQ=seq,
            PRCS_STTS_CD=status,
            FAIL_CD=code,
            FAIL_RSN=reason,
            SNDNG_DMND_DT=START,
            IDEM_KEY=f"h-{next(_n)}",
            SPLR_NM="mock",
            SPLR_ACNT_ID="mock",
        )
    world.db.commit()
    out = call(world, "GET", f"/sms/{req['SMS_DMND_SN']}").json()
    by = {t["targetId"]: t for t in out["targets"]}
    f = by[str(failed["SMS_TRGT_SN"])]
    assert (f["name"], f["phone"], f["state"], f["attempts"], f["failCode"], f["failReason"]) == (
        "김*패",
        "010-****-8888",
        "FAIL",
        2,
        "MOCK_REJECTED",
        "수신 거부",
    )
    ok = by[str(done["SMS_TRGT_SN"])]
    assert (ok["state"], ok["attempts"], ok["failCode"], ok["failReason"]) == ("SENT", 0, None, None)
    assert by[str(broken["SMS_TRGT_SN"])]["phone"] == "****"  # 복호화할 수 없어도 응답은 나온다
    assert "01099998888" not in str(out)
    monkeypatch.setattr(sms_service, "DETAIL_TARGETS", 2)
    cut = call(world, "GET", f"/sms/{req['SMS_DMND_SN']}").json()
    assert (len(cut["targets"]), cut["targetsTruncated"], cut["targetCount"]) == (2, True, 3)


def test_동_담당자는_자기가_보낸_관리자_문자만_본다(world: World) -> None:
    a = dong(world, "가동")
    me = sender(world, kind="SK.DONG", dong_sn=a["DONG_SN"])
    mine = request(world, "SM.MANUAL", "SG.COURSE", by=me.sn, event=None)
    theirs = request(world, "SM.MANUAL", "SG.COURSE", by=sender(world).sn, event=None)
    auto = request(world, event="EV:9")
    use(world, me)
    assert [i["smsId"] for i in call(world, "GET", "/sms?kind=MANUAL").json()["items"]] == [
        str(mine["SMS_DMND_SN"])
    ]
    assert call(world, "GET", "/sms?kind=AUTO").json()["total"] == 0
    assert call(world, "GET", f"/sms/{mine['SMS_DMND_SN']}").status_code == 200
    for hidden in (theirs, auto):
        assert call(world, "GET", f"/sms/{hidden['SMS_DMND_SN']}").status_code == 404
    assert call(world, "GET", "/sms/999999999").status_code == 404 and call(
        world, "GET", "/sms/abc"
    ).status_code in (400, 422)


def test_발송이_거절되면_이력에_실패로_남고_다시_보내지_않는다(world: World) -> None:
    enroll(world, open_course(world))
    sender(world)
    sms_id = post_send(world, send_body(1)).json()["smsId"]
    world.sms.next_outcome = SendOutcome.REJECTED
    world.db.commit()
    jobs.dispatch_sms(world.db, world.settings, world.sms, world.bundle, world.clock)
    jobs.dispatch_sms(
        world.db, world.settings, world.sms, world.bundle, world.clock
    )  # 확인된 실패는 다시 보내지 않는다
    out = call(world, "GET", f"/sms/{sms_id}").json()
    assert (out["failed"], out["sent"], out["targets"][0]["state"], out["targets"][0]["attempts"]) == (
        1,
        0,
        "FAIL",
        1,
    )
