import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- wire the app's models + DB URL ----------------------------------------
import os  # noqa: E402
import sys  # noqa: E402

# alembic/ lives inside backend/; make the `app` package importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base, _make_engine  # noqa: E402
from app import models  # noqa: E402,F401  (import registers every model on Base.metadata)
from app.config import settings  # noqa: E402

# Respect the app's resolved DB URL: DATABASE_URL in prod (Postgres), SQLite locally.
config.set_main_option("sqlalchemy.url", settings.effective_database_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an Engine and associate a connection with the context.

    Reuse the app's engine builder so managed-Postgres SSL params (Aiven's
    `?sslmode=require`, `channel_binding`) are translated to asyncpg's `ssl`
    connect-arg exactly as the running app does — otherwise asyncpg rejects them.
    """

    connectable = _make_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
