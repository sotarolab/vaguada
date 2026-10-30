"""Frame schemas at every boundary that passes a DataFrame.

Long frames throughout. Timestamps are tz-aware UTC. `received_at` is set by the caller
that fetched the data, never by a parser, so a parser can be tested on a saved response.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

_UTC = pd.DatetimeTZDtype(tz="UTC")

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
ObsFrame = pa.DataFrameSchema(
    {
        "station_id": pa.Column(str),
        "valid_at": pa.Column(_UTC),
        "received_at": pa.Column(_UTC),
        "source": pa.Column(str),
        "var": pa.Column(str),
        "value": pa.Column(float, nullable=False),
        "precision": pa.Column(float, nullable=True),
    },
    coerce=True,
    strict=True,
)

RUN_COLUMNS = ["model", "station_id", "run_at", "received_at", "source", "var", "step_h", "values"]
RunFrame = pa.DataFrameSchema(
    {
        "model": pa.Column(str),
        "station_id": pa.Column(str),
        "run_at": pa.Column(_UTC),
        "received_at": pa.Column(_UTC),
        "source": pa.Column(str),
        "var": pa.Column(str),
        "step_h": pa.Column(int),
        "values": pa.Column(object),  # list[float | None], one element per hour
    },
    coerce=True,
    strict=True,
)

PRODUCT_COLUMNS = ["pil", "issued_at", "office", "received_at", "text"]
ProductFrame = pa.DataFrameSchema(
    {
        "pil": pa.Column(str),
        "issued_at": pa.Column(_UTC),
        "office": pa.Column(str),
        "received_at": pa.Column(_UTC),
        "text": pa.Column(str),
    },
    coerce=True,
    strict=True,
)

SETTLEMENT_COLUMNS = [
    "station_id",
    "local_day",
    "target",
    "received_at",
    "value",
    "source",
    "final",
]
SettlementFrame = pa.DataFrameSchema(
    {
        "station_id": pa.Column(str),
        "local_day": pa.Column(object),  # datetime.date
        "target": pa.Column(str, pa.Check.isin(["tmax", "tmin"])),
        "received_at": pa.Column(_UTC),
        "value": pa.Column(float),
        "source": pa.Column(str),
        "final": pa.Column(bool),
    },
    coerce=True,
    strict=True,
)

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
MarketFrame = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str),
        "as_of": pa.Column(_UTC),
        "station_id": pa.Column(str),
        "local_day": pa.Column(object),
        "bracket_lo": pa.Column(float, nullable=True),
        "bracket_hi": pa.Column(float, nullable=True),
        "received_at": pa.Column(_UTC),
        "yes_bid": pa.Column(float, nullable=True),
        "yes_ask": pa.Column(float, nullable=True),
        "last_price": pa.Column(float, nullable=True),
    },
    coerce=True,
    strict=True,
)


def empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})


def validate_obs(df: pd.DataFrame) -> pd.DataFrame:
    return ObsFrame.validate(df) if len(df) else empty(OBS_COLUMNS)


def validate_runs(df: pd.DataFrame) -> pd.DataFrame:
    return RunFrame.validate(df) if len(df) else empty(RUN_COLUMNS)


def validate_products(df: pd.DataFrame) -> pd.DataFrame:
    return ProductFrame.validate(df) if len(df) else empty(PRODUCT_COLUMNS)


def validate_settlements(df: pd.DataFrame) -> pd.DataFrame:
    return SettlementFrame.validate(df) if len(df) else empty(SETTLEMENT_COLUMNS)


def validate_markets(df: pd.DataFrame) -> pd.DataFrame:
    return MarketFrame.validate(df) if len(df) else empty(MARKET_COLUMNS)
