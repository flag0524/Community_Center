# 수강신청 생성의 강좌·회원 행 잠금 구간이 응답 조립 전에 끝나는지, 정원 집계가 한 번에 맞는지 실제 DB로 확인하는 시험
from typing import Any

import pytest
from sqlalchemy import text

from app.db.session import open_session
from app.domain.application import create
from app.domain.application.seats import count_by_status, seat_counts
from app.domain.application.service import SEAT_STATUSES, get_mine
from tests.arena import Arena, attempt, make_application, make_course, make_cycle, make_member
from tests.factory import RowFactory

pytestmark = pytest.mark.db


def _free(arena: Arena, table: str, key: str, value: int) -> bool:
    """다른 연결이 그 행을 바로(1초 안에) 잠글 수 있는가. 신청 요청이 아직 쥐고 있으면 False다."""
    with arena.migrated.connect() as connection:
        try:
            connection.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
            connection.execute(text(f"SELECT {key} FROM {table} WHERE {key} = :v FOR UPDATE"), {"v": value})
            return True
        except Exception:
            return False
        finally:
            connection.rollback()


def _spy(arena: Arena, monkeypatch: pytest.MonkeyPatch, course_sn: int, member_sn: int) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def spying(*args: Any, **kwargs: Any) -> Any:
        # 응답을 조립하는 이 시점에 신청 요청이 강좌·회원 행 잠금을 쥐고 있지 않아야 한다
        seen["course_free"] = _free(arena, "TB_CORS", "CORS_SN", course_sn)
        seen["member_free"] = _free(arena, "TB_MBR", "MBR_SN", member_sn)
        return get_mine(*args, **kwargs)

    monkeypatch.setattr(create, "get_mine", spying)
    return seen


def _setup(arena: Arena) -> tuple[int, int, int]:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        course = make_course(f, bundle, make_cycle(f, bundle), "강좌")
        return bundle, make_member(f, bundle, "lock-window"), int(course["CORS_SN"])

    bundle, member, course_sn = arena.build(make)
    arena.serve(bundle)
    return bundle, member, course_sn


def test_새_신청은_응답을_조립하기_전에_강좌와_회원_행_잠금을_푼다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, course_sn = _setup(arena)
    seen = _spy(arena, monkeypatch, course_sn, member)
    response = attempt(arena.applicant(member, bundle), course_sn, "lock-window-key-0001")()
    assert response.status_code == 201
    assert seen == {"course_free": True, "member_free": True}


def test_같은_키_재전송도_응답을_조립하기_전에_잠금을_푼다(
    arena: Arena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, member, course_sn = _setup(arena)
    who = arena.applicant(member, bundle)
    assert attempt(who, course_sn, "lock-window-key-0002")().status_code == 201
    seen = _spy(arena, monkeypatch, course_sn, member)
    again = attempt(who, course_sn, "lock-window-key-0002")()
    assert again.status_code == 201
    assert seen == {"course_free": True, "member_free": True}


def test_잠금을_일찍_풀어도_신청과_감사_기록은_함께_남는다(arena: Arena) -> None:
    bundle, member, course_sn = _setup(arena)
    response = attempt(arena.applicant(member, bundle), course_sn, "lock-window-key-0003")()
    assert response.status_code == 201
    assert len(arena.query("SELECT 1 FROM TB_ATNLC_APLY WHERE CORS_SN = :c", c=course_sn)) == 1
    assert len(arena.query("SELECT 1 FROM TB_JOB_HSTRY WHERE JOB_CD = 'APLY_CREATE'")) == 1


def test_감사_기록이_실패하면_신청도_남지_않는다(arena: Arena, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle, member, course_sn = _setup(arena)

    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("감사 기록 실패")

    monkeypatch.setattr(create, "record_job", broken)
    response = attempt(arena.applicant(member, bundle), course_sn, "lock-window-key-0005")()
    assert response.status_code == 500
    # 잠금을 일찍 풀더라도 신청 확정은 감사 기록까지 쓴 뒤여야 한다
    assert arena.query("SELECT 1 FROM TB_ATNLC_APLY WHERE CORS_SN = :c", c=course_sn) == []
    assert _free(arena, "TB_CORS", "CORS_SN", course_sn)


def test_거절된_신청은_잠금을_풀고_아무것도_남기지_않는다(arena: Arena) -> None:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        course = make_course(f, bundle, make_cycle(f, bundle), "작성중강좌", CORS_STTS_CD="CS.DRAFT")
        return bundle, make_member(f, bundle, "rejected"), int(course["CORS_SN"])

    bundle, member, course_sn = arena.build(make)
    arena.serve(bundle)
    response = attempt(arena.applicant(member, bundle), course_sn, "lock-window-key-0004")()
    assert response.status_code >= 400
    assert arena.query("SELECT 1 FROM TB_ATNLC_APLY WHERE CORS_SN = :c", c=course_sn) == []
    assert _free(arena, "TB_CORS", "CORS_SN", course_sn)


# --- 정원 집계 ----------------------------------------------------------------------------------


def test_정원_집계는_점유와_대기를_따로_한_번에_센다(arena: Arena) -> None:
    def make(f: RowFactory) -> tuple[int, int, int]:
        bundle = f.bundle()
        cycle = make_cycle(f, bundle)
        course = make_course(f, bundle, cycle, "집계", RCRT_NOPE=10, WTNG_NOPE=10)
        other = make_course(f, bundle, cycle, "다른강좌", RCRT_NOPE=10, WTNG_NOPE=10)
        states = ["ES.HOLD", "ES.CONFIRM", "ES.CONFIRM", "ES.WAIT", "ES.WAIT", "ES.CANCEL", "ES.EXPIRE"]
        for n, state in enumerate(states):
            make_application(
                f,
                bundle,
                make_member(f, bundle, f"c{n}"),
                course,
                state,
                seq=n if state == "ES.WAIT" else None,
            )
        make_application(f, bundle, make_member(f, bundle, "elsewhere"), other, "ES.CONFIRM")
        return bundle, int(course["CORS_SN"]), int(other["CORS_SN"])

    bundle, course_sn, other_sn = arena.build(make)
    with open_session(arena.engine) as db:
        assert seat_counts(db, bundle, course_sn) == (3, 2)  # 취소·만료·다른 강좌는 세지 않는다
        assert seat_counts(db, bundle, other_sn) == (1, 0)
        assert seat_counts(db, bundle, 0) == (0, 0)
        # 기존 단건 집계와 같은 값이다
        assert count_by_status(db, bundle, course_sn, SEAT_STATUSES) == 3
        assert count_by_status(db, bundle, course_sn, ("ES.WAIT",)) == 2
