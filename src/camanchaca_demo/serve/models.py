"""Response models. The client's types are generated from these, so a change here is a
change there, and the build fails on a stale copy."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Station(BaseModel):
    station_id: str
    name: str
    lat: float
    lon: float
    tz: str
    depth: str
    settles: bool
    market_series: str | None = None
    nws_office: str | None = None


class Series(BaseModel):
    """Columnar hourly values; `t` is epoch seconds."""

    t: list[int]
    values: list[float | None]


class ModelSeries(BaseModel):
    model: str
    run_at: datetime
    t: list[int]
    values: list[float | None]


class DailySeries(BaseModel):
    model: str
    run_at: datetime
    days: list[date]
    tmax: list[float | None]
    tmin: list[float | None]


class Settlement(BaseModel):
    local_day: date
    target: str
    value: float
    final: bool
    received_at: datetime


class Bracket(BaseModel):
    ticker: str
    local_day: date
    lo: float | None
    hi: float | None
    yes_bid: float | None
    yes_ask: float | None
    last_price: float | None
    as_of: datetime


class Discussion(BaseModel):
    office: str
    issued_at: datetime
    text: str


class ProfileLevel(BaseModel):
    level_hpa: int
    t: float | None
    z_m: float | None
    wspd_ms: float | None
    wdir_deg: float | None
    rh: float | None


class Profile(BaseModel):
    model: str
    run_at: datetime
    valid_at: datetime
    levels: list[ProfileLevel]


class PredictionRow(BaseModel):
    forecaster: str
    target: str
    local_day: date
    as_of: datetime
    lead_h: float
    p50: float
    p05: float | None = None
    p95: float | None = None


class StationPage(BaseModel):
    station: Station
    as_of: datetime
    unit: str = Field(description="Temperature unit of every value on the page: F")
    observed: dict[str, Series]
    models: list[ModelSeries]
    nws_daily: DailySeries | None
    predictions: list[PredictionRow]
    settlements: list[Settlement]
    brackets: list[Bracket]
    discussion: Discussion | None
    profiles: list[Profile]


class FeedStatus(BaseModel):
    feed: str
    last_success: datetime | None
    last_error: str | None
    rows: int
    updated_at: datetime | None


class Health(BaseModel):
    ok: bool
    db: bool
    feeds: list[FeedStatus]


class JournalEntry(BaseModel):
    station_id: str
    local_day: date
    created_at: datetime
    uncertainty: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] = []
    text: str = ""


class JournalNew(BaseModel):
    station_id: str
    local_day: date
    uncertainty: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] = []
    text: str = Field(default="", max_length=4000)
