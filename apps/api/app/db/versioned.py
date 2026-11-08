# 낙관적 잠금 갱신. 화면이 읽은 RCRD_VER와 같을 때만 고치고 1 올린다(TDD 10.1, 스키마 4절)
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Table, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode


def update_versioned(
    session: Session,
    table: Table,
    key: Mapping[str, Any],
    expected_version: int,
    values: Mapping[str, Any],
) -> int:
    """고친 뒤의 버전을 돌려준다. 행이 없으면 404, 버전이 다르면 409(VERSION_CONFLICT)다.

    key에는 기본키와 함께 운영묶음 조건을 넣는다. 그래야 다른 묶음의 행을 고칠 수 없다(C04).
    """
    where = [table.c[name] == value for name, value in key.items()]
    result = session.execute(
        update(table)
        .where(*where, table.c.RCRD_VER == expected_version)
        .values(**values, RCRD_VER=table.c.RCRD_VER + 1, MDFCN_DT=func.utc_timestamp())
    )
    if result.rowcount == 1:  # type: ignore[attr-defined]
        return expected_version + 1
    exists = session.execute(select(table.c.RCRD_VER).where(*where)).first()
    if exists is None:
        raise ApiError(ErrorCode.NOT_FOUND)
    raise ApiError(ErrorCode.VERSION_CONFLICT)
