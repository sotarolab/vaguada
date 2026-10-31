"""Claims about the baselines. Read these before the code.

1. RawModel(m) for a point model is the daily extreme of m's latest run on the target day.
   For the NWS it is the value of the NWS daily series for that day.
2. Persistence is yesterday's settled value; without a settlement it is yesterday's observed
   extreme when at least 18 hours were observed; otherwise nothing.
3. A forecaster that lacks what it needs returns None and never raises.
4. issue() writes one row per (forecaster, target, day) the slot covers, with as_of equal to
   the slot instant and a positive lead in its features.
"""

from datetime import date, timedelta

import pandas as pd

from camanchaca_demo import localday
from camanchaca_demo.forecast import issue as issue_mod
from camanchaca_demo.forecast.base import Inputs
from camanchaca_demo.forecast.baselines import Persistence, RawModel, default_forecasters
from camanchaca_demo.store.read import FrameStore
from tests.unit.test_daily import TZ, hourly_obs

DAY = date(2026, 7, 15)
SID = "asos:KLAX"


def run_row(model: str, var: str, run_at, values: list[float | None], step_h: int = 0):
    return {
        "model": model,
        "station_id": SID,
        "run_at": pd.Timestamp(run_at),
        "received_at": pd.Timestamp(run_at),
        "source": "test",
        "var": var,
        "step_h": step_h,
        "values": values,
    }


def inputs(obs=None, runs=None, settlements=None, as_of=None) -> Inputs:
    start, _ = localday.day_bounds(DAY, TZ)
    return Inputs(
        station_id=SID,
        tz=TZ,
        as_of=as_of or start,
        obs=obs if obs is not None else hourly_obs(start, []),
        runs=runs if runs is not None else pd.DataFrame(columns=["model", "var"]),
        settlements=settlements
        if settlements is not None
        else pd.DataFrame(columns=["local_day", "target", "value"]),
    )


def test_raw_point_model_is_its_daily_extreme() -> None:
    start, _ = localday.day_bounds(DAY, TZ)
    values = [20.0 + i for i in range(24)]  # max 43 at the last hour, min 20
    runs = pd.DataFrame([run_row("gfs", "t2m", start, values)])
    p = RawModel("gfs").predict("tmax", DAY, inputs(runs=runs))
    assert p is not None and p.quantiles["p50"] == 43.0 and p.features["n_hours"] == 24
    assert RawModel("gfs").predict("tmin", DAY, inputs(runs=runs)).quantiles["p50"] == 20.0
    assert RawModel("gfs").predict("tmax", DAY + timedelta(days=3), inputs(runs=runs)) is None
    assert RawModel("hrrr").predict("tmax", DAY, inputs(runs=runs)) is None


def test_raw_nws_uses_its_daily_series() -> None:
    start, _ = localday.day_bounds(DAY, TZ)
    runs = pd.DataFrame([run_row("nws", "tmax", start, [30.0, 31.0, None])])
    f = RawModel("nws")
    assert f.predict("tmax", DAY, inputs(runs=runs)).quantiles["p50"] == 30.0
    assert f.predict("tmax", DAY + timedelta(days=1), inputs(runs=runs)).quantiles["p50"] == 31.0
    assert f.predict("tmax", DAY + timedelta(days=2), inputs(runs=runs)) is None


def test_persistence_prefers_settlement_then_observed() -> None:
    yday = DAY - timedelta(days=1)
    settled = pd.DataFrame([{"local_day": yday, "target": "tmax", "value": 28.5}])
    assert Persistence().predict("tmax", DAY, inputs(settlements=settled)).quantiles["p50"] == 28.5
    start, _ = localday.day_bounds(yday, TZ)
    obs = hourly_obs(start, [10.0 + i for i in range(24)])
    p = Persistence().predict("tmax", DAY, inputs(obs=obs))
    assert p is not None and p.quantiles["p50"] == 33.0 and p.features["source"] == "observed"
    thin = hourly_obs(start, [10.0, 11.0, 12.0])
    assert Persistence().predict("tmax", DAY, inputs(obs=thin)) is None
    assert Persistence().predict("tmax", DAY, inputs()) is None


def test_issue_writes_one_row_per_forecaster_target_and_day() -> None:
    store = FrameStore()
    start, _ = localday.day_bounds(DAY, TZ)
    slot = localday.slot_time(DAY, 6, TZ)
    store.write_model_runs(
        pd.DataFrame(
            [
                run_row("gfs", "t2m", start, [20.0 + (i % 24) for i in range(72)]),
                run_row("nws", "tmax", start, [30.0, 31.0, 32.0]),
            ]
        )
    )
    rows = issue_mod.issue_slot(
        store, SID, TZ, DAY, 6, [RawModel("gfs"), RawModel("nws"), Persistence()]
    )
    targets = localday.targets_for_slot(DAY, 6)
    assert all(r["as_of"] == slot for r in rows)
    assert all(r["features"]["lead_h"] > 0 for r in rows)
    # gfs and nws have every (target, day) the 06:00 slot covers that lies inside their horizon
    got = {(r["forecaster"], r["target"], r["local_day"]) for r in rows}
    for target, day in targets:
        assert ("raw_gfs", target, day) in got
    assert ("raw_nws", "tmax", DAY) in got and ("raw_nws", "tmin", DAY) not in got
    assert not any(r["forecaster"] == "persistence" for r in rows)  # nothing to persist
    assert len(store.preds) == len(rows)
    # Issuing the same slot again adds nothing.
    assert issue_mod.issue_slot(store, SID, TZ, DAY, 6, [RawModel("gfs")]) and len(
        store.preds
    ) == len(rows)


def test_default_forecasters_have_unique_names() -> None:
    names = [f.name for f in default_forecasters()]
    assert len(names) == len(set(names)) == 8
