"""A feed never raises: a failing fetch writes a heartbeat error and returns the empty frame."""

from datetime import UTC, datetime

import pandas as pd

from camanchaca_demo.ingest.feed import run_feed
from camanchaca_demo.store import schemas
from camanchaca_demo.store.read import FrameStore

NOW = datetime(2026, 10, 30, 4, tzinfo=UTC)


def test_failure_is_recorded_not_raised() -> None:
    store = FrameStore()

    def boom() -> pd.DataFrame:
        raise RuntimeError("upstream down")

    out = run_feed(
        store, "x", boom, store.write_observations, schemas.empty(schemas.OBS_COLUMNS), NOW
    )
    assert out.empty
    assert store.beats["x"]["last_success"] is None
    assert "upstream down" in store.beats["x"]["last_error"]


def test_success_writes_rows_and_clears_error() -> None:
    store = FrameStore()
    store.heartbeat("x", False, 0, "earlier failure", NOW)
    frame = pd.DataFrame(
        {
            "station_id": ["asos:KLAX"],
            "valid_at": [NOW],
            "received_at": [NOW],
            "source": ["test"],
            "var": ["t2m"],
            "value": [20.0],
            "precision": [None],
        }
    )
    out = run_feed(
        store, "x", lambda: frame, store.write_observations, schemas.empty(schemas.OBS_COLUMNS), NOW
    )
    assert len(out) == 1
    assert store.beats["x"]["last_success"] == NOW
    assert store.beats["x"]["last_error"] is None
    assert store.beats["x"]["rows"] == 1
