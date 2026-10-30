"""The Postgres store against the same contract as the in-memory one. Runs only when
DATABASE_URL is set; writes under a test station id and removes its rows afterwards."""

import pytest
from sqlalchemy import delete

from camanchaca_demo.config import settings
from camanchaca_demo.store.engine import make_engine
from camanchaca_demo.store.read import PgStore
from tests.store_contract import SID, check_journal, check_store

pytestmark = pytest.mark.skipif(not settings().database_url, reason="DATABASE_URL not set")


def _cleanup(store: PgStore) -> None:
    t = store.t
    with store.engine.begin() as conn:
        for table in (
            t.observations,
            t.model_runs,
            t.settlements,
            t.markets,
            t.predictions,
            t.journal,
        ):
            conn.execute(delete(table).where(table.c.station_id == SID))


def test_pg_store_meets_the_contract() -> None:
    cfg = settings()
    assert cfg.database_url
    store = PgStore(make_engine(cfg.database_url), cfg.db_schema)
    _cleanup(store)
    try:
        check_store(store)
        check_journal(store)
    finally:
        _cleanup(store)
