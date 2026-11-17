# 파일 검사기 선택. 모의 검사기와 ClamAV(clamd) 어댑터가 있고 어느 것을 쓸지는 배포 설정이 정한다(PRD Q9)
from functools import lru_cache

from app.adapters.scan.base import FileScanner
from app.adapters.scan.clamd import ClamdScanner
from app.adapters.scan.mock import MockScanner
from app.core.config import ConfigError, Settings


@lru_cache(maxsize=1)
def _mock() -> MockScanner:
    return MockScanner()


def build_scanner(settings: Settings) -> FileScanner:
    if settings.file_scanner == "mock":
        return _mock()
    if settings.file_scanner == "clamd":
        return ClamdScanner(settings.clamd_host, settings.clamd_port)
    raise ConfigError(f"지원하지 않는 파일 검사기입니다: {settings.file_scanner}")
