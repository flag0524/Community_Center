# 전화번호처럼 되돌려 읽는 값의 AES-256-GCM 암호화. 키는 비밀키에서 용도별로 파생한다(스키마 1.3)
import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.tokens import derived_key

VERSION = "v1"
NONCE_BYTES = 12
ASSOCIATED_DATA = b"jori:pii:v1"  # 다른 용도의 암호문을 이 자리에 옮겨 붙여도 복호화되지 않게 묶는다


class DecryptError(ValueError):
    """형식이 틀리거나 변조된 암호문. 평문은 메시지에 담지 않는다."""


def encrypt(secret: str, plaintext: str) -> str:
    """'v1:' + base64(nonce + 암호문 + 태그). 같은 값도 매번 다른 암호문이 나온다."""
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(derived_key(secret, "pii-aes256")).encrypt(
        nonce, plaintext.encode("utf-8"), ASSOCIATED_DATA
    )
    return f"{VERSION}:{base64.b64encode(nonce + sealed).decode('ascii')}"


def decrypt(secret: str, token: str) -> str:
    try:
        version, payload = token.split(":", 1)
        if version != VERSION:
            raise DecryptError("지원하지 않는 암호문 버전")
        raw = base64.b64decode(payload, validate=True)
        return (
            AESGCM(derived_key(secret, "pii-aes256"))
            .decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], ASSOCIATED_DATA)
            .decode("utf-8")
        )
    except (ValueError, InvalidTag) as error:
        raise DecryptError("복호화할 수 없는 값") from error
