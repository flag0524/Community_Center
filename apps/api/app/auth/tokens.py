# 세션 토큰 발급·해시와 CSRF 토큰 파생. 원문은 DB·로그에 남기지 않고 해시만 저장한다(AUTH-03, ADR-008)
import hashlib
import hmac
import secrets


def new_token() -> str:
    """256비트 무작위 토큰. 쿠키로만 나가고 서버에는 해시만 남는다."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", errors="replace")).hexdigest()  # CHAR(64)


def _derived_key(secret: str, purpose: str) -> bytes:
    """한 비밀키에서 용도별 키를 갈라 쓴다. 한 용도의 값이 다른 용도에 통하지 않는다."""
    return hmac.new(secret.encode("utf-8"), f"jori:{purpose}".encode(), hashlib.sha256).digest()


def csrf_for(secret: str, scope: str, value: str) -> str:
    """scope는 로그인 뒤 'session'(값=세션 토큰 해시), 로그인 전 'anon'(값=무작위 시드)이다(DV17)."""
    return hmac.new(_derived_key(secret, "csrf"), f"{scope}:{value}".encode(), hashlib.sha256).hexdigest()


def same(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and hmac.compare_digest(left.encode(), right.encode())
