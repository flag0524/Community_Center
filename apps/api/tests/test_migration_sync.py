# 저장된 첫 마이그레이션 SQL이 설계안에서 지금 만든 결과와 같은지 보는 시험(배포 전에만 성립한다)
import pytest

from app.tools.generate_ddl import MIGRATIONS, generate


@pytest.mark.parametrize("name", ["0001_initial_schema.up.sql", "0001_initial_schema.down.sql"])
def test_저장된_마이그레이션이_설계안에서_만든_결과와_같다(name: str) -> None:
    """문서를 고쳤다면 `python -m app.tools.generate_ddl`로 다시 만든다. 배포한 뒤에는 새 버전을 더한다."""
    committed = (MIGRATIONS / name).read_text(encoding="utf-8")
    assert committed == generate()[name]
