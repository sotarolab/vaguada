"""Alembic environment. The URL and schema come from settings, never from alembic.ini."""

from __future__ import annotations

from sqlalchemy import text

from alembic import context
from camanchaca_demo.config import settings
from camanchaca_demo.store.engine import make_engine
from camanchaca_demo.store.tables import build_tables

cfg = settings()
if not cfg.database_url:
    raise SystemExit("DATABASE_URL is not set")
SCHEMA = cfg.db_schema
target_metadata = build_tables(SCHEMA).metadata


def run_migrations_online() -> None:
    engine = make_engine(cfg.database_url or "")
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
            # Only the service schema is compared; the database holds other schemas.
            include_name=lambda name, type_, parent: name == SCHEMA if type_ == "schema" else True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
