# 회원·관리자 휴대전화번호를 암호문과 검색해시로 바꾸고 되돌리는 공용 모듈(스키마 v0.8, ADR-110)
import hashlib
import hmac
from typing import Any

from app.auth.crypto import decrypt, encrypt
from app.auth.tokens import derived_key

ENCRYPTED = "MBL_TELNO_ENCPT_VL"
SEARCH_HASH = "MBL_TELNO_SRCH_HASH_VL"
# OTP 검색키(otp-phone-search)와 다른 용도 키라 서로의 값을 대조할 수 없다
SEARCH_PURPOSE = "member-phone-search"


def search_hash(secret: str, phone: str) -> str:
    """같은 번호는 늘 같은 값이어야 번호로 찾을 수 있다. 원문이나 단순 해시가 아니라 용도별 키의 HMAC이다."""
    return hmac.new(derived_key(secret, SEARCH_PURPOSE), phone.encode("utf-8"), hashlib.sha256).hexdigest()


def sealed_columns(secret: str, phone: str | None) -> dict[str, Any]:
    """TB_MBR에 넣거나 고칠 (암호문, 검색해시) 컬럼 값. 번호가 없으면 둘 다 NULL이다."""
    if not phone:
        return {ENCRYPTED: None, SEARCH_HASH: None}
    return {ENCRYPTED: encrypt(secret, phone), SEARCH_HASH: search_hash(secret, phone)}


def reveal(secret: str, token: str | None) -> str | None:
    """저장된 암호문을 번호로 되돌린다. 값이 없으면 None이다. 변조된 값은 DecryptError다."""
    return None if not token else decrypt(secret, token)
