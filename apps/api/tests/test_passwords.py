# 비밀번호 해시 검증이 깨진 저장값에 예외나 과도한 계산 없이 거절하는지 확인하는 시험
import base64
import hashlib
from typing import Any

import pytest

from app.auth.passwords import hash_password, verify_password
from app.core.config import PBKDF2_MAX_ITERATIONS, ConfigError, Settings

SALT = base64.b64encode(b"s" * 16).decode()


def digest(length: int) -> str:
    return base64.b64encode(b"d" * length).decode()


def test_저장한_비밀번호는_맞고_다른_비밀번호는_틀리다() -> None:
    encoded = hash_password("Right-pass-2026", 1000)
    assert verify_password("Right-pass-2026", encoded)
    assert not verify_password("Wrong-pass-2026", encoded)


@pytest.mark.parametrize(
    "encoded",
    [
        f"pbkdf2_sha256$1000${SALT}$",  # 다이제스트가 비었다
        f"pbkdf2_sha256$1000${SALT}${digest(31)}",
        f"pbkdf2_sha256$1000${SALT}${digest(64)}",
        f"pbkdf2_sha256${10**20}${SALT}${digest(32)}",  # C 정수 범위를 넘는 반복 횟수
        f"pbkdf2_sha256$0${SALT}${digest(32)}",
        f"pbkdf2_sha256$-1${SALT}${digest(32)}",
        f"pbkdf2_sha256$1000$한글${digest(32)}",
        "pbkdf2_sha256$1000$only-three",
        "",
    ],
)
def test_깨진_저장값은_예외_없이_거짓이다(encoded: str) -> None:
    assert verify_password("Right-pass-2026", encoded) is False


def test_상한을_넘는_반복_횟수는_계산하지_않고_거짓이다(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> bytes:
        pytest.fail("상한을 넘으면 해시를 계산하지 않아야 한다")

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", forbidden)
    encoded = f"pbkdf2_sha256${PBKDF2_MAX_ITERATIONS + 1}${SALT}${digest(32)}"
    assert verify_password("Right-pass-2026", encoded) is False


@pytest.mark.parametrize("iterations", [0, -1, PBKDF2_MAX_ITERATIONS + 1])
def test_검증할_수_없는_반복_횟수_설정은_기동을_거절한다(iterations: int) -> None:
    with pytest.raises(ConfigError):
        Settings(database_url="unused", site_id="s", pbkdf2_iterations=iterations)
