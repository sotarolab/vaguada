"""Engine construction. One place knows about the pooler."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine


def make_engine(database_url: str) -> Engine:
    """A Neon pooled host runs through a transaction-mode pooler, which does not keep
    server-side prepared statements between transactions. psycopg prepares after a few
    executions by default; turn that off so the same engine works pooled or direct."""
    url = database_url
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
