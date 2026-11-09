# 로컬 디스크 파일 저장소에서 객체키로 내용을 읽는다(웹 루트 밖, TRD 4.5). 쓰기는 파일 업로드 단계에서 만든다
from pathlib import Path


class StorageError(RuntimeError):
    """저장소에서 파일을 읽지 못했다. 메시지에 경로를 담지 않는다."""


def read_blob(root: str, key: str) -> bytes:
    """키가 저장소 밖을 가리키면(.. 등) 읽지 않는다. DB 값이라도 한 번 더 막는다."""
    base = Path(root).resolve()
    target = (base / key).resolve()
    if not target.is_relative_to(base) or target == base:
        raise StorageError("저장소 밖의 경로")
    try:
        return target.read_bytes()
    except OSError:
        raise StorageError("파일을 읽지 못했다") from None
