"""Daily extremes from hourly series. Pure functions: a frame in, a frame out.

Every function takes tz-aware UTC timestamps and the station's time zone, and groups by the
station's local calendar day through `localday`, so a DST day with 23 or 25 hours is one day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from camanchaca_demo import localday
from camanchaca_demo.features import schemas


def daily_extremes(obs: pd.DataFrame, tz: str, var: str = "t2m") -> pd.DataFrame:
    """The observed high and low of each local day present in `obs`, with the number of
    hourly values behind them. A day with no values has no row."""
    sel = obs[obs["var"] == var]
    if sel.empty:
        return schemas.empty(schemas.DAILY_COLUMNS)
    days = sel["valid_at"].map(lambda t: localday.local_day_of(t.to_pydatetime(), tz))
    g = sel.assign(local_day=days).groupby("local_day")["value"]
    out = pd.DataFrame(
        {"tmax": g.max(), "tmin": g.min(), "n_hours": g.count().astype(int)}
    ).reset_index()
    return schemas.DailyFrame.validate(out[schemas.DAILY_COLUMNS])


def running_extreme(
    obs: pd.DataFrame, local_day: date, tz: str, as_of: datetime, var: str = "t2m"
) -> tuple[float | None, float | None, int]:
    """The high and low observed so far on `local_day`, using values valid at or before
    `as_of`. Before the day starts there are none: (None, None, 0)."""
    start, end = localday.day_bounds(local_day, tz)
    sel = obs[(obs["var"] == var) & (obs["valid_at"] >= start) & (obs["valid_at"] < end)]
    sel = sel[sel["valid_at"] <= as_of]
    if sel.empty:
        return None, None, 0
    return float(sel["value"].max()), float(sel["value"].min()), int(len(sel))


def model_daily_extremes(runs: pd.DataFrame, tz: str, var: str = "t2m") -> pd.DataFrame:
    """Each model run's high and low per local day, from its hourly array. Element i of a
    run is valid at `run_at + (step_h + i)` hours. A day covered by fewer than `n_hours`
    hours is still reported; the count says how complete it is."""
    rows = []
    for _, r in runs[runs["var"] == var].iterrows():
        run_at = pd.Timestamp(r["run_at"]).to_pydatetime()
        step = int(r["step_h"])
        values = list(r["values"])
        times = [run_at + timedelta(hours=step + i) for i in range(len(values))]
        frame = pd.DataFrame({"t": times, "v": values}).dropna(subset=["v"])
        if frame.empty:
            continue
        frame["local_day"] = frame["t"].map(lambda t: localday.local_day_of(t, tz))
        g = frame.groupby("local_day")["v"]
        for day, hi, lo, n in zip(g.max().index, g.max(), g.min(), g.count(), strict=True):
            rows.append(
                {
                    "model": r["model"],
                    "run_at": r["run_at"],
                    "local_day": day,
                    "tmax": float(hi),
                    "tmin": float(lo),
                    "n_hours": int(n),
                }
            )
    if not rows:
        return schemas.empty(schemas.MODEL_DAILY_COLUMNS)
    return schemas.ModelDailyFrame.validate(pd.DataFrame(rows, columns=schemas.MODEL_DAILY_COLUMNS))
