# 관리자 밖 도메인이 관리자 서비스를 import하는 의존 역전이 새로 생기지 않게 지키는 시험(ADR-111·113)
import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[1] / "app" / "domain"

# 남아 있는 예외. 줄이는 방향으로만 바꾼다. 새 항목을 더하려면 먼저 공용 모듈로 옮길 수 없는지 본다.
ALLOWED = {
    # 관리자 문의 서비스의 조회 쿼리(_base)를 주민 문의 조회가 재사용한다
    ("board/inquiry.py", "app.domain.admin.inquiry_service"),
    # 권한 코드 열거형. 주민 쪽 이름 변경 승인 화면이 관리자 권한 코드를 안다
    ("member/name_change_service.py", "app.domain.admin.types"),
}


def admin_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.domain.admin"):
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("app.domain.admin"))
    return found


def test_관리자_밖_도메인은_허용_목록_밖에서_관리자_서비스를_import하지_않는다() -> None:
    found = {
        (path.relative_to(DOMAIN).as_posix(), module)
        for path in DOMAIN.rglob("*.py")
        if path.relative_to(DOMAIN).parts[0] != "admin"
        for module in admin_imports(path)
    }
    assert found == ALLOWED, (
        f"새로 생긴 의존 {sorted(found - ALLOWED)}, 해소된 의존 {sorted(ALLOWED - found)}"
    )


def test_감면과_파일_도메인은_관리자_모듈에_기대지_않는다() -> None:
    for name in ("reduction", "file"):
        for path in (DOMAIN / name).rglob("*.py"):
            assert admin_imports(path) == set(), path.name
