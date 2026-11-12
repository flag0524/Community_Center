# 문의 올리기·삭제가 겹치고 답변이 수정 직전에 달려도 한 번만 반영되는지 서로 다른 DB 연결로 확인하는 시험
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.board import inquiry
from tests.arena import Applicant, Arena, make_member, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

API = "/api/v1"
CODE = "IQ.CONC"


@pytest.fixture
def code(arena: Arena) -> Iterator[None]:
    """분류 코드는 묶음에 속하지 않아 아레나가 치워 주지 않는다. 만들고 끝나면 지운다."""
    with arena.migrated.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO TB_COM_CD (COM_CD, CD_GROUP_ID, CD_NM, SORT_SEQ, USE_YN, REG_DT) "
                "VALUES (:c, 'IQ', '동시성', 1, 'Y', NOW())"
            ),
            {"c": CODE},
        )
    yield
    with arena.migrated.begin() as connection:
        for condition in ("UP_PST_SN IS NOT NULL", "UP_PST_SN IS NULL"):  # 답변을 먼저 지운다
            connection.execute(
                text(f"DELETE FROM TB_PST WHERE INQRY_CLSF_CD = :c AND {condition}"), {"c": CODE}
            )
        connection.execute(text("DELETE FROM TB_COM_CD WHERE COM_CD = :c"), {"c": CODE})


def build(f: RowFactory) -> tuple[int, int]:
    bundle = f.bundle()
    f.make("TB_BBS", OPER_BNDL_SN=bundle, BBS_ID="qna", BBS_NM="문의", BBS_TYPE_CD="BT.QNA", MBR_WRT_YN="Y")
    return bundle, make_member(f, bundle, "asker")


def sessions(arena: Arena, bundle: int, member: int, count: int) -> list[Applicant]:
    """같은 회원의 세션을 여러 개 만든다. 세션이 같으면 세션 갱신 때문에 요청이 이미 한 줄로 선다."""
    return [arena.applicant(member, bundle) for _ in range(count)]


def sender(who: Applicant, method: str, path: str, **kwargs: Any) -> Callable[[], Any]:
    headers = {"X-CSRF-Token": who.csrf, **kwargs.pop("headers", {})}
    return lambda: who.client.request(method, f"{API}{path}", headers=headers, **kwargs)


def form() -> dict[str, Any]:
    return {"categoryId": CODE, "title": "문의", "body": "내용", "isPrivate": False}


def test_같은_키의_동시_작성은_한_문의만_만든다(
    arena: Arena, code: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    real = inquiry._category

    def slow(*args: Any) -> None:
        real(*args)
        time.sleep(0.3)  # 멱등 확인을 마치고 저장하기 전의 틈을 넓혀 잠금이 없으면 겹치게 한다

    monkeypatch.setattr(inquiry, "_category", slow)
    calls = [
        sender(s, "POST", "/me/inquiries", json=form(), headers={"Idempotency-Key": "conc-key-0001"})
        for s in sessions(arena, bundle, member, 4)
    ]
    responses = parallel(calls)
    assert [r.status_code for r in responses] == [201] * 4, [r.text for r in responses]
    assert len({r.json()["postId"] for r in responses}) == 1
    assert len(arena.query("SELECT 1 FROM TB_PST WHERE WRT_MBR_SN=:m", m=member)) == 1


def test_같은_문의를_동시에_지워도_한_번만_지운다(
    arena: Arena, code: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    [first, *rest] = sessions(arena, bundle, member, 4)
    made = sender(first, "POST", "/me/inquiries", json=form(), headers={"Idempotency-Key": "conc-key-0001"})()
    sn = made.json()["postId"]
    real = inquiry._lock

    def slow(*args: Any) -> Any:
        found = real(*args)
        time.sleep(0.3)  # 지움 여부를 읽은 뒤 갱신하기 전의 틈을 넓힌다. 잠금이 없으면 모두 이 틈에 들어온다
        return found

    monkeypatch.setattr(inquiry, "_lock", slow)
    codes = sorted(
        r.status_code for r in parallel([sender(s, "DELETE", f"/me/inquiries/{sn}") for s in [first, *rest]])
    )
    assert codes == [204, 404, 404, 404], codes
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD='INQ_DELETE'")) == 1


def test_수정_직전에_답변이_달리면_수정을_거절한다(
    arena: Arena, code: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member = arena.build(build)
    arena.serve(bundle)
    admin = arena.staff(bundle, "answerer", "AU.POST_W")
    [who] = sessions(arena, bundle, member, 1)
    made = sender(who, "POST", "/me/inquiries", json=form(), headers={"Idempotency-Key": "conc-key-0001"})()
    sn = int(made.json()["postId"])
    real = inquiry._lock

    def answer_arrives_first(db: Any, post_sn: int) -> Any:
        """읽은 뒤 잠그기 전에 다른 담당자의 답변이 확정된 상황을 만든다."""
        with arena.migrated.begin() as connection:
            row = connection.execute(text("SELECT BBS_SN FROM TB_PST WHERE PST_SN=:s"), {"s": post_sn}).one()
            connection.execute(
                text(
                    "INSERT INTO TB_PST (OPER_BNDL_SN, BBS_SN, UP_PST_SN, PST_TYPE_CD, PST_TTL, PST_CN, "
                    "WRT_MNGR_SN, PRVT_YN, NTC_YN, DEL_YN, INQRY_CLSF_CD, REG_DT, RCRD_VER) "
                    "VALUES (:b, :bbs, :up, 'PT.REPLY', '답변', '답변', :m, 'N', 'N', 'N', :c, NOW(), 1)"
                ),
                {"b": bundle, "bbs": row.BBS_SN, "up": post_sn, "m": admin.admin_sn, "c": CODE},
            )
        return real(db, post_sn)

    monkeypatch.setattr(inquiry, "_lock", answer_arrives_first)
    r = sender(who, "PUT", f"/me/inquiries/{sn}", json={**form(), "title": "고침"})()
    assert r.status_code == 422 and "답변" in r.json()["message"], r.text
    assert arena.query("SELECT PST_TTL t FROM TB_PST WHERE PST_SN=:s", s=sn)[0]["t"] == "문의"
