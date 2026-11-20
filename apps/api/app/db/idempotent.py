# 멱등 삽입. 같은 키·같은 요청이면 이전 결과를 돌려주고, 같은 키·다른 요청이면 거절한다(TDD 10.1, C08)
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import Row, RowMapping, Select, Table, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode

DUPLICATE_ENTRY = 1062


def insert_idempotent(
    session: Session,
    table: Table,
    values: Mapping[str, Any],
    same_request: Callable[[RowMapping], bool],
) -> tuple[RowMapping, bool]:
    """(행, 이전 요청의 재전송 여부)를 돌려준다. values에는 OPER_BNDL_SN과 IDEM_KEY가 있어야 한다.

    중복은 (묶음, 멱등키) 유일키 때문에 생겼을 때만 재전송으로 본다. 다른 유일키(예 유효 신청 중복)가
    막은 것이면 그대로 올려 호출한 쪽이 업무 오류로 바꾸게 한다.
    """
    try:
        # InnoDB는 중복 키로 실패한 문장만 되돌리고 바깥 트랜잭션은 이어 가므로 저장점이 필요 없다
        session.execute(insert(table).values(**values))
    except IntegrityError as error:
        if error.orig is None or error.orig.args[0] != DUPLICATE_ENTRY:
            raise
        existing = (
            session.execute(
                select(table).where(
                    table.c.OPER_BNDL_SN == values["OPER_BNDL_SN"], table.c.IDEM_KEY == values["IDEM_KEY"]
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            raise
        if not same_request(existing):
            raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT) from None
        return existing, True
    created = (
        session.execute(
            select(table).where(
                table.c.OPER_BNDL_SN == values["OPER_BNDL_SN"], table.c.IDEM_KEY == values["IDEM_KEY"]
            )
        )
        .mappings()
        .one()
    )
    return created, False


def find_prior(
    session: Session,
    query: Select[Any],
    table: Table,
    bundle_sn: int,
    key: str,
    same_request: Callable[[Row[Any]], bool],
) -> Row[Any] | None:
    """같은 (묶음, 멱등키)로 이미 처리된 요청의 행. 없으면 None이다.

    행이 있는데 같은 요청이 아니면 멱등키 충돌로 거절한다. 호출한 쪽은 행이 있으면 이전 결과를 돌려준다.
    선행 조회는 호출한 쪽이 잠금을 얻은 뒤에 해야 동시 재전송도 걸린다(FN-033).
    """
    prior = session.execute(query.where(table.c.OPER_BNDL_SN == bundle_sn, table.c.IDEM_KEY == key)).first()
    if prior is None:
        return None
    if not same_request(prior):
        raise ApiError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return prior
