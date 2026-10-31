"""Frames the feature functions return. Inputs are the store's long frames."""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

_UTC = pd.DatetimeTZDtype(tz="UTC")

DAILY_COLUMNS = ["local_day", "tmax", "tmin", "n_hours"]
DailyFrame = pa.DataFrameSchema(
    {
        "local_day": pa.Column(object),
        "tmax": pa.Column(float, nullable=True),
        "tmin": pa.Column(float, nullable=True),
        "n_hours": pa.Column(int),
    },
    coerce=True,
    strict=True,
)

MODEL_DAILY_COLUMNS = ["model", "run_at", "local_day", "tmax", "tmin", "n_hours"]
ModelDailyFrame = pa.DataFrameSchema(
    {
        "model": pa.Column(str),
        "run_at": pa.Column(_UTC),
        "local_day": pa.Column(object),
        "tmax": pa.Column(float, nullable=True),
        "tmin": pa.Column(float, nullable=True),
        "n_hours": pa.Column(int),
    },
    coerce=True,
    strict=True,
)


def empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})
