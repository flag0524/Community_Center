# ClamAV clamd에 INSTREAM으로 파일을 보내 검사하는 어댑터. 닿지 못하거나 결과를 알 수 없으면 통과로 보지 않는다(TRD 4.5, NF-SER-002)
import socket
import struct
from dataclasses import dataclass

from app.adapters.scan.base import ScanResult, ScanUnavailable

CHUNK = 64 * 1024  # clamd에 보내는 한 덩어리의 크기
MAX_REPLY = 4096  # 응답은 한 줄이다. 이보다 길면 잘못된 상대로 본다


@dataclass
class ClamdScanner:
    host: str
    port: int
    timeout_seconds: float = 30.0
    provider_name: str = "clamd"

    def _ask(self, data: bytes) -> str:
        with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as sock:
            sock.sendall(b"zINSTREAM\0")
            for start in range(0, len(data), CHUNK):
                chunk = data[start : start + CHUNK]
                sock.sendall(struct.pack(">I", len(chunk)) + chunk)
            sock.sendall(struct.pack(">I", 0))  # 길이 0은 끝을 뜻한다
            reply = b""
            while not reply.endswith(b"\0") and len(reply) < MAX_REPLY:
                part = sock.recv(1024)
                if not part:  # 응답을 다 받기 전에 상대가 연결을 닫았다
                    break
                reply += part
        return reply.rstrip(b"\0\n").decode("utf-8", "replace")

    def scan(self, data: bytes) -> ScanResult:
        try:
            reply = self._ask(data)
        except OSError:  # 연결 거절·시간 초과·끊김은 모두 검사기에 닿지 못한 것이다
            raise ScanUnavailable("검사기에 닿지 못했다") from None
        if reply.endswith(" OK"):
            return ScanResult(True)
        if reply.endswith(" FOUND"):
            name = reply.split(": ", 1)[-1].removesuffix(" FOUND")
            return ScanResult(False, name or "unknown")
        raise ScanUnavailable("검사 결과를 알 수 없다")  # ERROR·빈 응답·알 수 없는 응답은 통과로 보지 않는다
