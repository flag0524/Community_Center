# 업로드 검증(확장자·크기·내용 형식·파일명 정리)과 로컬 저장소 쓰기를 확인하는 시험(DB 없음)
from pathlib import Path

import pytest

from app.core.errors import ApiError
from app.domain.file.upload import ALLOWED, ALLOWED_EXTENSIONS, MAX_BYTES, clean_name, validate_upload
from app.files.storage import StorageError, new_key, read_blob, remove_blob, write_blob

PDF = b"%PDF-1.7\n..."
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 8
JPG = b"\xff\xd8\xff\xe0" + b"x" * 8
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 8
ZIP = b"PK\x03\x04" + b"x" * 8
SAMPLE = {
    "pdf": PDF,
    "png": PNG,
    "jpg": JPG,
    "jpeg": JPG,
    "hwp": OLE,
    "doc": OLE,
    "xls": OLE,
    "hwpx": ZIP,
    "docx": ZIP,
    "xlsx": ZIP,
}


def message(error: ApiError) -> str:
    return error.message


# --- 허용 형식 ----------------------------------------------------------------------------------


def test_허용_확장자는_문서가_정한_열_가지다() -> None:
    assert ALLOWED_EXTENSIONS == sorted(
        ["pdf", "hwp", "hwpx", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png"]
    )


@pytest.mark.parametrize("extension", sorted(SAMPLE))
def test_허용_확장자는_맞는_내용이면_통과하고_서버가_MIME을_정한다(extension: str) -> None:
    upload = validate_upload(f"계획서.{extension}", SAMPLE[extension])
    assert upload.extension == extension and upload.mime == ALLOWED[extension][0]
    assert upload.size == len(SAMPLE[extension]) and len(upload.sha256) == 64


@pytest.mark.parametrize(
    "name", ["a.exe", "a.php", "a.html", "a.svg", "a.zip", "a.js", "a.pdf.exe", "a", "a.", ".pdf.", "a.p df"]
)
def test_허용하지_않는_확장자는_거절한다(name: str) -> None:
    with pytest.raises(ApiError) as caught:
        validate_upload(name, PDF)
    assert caught.value.code.value == "RULE_REJECTED" and "file" in (caught.value.fields or {})


def test_확장자는_대소문자를_가리지_않는다() -> None:
    assert validate_upload("A.PDF", PDF).extension == "pdf"
    assert validate_upload("사진.JpG", JPG).extension == "jpg"


def test_빈_파일과_한도를_넘는_파일은_거절하고_한도_정확히는_받는다() -> None:
    with pytest.raises(ApiError):
        validate_upload("a.pdf", b"")
    exact = PDF + b"x" * (MAX_BYTES - len(PDF))
    assert validate_upload("a.pdf", exact).size == MAX_BYTES
    with pytest.raises(ApiError) as caught:
        validate_upload("a.pdf", exact + b"x")
    assert "20MB" in caught.value.message


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.pdf", PNG),
        ("a.png", PDF),
        ("a.jpg", PNG),
        ("a.docx", OLE),
        ("a.doc", ZIP),
        ("a.hwp", ZIP),
        ("a.pdf", b"<html>"),
    ],
)
def test_내용이_확장자의_형식이_아니면_거절한다(name: str, data: bytes) -> None:
    with pytest.raises(ApiError) as caught:
        validate_upload(name, data)
    assert "맞지 않" in caught.value.message


# --- 파일명 정리 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\a\\문서.pdf", "문서.pdf"),
        ("a/b/c.pdf", "c.pdf"),
        ('a"b<c>d|e.pdf', "a_b_c_d_e.pdf"),
        ("a\r\nb.pdf", "a_b.pdf"),
        ("...hidden.pdf", "hidden.pdf"),
        (" 공백 .pdf", "공백.pdf"),
        (".pdf", "file.pdf"),
        ("", "file"),
        ("noext", "noext"),
    ],
)
def test_파일명은_경로와_특수문자를_없앤다(raw: str, cleaned: str) -> None:
    assert clean_name(raw) == cleaned


def test_긴_파일명은_확장자를_남기고_줄이고_한글은_NFC로_맞춘다() -> None:
    long = clean_name("가" * 500 + ".pdf")
    assert long.endswith(".pdf") and len(long) == 200 + 4
    decomposed = "한글".encode("utf-16").decode("utf-16")  # 조합형 입력
    import unicodedata

    assert clean_name(unicodedata.normalize("NFD", "한글.pdf")) == unicodedata.normalize("NFC", "한글.pdf")
    assert decomposed


# --- 저장소 -------------------------------------------------------------------------------------


def test_객체키는_묶음_접두부와_난수이고_원본_이름을_담지_않는다() -> None:
    keys = {new_key(7) for _ in range(200)}
    assert len(keys) == 200
    for key in keys:
        prefix, shard, token = key.split("/")
        assert prefix == "b7" and token.startswith(shard) and len(token) == 32 and ".pdf" not in key


def test_저장하고_읽으며_같은_키는_덮어쓰지_않고_임시_파일을_남기지_않는다(tmp_path: Path) -> None:
    key = new_key(1)
    write_blob(str(tmp_path), key, b"hello")
    assert read_blob(str(tmp_path), key) == b"hello"
    with pytest.raises(StorageError):
        write_blob(str(tmp_path), key, b"other")
    assert read_blob(str(tmp_path), key) == b"hello"  # 덮어쓰지 않았다
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("key", ["../outside", "a/../../outside", "/etc/passwd", ".", ""])
def test_저장소_밖을_가리키는_키는_읽고_쓰지_않는다(tmp_path: Path, key: str) -> None:
    with pytest.raises(StorageError):
        read_blob(str(tmp_path), key)
    with pytest.raises(StorageError):
        write_blob(str(tmp_path), key, b"x")
    assert not any(p.name == "outside" for p in tmp_path.parent.iterdir())


def test_없는_파일을_읽으면_저장소_오류이고_치우기는_조용하다(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        read_blob(str(tmp_path), "b1/aa/none")
    remove_blob(str(tmp_path), "b1/aa/none")
    remove_blob(str(tmp_path), "../outside")  # 밖을 가리켜도 아무 일도 없다
    key = new_key(1)
    write_blob(str(tmp_path), key, b"x")
    remove_blob(str(tmp_path), key)
    with pytest.raises(StorageError):
        read_blob(str(tmp_path), key)


def test_검증한_결과의_이름은_정리한_이름이고_빈_파일은_빈_파일이라고_알린다() -> None:
    upload = validate_upload("../../a/b\\c.pdf", PDF)
    assert upload.name == "c.pdf"  # 저장되는 이름은 경로가 없는 정리한 이름이다
    with pytest.raises(ApiError) as empty:
        validate_upload("a.pdf", b"")
    assert "빈 파일" in empty.value.message
    with pytest.raises(ApiError):
        validate_upload("a.pdf", b"%PDFx")  # 시작 바이트는 %PDF-까지 맞아야 한다
