# 일련번호가 JS Number 한계(2^53)를 넘어도 문자열로 손실 없이 오가는지 확인하는 시험
import json

import pytest
from pydantic import ValidationError

from app.domain.application.schemas import ApplicationCreate

BEYOND_JS_SAFE_INTEGER = "9007199254740993"  # 2^53 + 1
MAX_22_DIGITS = "9" * 22


def test_2의_53제곱을_넘는_값도_그대로_왕복한다() -> None:
    parsed = ApplicationCreate.model_validate_json(json.dumps({"courseId": BEYOND_JS_SAFE_INTEGER}))
    assert parsed.course_id == BEYOND_JS_SAFE_INTEGER
    dumped = parsed.model_dump_json(by_alias=True)
    assert json.loads(dumped)["courseId"] == BEYOND_JS_SAFE_INTEGER


def test_22자리까지_허용한다() -> None:
    assert ApplicationCreate(course_id=MAX_22_DIGITS).course_id == MAX_22_DIGITS


@pytest.mark.parametrize("value", ["", "abc", "12a", "-1", "1.5", " 1", "9" * 23])
def test_숫자_문자열이_아니거나_23자리_이상이면_거절한다(value: str) -> None:
    with pytest.raises(ValidationError):
        ApplicationCreate.model_validate({"courseId": value})


def test_숫자_타입으로_보내면_거절한다() -> None:
    with pytest.raises(ValidationError):
        ApplicationCreate.model_validate({"courseId": 123})
