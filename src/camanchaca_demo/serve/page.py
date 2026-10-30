"""Assemble a station page from store reads. Reads only; the unit conversion is the only
arithmetic, and it lives here so the client draws what it is given."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from camanchaca_demo import localday
from camanchaca_demo.serve import models as m
from camanchaca_demo.store.read import Store

TEMPERATURE_VARS = {"t2m", "td2m", "tmax", "tmin"}
PROFILE_LEVELS = (1000, 925, 850, 700, 500)


def c_to_f(c: float | None) -> float | None:
    return None if c is None or pd.isna(c) else round(c * 9.0 / 5.0 + 32.0, 2)


def _conv(var: str, values: list[Any]) -> list[float | None]:
    if var in TEMPERATURE_VARS:
        return [c_to_f(v) for v in values]
    return [None if v is None or pd.isna(v) else float(v) for v in values]


def _epoch(ts: Any) -> int:
    return int(pd.Timestamp(ts).timestamp())


def station_row(stations: pd.DataFrame, station_id: str) -> pd.Series | None:
    hit = stations[stations["station_id"] == station_id]
    return None if hit.empty else hit.iloc[0]


def to_station(row: pd.Series) -> m.Station:
    def opt(key: str) -> str | None:
        v = row.get(key)
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    return m.Station(
        station_id=str(row["station_id"]),
        name=str(row["name"]),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        tz=str(row["tz"]),
        depth=str(row["depth"]),
        settles=bool(row["settles"]),
        market_series=opt("market_series"),
        nws_office=opt("nws_office"),
    )


def observed_series(obs: pd.DataFrame, var: str) -> m.Series:
    sel = obs[obs["var"] == var].sort_values("valid_at")
    return m.Series(
        t=[_epoch(t) for t in sel["valid_at"]], values=_conv(var, sel["value"].tolist())
    )


def model_series(runs: pd.DataFrame, var: str, hours_ahead: int) -> list[m.ModelSeries]:
    out: list[m.ModelSeries] = []
    for _, r in runs[runs["var"] == var].sort_values("model").iterrows():
        run_at = pd.Timestamp(r["run_at"])
        values = list(r["values"])[:hours_ahead]
        t = [_epoch(run_at + timedelta(hours=int(r["step_h"]) + i)) for i in range(len(values))]
        out.append(
            m.ModelSeries(
                model=str(r["model"]), run_at=run_at.to_pydatetime(), t=t, values=_conv(var, values)
            )
        )
    return out


def nws_daily(runs: pd.DataFrame, tz: str) -> m.DailySeries | None:
    nws = runs[(runs["model"] == "nws") & (runs["var"].isin(["tmax", "tmin"]))]
    if nws.empty:
        return None
    by_var = {str(r["var"]): r for _, r in nws.iterrows()}
    ref = next(iter(by_var.values()))
    run_at = pd.Timestamp(ref["run_at"])
    day0 = localday.local_day_of(run_at.to_pydatetime(), tz)
    n = max(len(r["values"]) for r in by_var.values())
    days = [day0 + timedelta(days=i) for i in range(n)]

    def padded(var: str) -> list[float | None]:
        vals = list(by_var[var]["values"]) if var in by_var else []
        return _conv(var, vals + [None] * (n - len(vals)))

    return m.DailySeries(
        model="nws",
        run_at=run_at.to_pydatetime(),
        days=days,
        tmax=padded("tmax"),
        tmin=padded("tmin"),
    )


def _at(by_var: dict[str, list[Any]], idx: int, var: str) -> float | None:
    vals = by_var.get(var)
    if not vals or idx >= len(vals) or vals[idx] is None:
        return None
    return float(vals[idx])


def profiles(runs: pd.DataFrame, as_of: datetime) -> list[m.Profile]:
    out: list[m.Profile] = []
    for model, grp in runs[runs["var"].str.match(r"^(t|z|wspd|wdir|rh)_\d+$")].groupby("model"):
        run_at = pd.Timestamp(grp["run_at"].iloc[0])
        idx = max(0, int((as_of - run_at.to_pydatetime()).total_seconds() // 3600))
        by_var = {str(r["var"]): list(r["values"]) for _, r in grp.iterrows()}

        levels = [
            m.ProfileLevel(
                level_hpa=p,
                t=c_to_f(_at(by_var, idx, f"t_{p}")),
                z_m=_at(by_var, idx, f"z_{p}"),
                wspd_ms=_at(by_var, idx, f"wspd_{p}"),
                wdir_deg=_at(by_var, idx, f"wdir_{p}"),
                rh=_at(by_var, idx, f"rh_{p}"),
            )
            for p in PROFILE_LEVELS
        ]
        if any(level.t is not None for level in levels):
            out.append(
                m.Profile(
                    model=str(model),
                    run_at=run_at.to_pydatetime(),
                    valid_at=(run_at + timedelta(hours=idx)).to_pydatetime(),
                    levels=levels,
                )
            )
    return out


def build_page(
    store: Store,
    station_id: str,
    as_of: datetime | None = None,
    hours_back: int = 48,
    hours_ahead: int = 120,
) -> m.StationPage | None:
    at = (as_of or datetime.now(UTC)).astimezone(UTC)
    row = station_row(store.stations(), station_id)
    if row is None:
        return None
    tz = str(row["tz"])
    obs = store.observations(station_id, at - timedelta(hours=hours_back), at)
    runs = store.latest_runs(station_id, at)
    today = localday.local_day_of(at, tz)
    settle = store.settlements(station_id, at)
    brackets: list[m.Bracket] = []
    for day in (today, today + timedelta(days=1)):
        mk = store.markets(station_id, day, at)
        for _, r in mk.sort_values(["bracket_lo", "bracket_hi"], na_position="first").iterrows():
            brackets.append(
                m.Bracket(
                    ticker=str(r["ticker"]),
                    local_day=day,
                    lo=None if pd.isna(r["bracket_lo"]) else float(r["bracket_lo"]),
                    hi=None if pd.isna(r["bracket_hi"]) else float(r["bracket_hi"]),
                    yes_bid=None if pd.isna(r["yes_bid"]) else float(r["yes_bid"]),
                    yes_ask=None if pd.isna(r["yes_ask"]) else float(r["yes_ask"]),
                    last_price=None if pd.isna(r["last_price"]) else float(r["last_price"]),
                    as_of=pd.Timestamp(r["as_of"]).to_pydatetime(),
                )
            )
    office = row.get("nws_office")
    discussion = None
    if office is not None and not pd.isna(office):
        prod = store.latest_product(f"AFD{office}", at)
        if prod is not None:
            discussion = m.Discussion(
                office=str(office), issued_at=prod["issued_at"], text=prod["text"]
            )
    return m.StationPage(
        station=to_station(row),
        as_of=at,
        unit="F",
        observed={v: observed_series(obs, v) for v in ("t2m", "td2m", "wspd10", "cloud")},
        models=model_series(runs, "t2m", hours_ahead),
        nws_daily=nws_daily(runs, tz),
        settlements=[
            m.Settlement(
                local_day=r["local_day"],
                target=str(r["target"]),
                value=c_to_f(float(r["value"])) or 0.0,
                final=bool(r["final"]),
                received_at=pd.Timestamp(r["received_at"]).to_pydatetime(),
            )
            for _, r in settle.sort_values(["local_day", "target"], ascending=[False, True])
            .head(30)
            .iterrows()
        ],
        brackets=brackets,
        discussion=discussion,
        profiles=profiles(runs, at),
    )
