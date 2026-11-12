# 배포마다 다른 설정(접속 정보, 사이트 식별자, 비밀키)을 환경변수에서 읽는다. 비밀값은 저장소에 두지 않는다
import os
from dataclasses import dataclass
from functools import lru_cache

MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """필수 설정이 없거나 잘못됐을 때 서버를 시작하지 못하게 하는 오류. 메시지에 값은 담지 않는다."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    site_id: str  # 이 배포가 맡는 운영묶음의 TB_OPER_BNDL.SITE_ID. 요청이 아니라 배포 설정이 정한다(R26)
    secret_key: str = "x" * MIN_SECRET_LENGTH  # CSRF·OTP 검증값용 비밀키(용도별로 파생)
    pbkdf2_iterations: int = 600_000  # 비밀번호 해시 반복 횟수. 해시마다 값이 같이 저장돼 나중에 올려도 된다
    cookie_secure: bool = True  # 로컬 http 개발에서만 끈다
    # 관리자 로그인 실패 제한은 기관 정책(Q28) 전까지 값을 지어내지 않는다. 설정이 없으면 잠그지 않는다.
    admin_lock_failures: int | None = None
    admin_lock_minutes: int | None = None
    sms_provider: str = "mock"  # 공급자는 계약 후 정해진다(Q2~Q4). 그 전에는 모의 어댑터만 있다
    sms_sender_number: str = "TBD"  # 발신번호도 미정이라 값을 지어내지 않고 TBD로 표시한다
    file_root: str = "/data/files"  # 첨부파일 저장 위치. 웹 루트 밖이어야 한다(TRD 4.5)
    pg_provider: str = "mock"  # 결제대행사는 계약 후 정해진다(PRD Q1). 그 전에는 모의 어댑터만 있다
    pg_merchant_id: str = "TBD"  # 가맹점 아이디도 미정이라 값을 지어내지 않는다
    worker_status_file: str = (
        "/var/run/jori/worker-status.json"  # 워커가 작업별 마지막 실행을 쓰고 /api/health가 읽는다
    )


def _int(env: dict[str, str], name: str) -> int | None:
    raw = env.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}은 정수여야 합니다.") from None


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if environ is None else environ)
    missing = [name for name in ("JORI_DATABASE_URL", "JORI_SITE_ID", "JORI_SECRET_KEY") if not env.get(name)]
    if missing:
        raise ConfigError(f"필수 환경변수가 없습니다: {', '.join(missing)}")
    if len(env["JORI_SECRET_KEY"]) < MIN_SECRET_LENGTH:
        raise ConfigError(f"JORI_SECRET_KEY는 {MIN_SECRET_LENGTH}자 이상이어야 합니다.")
    lock_failures = _int(env, "JORI_ADMIN_LOCK_FAILURES")
    lock_minutes = _int(env, "JORI_ADMIN_LOCK_MINUTES")
    if (lock_failures is None) != (lock_minutes is None):
        raise ConfigError("JORI_ADMIN_LOCK_FAILURES와 JORI_ADMIN_LOCK_MINUTES는 함께 설정해야 합니다.")
    return Settings(
        database_url=env["JORI_DATABASE_URL"],
        site_id=env["JORI_SITE_ID"],
        secret_key=env["JORI_SECRET_KEY"],
        pbkdf2_iterations=_int(env, "JORI_PBKDF2_ITERATIONS") or 600_000,
        cookie_secure=env.get("JORI_COOKIE_SECURE", "1") != "0",
        admin_lock_failures=lock_failures,
        admin_lock_minutes=lock_minutes,
        sms_provider=env.get("JORI_SMS_PROVIDER", "mock"),
        sms_sender_number=env.get("JORI_SMS_SENDER_NUMBER", "TBD"),
        file_root=env.get("JORI_FILE_ROOT") or "/data/files",
        pg_provider=env.get("JORI_PG_PROVIDER", "mock"),
        pg_merchant_id=env.get("JORI_PG_MERCHANT_ID", "TBD"),
        worker_status_file=env.get("JORI_WORKER_STATUS_FILE") or "/var/run/jori/worker-status.json",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스가 쓰는 설정의 유일한 읽기 경로. 의존성과 DB 엔진이 같은 값을 보게 한다."""
    return load_settings()
