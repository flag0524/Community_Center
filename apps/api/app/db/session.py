# DB 엔진과 요청 단위 세션. 요청 하나가 트랜잭션 하나이고 성공하면 커밋, 예외가 나면 되돌린다
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, load_settings


def create_db_engine(settings: Settings) -> Engine:
    """시각은 UTC로 저장한다(스키마 N07). 서버 설정과 관계없이 세션마다 UTC로 고정한다."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_db_engine(load_settings())


def open_session(engine: Engine) -> Session:
    # 의도하지 않은 지연 쓰기를 막으려고 autoflush를 끈다. 쓰기는 명시한 문장만 보낸다.
    return Session(engine, expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """FastAPI 의존성. 응답을 보내기 전에 커밋하므로 커밋 실패가 성공 응답으로 새지 않는다."""
    session = open_session(get_engine())
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
