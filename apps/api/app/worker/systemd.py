# systemd 알림(sd_notify). 워커가 살아 있음을 watchdog에 알리고 기동 완료를 알린다(TDD 7, 11장, ADR-027)
import os
import socket
import sys
from collections.abc import Callable, Mapping

Sender = Callable[[str, bytes], None]


def _send_datagram(address: str, payload: bytes) -> None:
    if sys.platform == "win32":
        raise OSError("윈도에는 유닉스 소켓이 없다")  # systemd는 리눅스에만 있다
    # 주소가 @로 시작하면 리눅스의 추상 소켓이다
    target = "\0" + address[1:] if address.startswith("@") else address
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(target)
        sock.sendall(payload)


def notify(message: str, environ: Mapping[str, str] | None = None, send: Sender = _send_datagram) -> bool:
    """systemd에 상태를 알린다(예: READY=1, WATCHDOG=1). systemd 밖(개발·시험)이면 아무것도 하지 않고 False다.
    알림이 실패해도 워커를 멈추지 않는다. 멈추면 watchdog이 정지로 보고 다시 시작하므로 그것으로 충분하다."""
    address = (os.environ if environ is None else environ).get("NOTIFY_SOCKET")
    if not address:
        return False
    try:
        send(address, message.encode())
    except OSError:
        return False
    return True
