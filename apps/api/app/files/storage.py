# 로컬 디스크 파일 저장소. 웹 루트 밖에서 객체키로 읽고 쓴다(TRD 4.5). 키는 묶음 접두부 + 난수이고 원본 이름은 DB에만 둔다
import contextlib
import os
import secrets
from pathlib import Path


class StorageError(RuntimeError):
    """저장소에서 파일을 읽거나 쓰지 못했다. 메시지에 경로를 담지 않는다."""


def _resolve(root: str, key: str) -> Path:
    """키가 저장소 밖을 가리키면(.. 등) 거부한다. DB 값이라도 한 번 더 막는다."""
    base = Path(root).resolve()
    target = (base / key).resolve()
    if not target.is_relative_to(base) or target == base:
        raise StorageError("저장소 밖의 경로")
    return target


def read_blob(root: str, key: str) -> bytes:
    try:
        return _resolve(root, key).read_bytes()
    except OSError:
        raise StorageError("파일을 읽지 못했다") from None


def new_key(bundle_sn: int) -> str:
    """묶음 접두부 + 난수 객체키. 추측할 수 없고 원본 이름·확장자를 담지 않는다. 폴더를 나눠 한 폴더가 커지지 않게 한다."""
    token = secrets.token_hex(16)
    return f"b{bundle_sn}/{token[:2]}/{token}"


def write_blob(root: str, key: str, data: bytes) -> None:
    """임시 파일에 쓴 뒤 바꿔 놓아, 읽는 쪽이 반쯤 쓴 파일을 보지 않게 한다. 같은 키가 이미 있으면 덮어쓰지 않는다."""
    target = _resolve(root, key)
    temp = target.with_name(target.name + ".part")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise StorageError("이미 있는 객체키")
        temp.write_bytes(data)
        os.replace(temp, target)
    except OSError:
        temp.unlink(missing_ok=True)
        raise StorageError("파일을 쓰지 못했다") from None


def remove_blob(root: str, key: str) -> None:
    """저장한 뒤 DB 기록이 실패했을 때 고아 파일을 치운다. 없으면 조용히 지나간다."""
    with contextlib.suppress(OSError, StorageError):
        _resolve(root, key).unlink(missing_ok=True)
