"""What a forecaster is. Every forecaster, public or private, implements this and writes
to the same `predictions` table through `issue()`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class Inputs:
    """Everything a forecaster may look at, all read at `as_of`. Nothing else exists."""

    station_id: str
    tz: str
    as_of: datetime
    obs: pd.DataFrame  # observations, long
    runs: pd.DataFrame  # latest model run per (model, var) received by as_of
    settlements: pd.DataFrame  # settled days known at as_of


@dataclass(frozen=True)
class Prediction:
    quantiles: dict[str, float]  # at least p50; p05 and p95 when the forecaster has a band
    features: dict[str, Any] = field(default_factory=dict)


class Forecaster(Protocol):
    name: str
    version: str

    def predict(self, target: str, local_day: date, inputs: Inputs) -> Prediction | None:
        """A prediction for the target on the day, or None when the inputs do not allow
        one. Never raises on missing data."""
        ...
