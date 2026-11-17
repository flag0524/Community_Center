# clamd 검사 어댑터(INSTREAM 전송, 통과·탐지·오류·닿지 못함·시간 초과, 설정과 선택)를 가짜 clamd로 확인한다
import socket
import socketserver
import struct
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from app.adapters.scan import build_scanner
from app.adapters.scan.base import ScanUnavailable
from app.adapters.scan.clamd import CHUNK, ClamdScanner
from app.core.config import ConfigError, Settings, load_settings

ENV = {"JORI_DATABASE_URL": "mysql://x", "JORI_SITE_ID": "s", "JORI_SECRET_KEY": "k" * 32}


class FakeClamd:
    """INSTREAM을 받아 정해 둔 응답을 돌려주는 clamd 흉내. 받은 명령과 덩어리 길이를 기록한다."""

    def __init__(self, reply: bytes | None = b"stream: OK\0", hang: bool = False) -> None:
        self.reply, self.hang = reply, hang
        self.command = b""
        self.chunks: list[int] = []
        self.received = b""
        outer = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                sock: socket.socket = self.request
                outer.command = _read(sock, len(b"zINSTREAM\0"))
                while True:
                    size = struct.unpack(">I", _read(sock, 4))[0]
                    if size == 0:
                        break
                    outer.chunks.append(size)
                    outer.received += _read(sock, size)
                if outer.hang:
                    time.sleep(2)
                elif outer.reply is not None:
                    sock.sendall(outer.reply)

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = int(self.server.server_address[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _read(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ConnectionError
        data += part
    return data


@pytest.fixture
def clamd() -> Iterator[Any]:
    made: list[FakeClamd] = []

    def start(**kw: Any) -> FakeClamd:
        fake = FakeClamd(**kw)
        made.append(fake)
        return fake

    yield start
    for fake in made:
        fake.close()


def scanner(fake: FakeClamd, **kw: Any) -> ClamdScanner:
    return ClamdScanner("127.0.0.1", fake.port, **kw)


def test_깨끗한_파일은_통과이고_명령과_내용을_INSTREAM_형식으로_보낸다(clamd: Any) -> None:
    fake = clamd()
    result = scanner(fake).scan(b"hello-file")
    assert result.clean is True and result.signature is None
    assert fake.command == b"zINSTREAM\0"
    assert fake.chunks == [10] and fake.received == b"hello-file"


def test_큰_파일은_덩어리로_나눠_보내고_내용이_그대로_간다(clamd: Any) -> None:
    fake = clamd()
    data = bytes(range(256)) * (CHUNK // 256 * 2 + 3)  # 두 덩어리를 넘는 크기
    assert scanner(fake).scan(data).clean is True
    assert fake.received == data
    assert fake.chunks[:-1] == [CHUNK] * (len(fake.chunks) - 1) and sum(fake.chunks) == len(data)


def test_탐지하면_차단이고_탐지_이름은_결과에만_담는다(clamd: Any) -> None:
    fake = clamd(reply=b"stream: Eicar-Test-Signature FOUND\0")
    result = scanner(fake).scan(b"x")
    assert (result.clean, result.signature) == (False, "Eicar-Test-Signature")


@pytest.mark.parametrize(
    "reply",
    [b"INSTREAM size limit exceeded. ERROR\0", b"stream: lstat() failed ERROR\0", b"garbage\0", b"\0", None],
)
def test_오류나_알_수_없는_응답이나_끊김은_통과로_보지_않는다(clamd: Any, reply: bytes | None) -> None:
    with pytest.raises(ScanUnavailable):
        scanner(clamd(reply=reply)).scan(b"x")


def test_연결을_거절하면_검사기에_닿지_못한_것이다() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])  # 닫으면 아무도 듣지 않는 포트다
    with pytest.raises(ScanUnavailable):
        ClamdScanner("127.0.0.1", port, timeout_seconds=1).scan(b"x")


def test_응답이_없으면_시간_초과로_닿지_못한_것이다(clamd: Any) -> None:
    started = time.monotonic()
    with pytest.raises(ScanUnavailable):
        scanner(clamd(hang=True), timeout_seconds=0.3).scan(b"x")
    assert time.monotonic() - started < 1.5


def test_설정은_기본_주소와_환경변수를_읽고_잘못된_포트는_거절한다() -> None:
    defaults = load_settings(ENV)
    assert (defaults.file_scanner, defaults.clamd_host, defaults.clamd_port) == ("mock", "127.0.0.1", 3310)
    custom = load_settings(
        {**ENV, "JORI_FILE_SCANNER": "clamd", "JORI_CLAMD_HOST": "10.0.0.5", "JORI_CLAMD_PORT": "3311"}
    )
    assert (custom.file_scanner, custom.clamd_host, custom.clamd_port) == ("clamd", "10.0.0.5", 3311)
    with pytest.raises(ConfigError):
        load_settings({**ENV, "JORI_CLAMD_PORT": "abc"})


def test_설정에_따라_검사기를_고르고_모르는_이름은_거절한다() -> None:
    base = Settings(database_url="x", site_id="s")
    picked = build_scanner(replace(base, file_scanner="clamd", clamd_host="10.0.0.5", clamd_port=3311))
    assert isinstance(picked, ClamdScanner) and (picked.host, picked.port) == ("10.0.0.5", 3311)
    assert picked.provider_name == "clamd"
    assert build_scanner(replace(base, file_scanner="mock")).provider_name == "mock"
    with pytest.raises(ConfigError):
        build_scanner(replace(base, file_scanner="unknown"))
