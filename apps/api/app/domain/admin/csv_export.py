# 관리자 목록 CSV 내보내기 공통 규칙: UTF-8 BOM, RFC 4180, 수식 주입 방지, 5만 행 한도, 생성 작업이력(TDD 8.6, FN-068)
import csv
import io
import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from fastapi import Response
from sqlalchemy.orm import Session

from app.audit import record_job
from app.auth.admin_access import Admin
from app.core.errors import ApiError, ErrorCode
from app.core.times import KST, utc

MAX_ROWS = 50_000  # 계약(CSV_RESPONSE)이 정한 한도. 넘으면 만들지 않고 거절한다
BOM = "﻿"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")  # 스프레드시트가 수식으로 읽는 시작 문자(TRD 4.6)


def cell(value: Any) -> str:
    """CSV 한 칸의 글자. 시각은 한국 시각, 날짜는 YYYY-MM-DD다. 글자가 수식처럼 시작하면 앞에 작은따옴표를 붙인다."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else utc(value)
        return stamp.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float):
        return str(value)  # 숫자는 글자가 아니라 값이라 음수 부호를 막지 않는다
    text = str(value)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def build_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> bytes:
    """RFC 4180에 맞춘다(쉼표 구분, 따옴표·줄바꿈 이스케이프, CRLF). 머리글도 수식 주입 방지를 거친다."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow([cell(h) for h in header])
    for row in rows:
        writer.writerow([cell(v) for v in row])
    return (BOM + out.getvalue()).encode("utf-8")


def fetch_all(db: Session, query: Any) -> list[Any]:
    """목록과 같은 조회에서 페이지 제한만 풀어 모두 읽는다. 한도를 넘으면 만들지 않는다(RULE_REJECTED)."""
    rows = list(db.execute(query.limit(MAX_ROWS + 1)).all())
    if len(rows) > MAX_ROWS:
        raise ApiError(
            ErrorCode.RULE_REJECTED,
            f"내려받을 수 있는 최대 {MAX_ROWS:,}건을 넘었습니다. 조건을 좁혀 주세요.",
        )
    return rows


def chunks(values: list[int], size: int = 1000) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def csv_response(filename: str, content: bytes) -> Response:
    """한글 파일명은 RFC 5987 형식으로 함께 준다. 캐시하지 않는다(개인정보가 섞일 수 있다)."""
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)  # 따옴표·줄바꿈·경로 문자가 헤더로 새지 않게 한다
    if not re.search(r"[A-Za-z0-9]", ascii_name.rsplit(".", 1)[0]):
        ascii_name = "export.csv"  # 한글뿐인 이름은 영문 대체 이름이 없다. 실제 이름은 filename*가 전한다
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


def audit_export(
    db: Session, admin: Admin, kind: str, count: int, request_id: str, now: datetime, filters: dict[str, Any]
) -> None:
    """만들 때마다 누가·무엇을·몇 건·어떤 조건으로 만들었는지 남긴다. 검색어 같은 입력값 자체는 남기지 않는다."""
    given = ",".join(sorted(k for k, v in filters.items() if v not in (None, "", False)))
    record_job(
        db,
        actor="AK.ADMIN",
        job="CSV_EXPORT",
        table=kind,
        key=None,
        request_id=request_id,
        now=now,
        bundle_sn=admin.bundle_sn,
        admin_sn=admin.admin_sn,
        change=f"{count}건 내보냄(조건: {given or '없음'})",
    )
