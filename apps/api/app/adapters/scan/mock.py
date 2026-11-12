# 시험·개발용 모의 검사기. 표준 시험 문자열(EICAR)이나 시험이 정한 내용을 악성으로 본다
from dataclasses import dataclass, field

from app.adapters.scan.base import ScanResult, ScanUnavailable

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass
class MockScanner:
    provider_name: str = "mock"
    scanned: list[int] = field(default_factory=list)  # 검사한 내용의 길이(내용은 담지 않는다)
    unavailable: bool = False
    infected: list[bytes] = field(default_factory=list)  # 이 내용이 들어 있으면 악성으로 본다

    def scan(self, data: bytes) -> ScanResult:
        if self.unavailable:
            raise ScanUnavailable("검사기에 닿지 못했다")
        self.scanned.append(len(data))
        if EICAR in data or any(bad in data for bad in self.infected):
            return ScanResult(False, "Mock.Test-Signature")
        return ScanResult(True)
