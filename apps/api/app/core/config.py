# 배포마다 다른 설정(접속 정보, 사이트 식별자)을 환경변수에서 읽는다. 비밀값은 저장소에 두지 않는다
import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """필수 설정이 없을 때 서버를 시작하지 못하게 하는 오류. 메시지에 값은 담지 않는다."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    site_id: str  # 이 배포가 맡는 운영묶음의 TB_OPER_BNDL.SITE_ID. 요청이 아니라 배포 설정이 정한다(R26)


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    missing = [name for name in ("JORI_DATABASE_URL", "JORI_SITE_ID") if not env.get(name)]
    if missing:
        raise ConfigError(f"필수 환경변수가 없습니다: {', '.join(missing)}")
    return Settings(database_url=env["JORI_DATABASE_URL"], site_id=env["JORI_SITE_ID"])
