"""Column contracts for the frames the parsers return. No validation library: every function
returns the columns in this order with tz-aware UTC timestamps, and the tests check it."""

from __future__ import annotations

import pandas as pd

STATION_COLUMNS = [
    "station_id",
    "network",
    "name",
    "lat",
    "lon",
    "elev_m",
    "tz",
    "settles",
    "settlement_source",
    "tier",
    "depth",
    "market_series",
    "nws_office",
    "nws_grid_x",
    "nws_grid_y",
    "active",
]
OBS_COLUMNS = ["station_id", "valid_at", "received_at", "source", "var", "value", "precision"]
RUN_COLUMNS = ["model", "station_id", "run_at", "received_at", "source", "var", "step_h", "values"]
PRODUCT_COLUMNS = ["pil", "issued_at", "office", "received_at", "text"]
SETTLEMENT_COLUMNS = ["station_id", "local_day", "target", "received_at", "value", "source", "final"]
MARKET_COLUMNS = [
    "ticker",
    "as_of",
    "station_id",
    "local_day",
    "bracket_lo",
    "bracket_hi",
    "received_at",
    "yes_bid",
    "yes_ask",
    "last_price",
]
DAILY_COLUMNS = ["local_day", "tmax", "tmin", "n_hours"]
MODEL_DAILY_COLUMNS = ["model", "run_at", "local_day", "tmax", "tmin", "n_hours"]

_TIMES = {"valid_at", "received_at", "run_at", "issued_at", "as_of"}


def empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})


def _frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if len(df) == 0:
        return empty(columns)
    out = df[columns].reset_index(drop=True)
    for c in _TIMES & set(columns):
        out[c] = pd.to_datetime(out[c], utc=True)
    return out


def validate_obs(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(df, OBS_COLUMNS)


def validate_runs(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(df, RUN_COLUMNS)


def validate_products(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(df, PRODUCT_COLUMNS)


def validate_settlements(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(df, SETTLEMENT_COLUMNS)


def validate_markets(df: pd.DataFrame) -> pd.DataFrame:
    return _frame(df, MARKET_COLUMNS)


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0
