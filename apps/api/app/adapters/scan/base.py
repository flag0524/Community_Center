# 파일 바이러스 검사 어댑터 규약. 검사기가 못 쓰는 상태를 깨끗함으로 오해하지 않게 오류를 따로 둔다(TRD 4.5, NF-SER-002)
from dataclasses import dataclass
from typing import Protocol


class ScanUnavailable(RuntimeError):
    """검사기에 닿지 못했거나 결과를 알 수 없다. 검사 대기로 두고 다음 주기에 다시 한다. 통과로 보지 않는다."""


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str | None = None  # 탐지 이름. 내부 기록에만 쓰고 화면에는 내보내지 않는다


class FileScanner(Protocol):
    provider_name: str

    def scan(self, data: bytes) -> ScanResult:
        """파일 내용을 검사한다. 닿지 못하면 ScanUnavailable을 던진다."""
        ...
