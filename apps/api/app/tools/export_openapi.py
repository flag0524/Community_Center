# FastAPI 앱에서 OpenAPI 계약 파일을 만들어 프런트 타입 생성기에 넘기는 도구
import json
import sys
from pathlib import Path

from app.main import create_app


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("사용법 python -m app.tools.export_openapi <출력 파일>", file=sys.stderr)
        return 2
    schema = create_app().openapi()
    target = Path(argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    # 키 정렬과 고정된 줄바꿈으로 같은 코드는 항상 같은 파일을 만든다.
    target.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
