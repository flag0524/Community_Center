# 비밀번호 해시(PBKDF2-HMAC-SHA-256). 계정별 salt·반복 횟수를 정하고 인코딩 결과만 저장한다(스키마 1.3)
import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

ALGORITHM = "pbkdf2_sha256"
SALT_BYTES = 16


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str, iterations: int) -> str:
    """'pbkdf2_sha256$반복$salt$해시'. 반복 횟수를 함께 저장해 설정을 올려도 옛 해시를 검증할 수 있다."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """형식이 맞지 않는 저장값은 예외 없이 false다(깨진 행이 로그인을 막거나 서버를 멈추지 않게)."""
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$")
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_text)
        expected = base64.b64decode(digest_text, validate=True)
        salt = base64.b64decode(salt_text, validate=True)
    except ValueError:
        return False
    if iterations < 1:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(actual, expected)


@lru_cache(maxsize=4)
def dummy_hash(iterations: int) -> str:
    """없는 아이디에도 같은 계산을 해서 응답 시간으로 계정 존재를 알 수 없게 한다(TDD 8.1)."""
    return hash_password("dummy-password-for-timing", iterations)
