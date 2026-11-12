# 파일 검사기 선택. 실제 검사기(ClamAV clamd)는 배포 환경이 정해진 뒤 어댑터로 더한다(PRD Q9)
from functools import lru_cache

from app.adapters.scan.base import FileScanner
from app.adapters.scan.mock import MockScanner
from app.core.config import ConfigError, Settings


@lru_cache(maxsize=1)
def _mock() -> MockScanner:
    return MockScanner()


def build_scanner(settings: Settings) -> FileScanner:
    if settings.file_scanner == "mock":
        return _mock()
    raise ConfigError(f"지원하지 않는 파일 검사기입니다: {settings.file_scanner}")
