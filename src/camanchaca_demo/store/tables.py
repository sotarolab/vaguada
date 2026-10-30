"""Table definitions, SQLAlchemy Core. One function builds them for a schema name so the
migration, the service and the tests share one source of truth.

Append-only except `stations` (edited by hand), `heartbeat`, and the derived `scores` and
`scorecard`. A correction is a new row with a later `received_at`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL


@dataclass(frozen=True)
class Tables:
    metadata: MetaData
    stations: Table
    observations: Table
    model_runs: Table
    products: Table
    settlements: Table
    markets: Table
    predictions: Table
    scores: Table
    scorecard: Table
    heartbeat: Table


def build_tables(schema: str) -> Tables:
    md = MetaData(schema=schema)
    ts = DateTime(timezone=True)

    stations = Table(
        "stations",
        md,
        Column("station_id", String, primary_key=True),
        Column("network", String, nullable=False),
        Column("name", String, nullable=False),
        Column("lat", Float, nullable=False),
        Column("lon", Float, nullable=False),
        Column("elev_m", Float),
        Column("tz", String, nullable=False),
        Column("settles", Boolean, nullable=False),
        Column("settlement_source", String),
        Column("tier", SmallInteger, nullable=False, default=1),
        Column("depth", String, nullable=False, default="slot"),
        Column("market_series", String),
        Column("nws_office", String),
        Column("nws_grid_x", Integer),
        Column("nws_grid_y", Integer),
        Column("active", Boolean, nullable=False, default=True),
    )

    observations = Table(
        "observations",
        md,
        Column("station_id", String, primary_key=True),
        Column("valid_at", ts, primary_key=True),
        Column("source", String, primary_key=True),
        Column("var", String, primary_key=True),
        Column("received_at", ts, primary_key=True),
        Column("value", REAL, nullable=False),
        Column("precision", REAL),
        Index("ix_observations_station_valid", "station_id", "valid_at"),
    )

    model_runs = Table(
        "model_runs",
        md,
        Column("model", String, primary_key=True),
        Column("station_id", String, primary_key=True),
        Column("run_at", ts, primary_key=True),
        Column("var", String, primary_key=True),
        Column("received_at", ts, nullable=False),
        Column("source", String, nullable=False),
        Column("step_h", SmallInteger, nullable=False, default=0),
        Column("values", ARRAY(REAL), nullable=False),
        Index("ix_model_runs_station_run", "station_id", "run_at", "model"),
    )

    products = Table(
        "products",
        md,
        Column("pil", String, primary_key=True),
        Column("issued_at", ts, primary_key=True),
        Column("office", String, nullable=False),
        Column("received_at", ts, nullable=False),
        Column("text", Text, nullable=False),
    )

    settlements = Table(
        "settlements",
        md,
        Column("station_id", String, primary_key=True),
        Column("local_day", Date, primary_key=True),
        Column("target", String, primary_key=True),
        Column("received_at", ts, primary_key=True),
        Column("value", REAL, nullable=False),
        Column("source", String, nullable=False),
        Column("final", Boolean, nullable=False, default=False),
    )

    markets = Table(
        "markets",
        md,
        Column("ticker", String, primary_key=True),
        Column("as_of", ts, primary_key=True),
        Column("station_id", String, nullable=False),
        Column("local_day", Date, nullable=False),
        Column("bracket_lo", REAL),
        Column("bracket_hi", REAL),
        Column("received_at", ts, nullable=False),
        Column("yes_bid", REAL),
        Column("yes_ask", REAL),
        Column("last_price", REAL),
        Index("ix_markets_station_day", "station_id", "local_day"),
    )

    predictions = Table(
        "predictions",
        md,
        Column("forecaster", String, primary_key=True),
        Column("version", String, primary_key=True),
        Column("station_id", String, primary_key=True),
        Column("target", String, primary_key=True),
        Column("local_day", Date, primary_key=True),
        Column("as_of", ts, primary_key=True),
        Column("received_at", ts, nullable=False),
        Column("quantiles", JSONB, nullable=False),
        Column("features", JSONB),
        Index("ix_predictions_station_target_day", "station_id", "target", "local_day"),
    )

    scores = Table(
        "scores",
        md,
        Column("forecaster", String, primary_key=True),
        Column("version", String, primary_key=True),
        Column("station_id", String, primary_key=True),
        Column("target", String, primary_key=True),
        Column("local_day", Date, primary_key=True),
        Column("lead_h", REAL, primary_key=True),
        Column("mae", REAL),
        Column("crps", REAL),
        Column("brier", JSONB),
        Column("bracket_brier", REAL),
        Column("covered_90", Boolean),
        Column("computed_at", ts, nullable=False),
        Index("ix_scores_station_target_day", "station_id", "target", "local_day"),
    )

    scorecard = Table(
        "scorecard",
        md,
        Column("forecaster", String, primary_key=True),
        Column("version", String, primary_key=True),
        Column("target", String, primary_key=True),
        Column("lead_h", REAL, primary_key=True),
        Column("period", String, primary_key=True),
        Column("n", Integer, nullable=False),
        Column("mae", REAL),
        Column("bias", REAL),
        Column("built_at", ts, nullable=False),
    )

    heartbeat = Table(
        "heartbeat",
        md,
        Column("feed", String, primary_key=True),
        Column("last_success", ts),
        Column("last_error", Text),
        Column("rows", Integer, nullable=False, default=0),
        Column("updated_at", ts, nullable=False),
    )

    return Tables(
        metadata=md,
        stations=stations,
        observations=observations,
        model_runs=model_runs,
        products=products,
        settlements=settlements,
        markets=markets,
        predictions=predictions,
        scores=scores,
        scorecard=scorecard,
        heartbeat=heartbeat,
    )
