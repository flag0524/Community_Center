# 업로드 파일 검증: 확장자·크기·내용 형식을 서버가 검사하고 파일명을 정리한다(TRD 4.5, NF-SER-002, NF-SER-007)
import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.core.errors import ApiError, ErrorCode

MAX_BYTES = 20 * 1024 * 1024  # 파일당 20MB(Q9 확정 전 가정)
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # 구형 오피스·한글 문서 컨테이너
ZIP = b"PK\x03\x04"  # 신형 오피스·한글(hwpx) 문서 컨테이너
JPEG = b"\xff\xd8\xff"

# 허용 확장자 → (서버가 정하는 MIME, 내용 시작 바이트). 클라이언트가 보낸 형식은 믿지 않는다
ALLOWED: dict[str, tuple[str, bytes]] = {
    "pdf": ("application/pdf", b"%PDF-"),
    "hwp": ("application/x-hwp", OLE),
    "hwpx": ("application/vnd.hancom.hwpx", ZIP),
    "doc": ("application/msword", OLE),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ZIP),
    "xls": ("application/vnd.ms-excel", OLE),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ZIP),
    "jpg": ("image/jpeg", JPEG),
    "jpeg": ("image/jpeg", JPEG),
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}
ALLOWED_EXTENSIONS = sorted(ALLOWED)
STEM_MAX = 200  # 컬럼(300자) 안에서 확장자를 남기려고 줄인다
UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f\\/:*?"<>|]+')


@dataclass(frozen=True)
class Upload:
    name: str  # 정리한 원본 이름(DB에만 둔다)
    extension: str
    mime: str
    size: int
    sha256: str
    data: bytes


def clean_name(raw: str) -> str:
    """경로 구분자와 제어·특수 문자를 없애고 NFC로 맞춘다. 숨김 파일처럼 점으로 시작하지 않게 한다."""
    base = re.split(r"[\\/]", unicodedata.normalize("NFC", raw))[-1]
    base = UNSAFE_NAME.sub("_", base).strip()
    stem, dot, ext = base.rpartition(".")  # 확장자를 먼저 나눠야 `.pdf` 같은 이름이 확장자를 잃지 않는다
    if not dot:
        stem, ext = base, ""
    stem = (stem.lstrip(". ").strip() or "file")[:STEM_MAX]  # 숨김 파일처럼 점으로 시작하지 않게 한다
    return f"{stem}.{ext}" if ext else stem


def _reject(message: str) -> ApiError:
    return ApiError(ErrorCode.RULE_REJECTED, message, fields={"file": message})


def validate_upload(raw_name: str, data: bytes) -> Upload:
    """허용 확장자, 비어 있지 않음, 20MB 이하, 내용이 확장자의 형식인지를 확인한다. 하나라도 어긋나면 422다."""
    name = clean_name(raw_name or "")
    extension = name.rpartition(".")[2].lower() if "." in name else ""
    if extension not in ALLOWED:
        raise _reject(f"올릴 수 없는 파일 형식입니다. 허용: {', '.join(ALLOWED_EXTENSIONS)}")
    if not data:
        raise _reject("빈 파일은 올릴 수 없습니다.")
    if len(data) > MAX_BYTES:
        raise _reject(f"파일은 {MAX_BYTES // (1024 * 1024)}MB 이하여야 합니다.")
    mime, magic = ALLOWED[extension]
    if not data.startswith(magic):
        raise _reject("파일 내용이 확장자와 맞지 않습니다.")
    return Upload(name, extension, mime, len(data), hashlib.sha256(data).hexdigest(), data)
