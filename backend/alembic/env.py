"""Alembic async environment for the skill marketplace."""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from db.models import Base

target_metadata = Base.metadata

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    context.config.get_main_option("sqlalchemy.url"),
)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")


def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
