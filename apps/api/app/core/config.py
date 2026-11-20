# 배포마다 다른 설정(접속 정보, 사이트 식별자, 비밀키)을 환경변수에서 읽는다. 비밀값은 저장소에 두지 않는다
import os
from dataclasses import dataclass
from functools import lru_cache

MIN_SECRET_LENGTH = 32
ADMIN_LOCK_FAILURES = 5  # 기관 확정값(Q28): 연속 실패 허용 횟수
ADMIN_LOCK_MINUTES = 5  # 기관 확정값(Q28): 잠금 시간(분). 실패를 세는 구간도 같다


class ConfigError(RuntimeError):
    """필수 설정이 없거나 잘못됐을 때 서버를 시작하지 못하게 하는 오류. 메시지에 값은 담지 않는다."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    site_id: str  # 이 배포가 맡는 운영묶음의 TB_OPER_BNDL.SITE_ID. 요청이 아니라 배포 설정이 정한다(R26)
    environment: str = "development"  # 운영 배포는 JORI_ENVIRONMENT=production을 명시한다
    secret_key: str = "x" * MIN_SECRET_LENGTH  # CSRF·OTP 검증값용 비밀키(용도별로 파생)
    pbkdf2_iterations: int = 600_000  # 비밀번호 해시 반복 횟수. 해시마다 값이 같이 저장돼 나중에 올려도 된다
    cookie_secure: bool = True  # 로컬 http 개발에서만 끈다
    # 관리자 로그인 실패 제한. 기관이 5회·5분으로 정했고(Q28, 2026-11-17)
    # 배포 설정(load_settings)이 그 값을 기본으로 쓴다.
    # 시험이나 코드에서 Settings를 직접 만들 때 값을 주지 않으면 잠그지 않는다.
    admin_lock_failures: int | None = None
    admin_lock_minutes: int | None = None
    sms_provider: str = "mock"  # 공급자는 계약 후 정해진다(Q2~Q4). 그 전에는 모의 어댑터만 있다
    sms_sender_number: str = "TBD"  # 발신번호도 미정이라 값을 지어내지 않고 TBD로 표시한다
    file_root: str = "/data/files"  # 첨부파일 저장 위치. 웹 루트 밖이어야 한다(TRD 4.5)
    file_scanner: str = "mock"  # 파일 검사기. "mock" 또는 "clamd"(주소는 아래 두 값, 배포 환경이 정한다)
    clamd_host: str = "127.0.0.1"  # clamd의 기본 접속 주소(TCP)
    clamd_port: int = 3310  # clamd의 기본 TCP 포트
    pg_provider: str = "mock"  # 결제대행사는 계약 후 정해진다(PRD Q1). 그 전에는 모의 어댑터만 있다
    pg_merchant_id: str = "TBD"  # 가맹점 아이디도 미정이라 값을 지어내지 않는다
    worker_status_file: str = (
        "/var/run/jori/worker-status.json"  # 워커가 작업별 마지막 실행을 쓰고 /api/health가 읽는다
    )
    build_commit: str = "unknown"  # 배포한 빌드의 커밋 해시. 배포 절차가 넣고 /api/health/version이 보인다
    # DB 커넥션 풀. 프로세스마다 따로 갖는다. 실제 동시 처리 상한은 요청 스레드 수가 아니라
    # (풀 + 초과) x (API 프로세스 수 + 워커 1)이므로 MariaDB max_connections와 함께 정한다.
    # 부하 시험 전의 가정값이며 시험 결과로 조정한다. 풀 대기 시간(초)은 길게 막히지 않게 짧게 둔다.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 10
    # 같은 휴대전화번호로 하루(24시간)에 받을 수 있는 인증번호 수. 문자 비용 남용과 괴롭힘을 막는다.
    # 번호 단위 한도이고 IP 단위 한도는 Nginx가 맡는다(코드 리뷰 보안 중-2, 값은 사용자 확정 2026-11-20)
    otp_daily_limit: int = 10

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ConfigError("JORI_ENVIRONMENT는 development, test, production 중 하나여야 합니다.")
        if self.db_pool_size < 1 or self.db_pool_timeout < 1 or self.db_max_overflow < 0:
            raise ConfigError("DB 풀 크기와 대기 시간은 1 이상, 초과 허용은 0 이상이어야 합니다.")
        if self.otp_daily_limit < 1:
            raise ConfigError("인증번호 하루 상한은 1 이상이어야 합니다.")
        if self.environment == "production":
            if "mock" in (self.pg_provider, self.sms_provider, self.file_scanner):
                raise ConfigError("운영 환경에서는 PG·SMS·파일 검사에 mock을 사용할 수 없습니다.")
            if not self.cookie_secure:
                raise ConfigError("운영 환경에서는 보안 쿠키를 사용해야 합니다.")


def _int(env: dict[str, str], name: str) -> int | None:
    raw = env.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}은 정수여야 합니다.") from None


def _int_or(env: dict[str, str], name: str, default: int) -> int:
    """값이 없을 때만 기본값을 쓴다. 0도 사용자가 준 값이라 검사에서 걸러야 한다."""
    value = _int(env, name)
    return default if value is None else value


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
        environment=env.get("JORI_ENVIRONMENT", "development"),
        secret_key=env["JORI_SECRET_KEY"],
        pbkdf2_iterations=_int(env, "JORI_PBKDF2_ITERATIONS") or 600_000,
        cookie_secure=env.get("JORI_COOKIE_SECURE", "1") != "0",
        admin_lock_failures=ADMIN_LOCK_FAILURES if lock_failures is None else lock_failures,
        admin_lock_minutes=ADMIN_LOCK_MINUTES if lock_minutes is None else lock_minutes,
        sms_provider=env.get("JORI_SMS_PROVIDER", "mock"),
        sms_sender_number=env.get("JORI_SMS_SENDER_NUMBER", "TBD"),
        file_root=env.get("JORI_FILE_ROOT") or "/data/files",
        file_scanner=env.get("JORI_FILE_SCANNER", "mock"),
        clamd_host=env.get("JORI_CLAMD_HOST") or "127.0.0.1",
        clamd_port=_int(env, "JORI_CLAMD_PORT") or 3310,
        pg_provider=env.get("JORI_PG_PROVIDER", "mock"),
        pg_merchant_id=env.get("JORI_PG_MERCHANT_ID", "TBD"),
        worker_status_file=env.get("JORI_WORKER_STATUS_FILE") or "/var/run/jori/worker-status.json",
        build_commit=env.get("JORI_BUILD_COMMIT") or "unknown",
        db_pool_size=_int_or(env, "JORI_DB_POOL_SIZE", 10),
        db_max_overflow=_int_or(env, "JORI_DB_MAX_OVERFLOW", 10),
        db_pool_timeout=_int_or(env, "JORI_DB_POOL_TIMEOUT", 10),
        otp_daily_limit=_int_or(env, "JORI_OTP_DAILY_LIMIT", 10),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스가 쓰는 설정의 유일한 읽기 경로. 의존성과 DB 엔진이 같은 값을 보게 한다."""
    return load_settings()
