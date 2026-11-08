# Alembic 실행 환경. 접속 정보는 JORI_DATABASE_URL 환경변수나 시험이 넘긴 연결에서만 받는다
import os

from alembic import context
from sqlalchemy import create_engine

config = context.config


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, transaction_per_migration=False)
        with context.begin_transaction():
            context.run_migrations()
        return
    url = os.environ.get("JORI_DATABASE_URL")
    if not url:
        raise RuntimeError("JORI_DATABASE_URL 환경변수가 필요합니다.")
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run()
