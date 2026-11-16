# 같은 회원의 같은 강좌 후기가 동시에 들어와도 한 건만 만들어지는지 서로 다른 DB 연결로 확인하는 시험
import time
from typing import Any

import pytest

from app.domain.board import review
from tests.arena import Applicant, Arena, make_application, make_course, make_cycle, make_member, parallel
from tests.factory import RowFactory

pytestmark = pytest.mark.db

API = "/api/v1"


def build(f: RowFactory) -> tuple[int, int, int]:
    bundle = f.bundle()
    member = make_member(f, bundle, "writer")
    course = make_course(f, bundle, make_cycle(f, bundle), "요가")
    make_application(f, bundle, member, course, "ES.CONFIRM")
    f.make(
        "TB_BBS",
        OPER_BNDL_SN=bundle,
        BBS_ID="review",
        BBS_NM="수강후기",
        BBS_TYPE_CD="BT.REVIEW",
        MBR_WRT_YN="Y",
        USE_YN="Y",
    )
    return bundle, member, int(course["CORS_SN"])


def send(who: Applicant, course: int, key: str) -> Any:
    return who.client.post(
        f"{API}/me/reviews",
        json={"courseId": str(course), "title": "좋았어요", "body": "재미있었습니다"},
        headers={"X-CSRF-Token": who.csrf, "Idempotency-Key": key},
    )


def test_같은_강좌의_후기를_다른_키로_동시에_써도_한_건만_만든다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, course = arena.build(build)
    arena.serve(bundle)
    real = review._eligible

    def slow(*args: Any) -> Any:
        time.sleep(0.5)  # 자격을 확인하고 저장하기 전의 틈을 넓힌다. 회원 행 잠금이 없으면 둘 다 쓴다
        return real(*args)

    monkeypatch.setattr(review, "_eligible", slow)
    one, two = (arena.applicant(member, bundle) for _ in range(2))  # 세션이 같으면 이미 한 줄로 선다
    responses = parallel(
        [lambda: send(one, course, "rvw-conc-0001"), lambda: send(two, course, "rvw-conc-0002")]
    )
    assert sorted(r.status_code for r in responses) == [201, 422], [r.text for r in responses]
    assert len(arena.query("SELECT 1 FROM TB_PST WHERE WRT_MBR_SN=:m AND DEL_YN='N'", m=member)) == 1
