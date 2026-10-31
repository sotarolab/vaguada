"""The baselines every scorecard column is measured against.

RawModel: a model's own daily extreme for the day, from its latest run. The NWS carries
daily values directly; the point models are reduced from their hourly arrays.
Persistence: yesterday's settled value, or yesterday's observed extreme when the climate
report has not arrived.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from camanchaca_demo import localday
from camanchaca_demo.features.daily import daily_extremes, model_daily_extremes, running_extreme
from camanchaca_demo.forecast.base import Forecaster, Inputs, Prediction

DAILY_MODELS = {"nws"}  # carry tmax/tmin series of their own; never reduced from hourly


class RawModel:
    version = "1"

    def __init__(self, model: str) -> None:
        self.model = model
        self.name = f"raw_{model}"
        self._cache: tuple[int, pd.DataFrame] | None = None

    def _daily(self, inputs: Inputs, runs: pd.DataFrame) -> pd.DataFrame:
        """The model's daily frame, computed once per Inputs and reused across targets and days."""
        if self._cache is None or self._cache[0] != id(inputs):
            self._cache = (id(inputs), model_daily_extremes(runs, inputs.tz))
        return self._cache[1]

    def predict(self, target: str, local_day: date, inputs: Inputs) -> Prediction | None:
        runs = inputs.runs[inputs.runs["model"] == self.model]
        if runs.empty:
            return None
        daily = runs[runs["var"] == target]
        if not daily.empty:
            # A daily series: element i is the value for the run's local day plus i.
            r = daily.iloc[0]
            day0 = localday.local_day_of(r["run_at"].to_pydatetime(), inputs.tz)
            i = (local_day - day0).days
            values = list(r["values"])
            if 0 <= i < len(values) and values[i] is not None:
                return Prediction({"p50": float(values[i])}, {"run_at": r["run_at"].isoformat()})
            return None
        if self.model in DAILY_MODELS:
            return None
        md = self._daily(inputs, runs)
        hit = md[md["local_day"] == local_day]
        if hit.empty:
            return None
        row = hit.iloc[0]
        value = row[target]
        if value is None or value != value:  # NaN
            return None
        return Prediction(
            {"p50": float(value)},
            {"run_at": row["run_at"].isoformat(), "n_hours": int(row["n_hours"])},
        )


class Persistence:
    name = "persistence"
    version = "1"

    def predict(self, target: str, local_day: date, inputs: Inputs) -> Prediction | None:
        yesterday = local_day - timedelta(days=1)
        s = inputs.settlements
        hit = s[(s["local_day"] == yesterday) & (s["target"] == target)] if len(s) else s
        if len(hit):
            return Prediction({"p50": float(hit.iloc[0]["value"])}, {"source": "settled"})
        d = daily_extremes(inputs.obs, inputs.tz)
        hit = d[d["local_day"] == yesterday]
        if hit.empty or hit.iloc[0]["n_hours"] < 18:
            return None
        return Prediction({"p50": float(hit.iloc[0][target])}, {"source": "observed"})


class RunningExtreme:
    """What has been observed so far today: the floor of the high and the ceiling of the
    low. Only meaningful on the day itself; None before it starts and for other days."""

    name = "observed_so_far"
    version = "1"

    def predict(self, target: str, local_day: date, inputs: Inputs) -> Prediction | None:
        if localday.local_day_of(inputs.as_of, inputs.tz) != local_day:
            return None
        hi, lo, n = running_extreme(inputs.obs, local_day, inputs.tz, inputs.as_of)
        value = hi if target == "tmax" else lo
        if value is None:
            return None
        return Prediction({"p50": float(value)}, {"n_hours": n})


def default_forecasters() -> list[Forecaster]:
    models = ("gfs", "hrrr", "nbm", "ifs", "icon", "nws")
    out: list[Forecaster] = [RawModel(m) for m in models]
    out.extend([Persistence(), RunningExtreme()])
    return out
