"""The claim: rows received after a slot change no prediction issued at that slot.
Hypothesis adds observations and model runs with later receipt times and checks that
issuing the slot again, into a fresh store, gives identical rows."""

from datetime import date, timedelta

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from camanchaca_demo import localday
from camanchaca_demo.forecast.baselines import Persistence, RawModel
from camanchaca_demo.forecast.issue import issue_slot
from camanchaca_demo.store.read import FrameStore
from tests.unit.test_baselines import SID, run_row
from tests.unit.test_daily import TZ, hourly_obs

DAY = date(2026, 7, 15)
HOUR = 12


def seed(store: FrameStore) -> None:
    start, _ = localday.day_bounds(DAY - timedelta(days=1), TZ)
    store.write_observations(hourly_obs(start, [10.0 + (i % 24) * 0.5 for i in range(36)]))
    store.write_model_runs(
        pd.DataFrame([run_row("gfs", "t2m", start, [15.0 + (i % 24) for i in range(96)])])
    )


def strip(rows):
    return sorted(
        (r["forecaster"], r["target"], r["local_day"], r["quantiles"]["p50"]) for r in rows
    )


@given(
    late_obs=st.lists(st.floats(-10, 45, allow_nan=False), min_size=0, max_size=12),
    late_run=st.lists(st.floats(-10, 45, allow_nan=False), min_size=0, max_size=48),
)
@settings(max_examples=60, deadline=None)
def test_later_rows_change_nothing(late_obs: list[float], late_run: list[float]) -> None:
    slot = localday.slot_time(DAY, HOUR, TZ)
    received = slot + timedelta(seconds=1)
    a, b = FrameStore(), FrameStore()
    seed(a)
    seed(b)
    # Rows that arrive after the slot: same valid times, later receipt.
    if late_obs:
        obs = hourly_obs(slot - timedelta(hours=len(late_obs)), late_obs)
        obs["received_at"] = received + timedelta(minutes=5)
        b.write_observations(obs)
    if late_run:
        run = run_row("gfs", "t2m", slot - timedelta(hours=3), late_run)
        run["received_at"] = pd.Timestamp(received + timedelta(minutes=5))
        b.write_model_runs(pd.DataFrame([run]))
    fs = [RawModel("gfs"), Persistence()]
    ra = issue_slot(a, SID, TZ, DAY, HOUR, fs, received_at=received)
    rb = issue_slot(b, SID, TZ, DAY, HOUR, fs, received_at=received)
    assert strip(ra) == strip(rb)
