"""The NWS gridpoint forecast, the settlement-grade NWS number.

One request per station to `gridpoints/{office}/{x},{y}`. Each variable is a list of
(validTime with an ISO duration, value). Hourly variables are expanded to an hourly array;
the daily `maxTemperature` and `minTemperature` become `tmax` and `tmin` with a 24-hour
stride, one element per local day. `run_at` is the grid's `updateTime`, the true issue
time, so an unchanged grid dedupes on the key.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from camanchaca_demo.store import schemas

POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
GRID_URL = "https://api.weather.gov/gridpoints/{office}/{x},{y}"

HOURLY = {
    "temperature": "t2m",
    "dewpoint": "td2m",
    "skyCover": "cloud",
    "windSpeed": "wspd10",
    "windDirection": "wdir10",
    "probabilityOfPrecipitation": "pop",
    "quantitativePrecipitation": "precip",
    "relativeHumidity": "rh2m",
}
DAILY = {"maxTemperature": "tmax", "minTemperature": "tmin"}

_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")


def resolve_grid(client: httpx.Client, lat: float, lon: float) -> tuple[str, int, int]:
    r = client.get(POINTS_URL.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"))
    r.raise_for_status()
    p = r.json()["properties"]
    return str(p["gridId"]), int(p["gridX"]), int(p["gridY"])


def fetch(client: httpx.Client, office: str, x: int, y: int) -> dict[str, Any]:
    r = client.get(GRID_URL.format(office=office, x=x, y=y))
    r.raise_for_status()
    payload: dict[str, Any] = r.json()
    return payload


def _span(valid_time: str) -> tuple[datetime, int]:
    start_s, dur_s = valid_time.split("/")
    start = datetime.fromisoformat(start_s)
    m = _DUR.match(dur_s)
    if not m:
        return start, 1
    days, hours, _minutes = (int(g) if g else 0 for g in m.groups())
    return start, max(1, days * 24 + hours)


PERIOD_TOTALS = {"precip"}  # a period total is spread evenly over the hours it covers


def _hourly(
    entries: list[dict[str, Any]], run_at: datetime, horizon_h: int, total: bool = False
) -> list[float | None]:
    out: list[float | None] = [None] * horizon_h
    for e in entries:
        start, hours = _span(e["validTime"])
        v = e.get("value")
        if v is not None and total:
            v = float(v) / hours
        for k in range(hours):
            i = int((start + timedelta(hours=k) - run_at).total_seconds() // 3600)
            if 0 <= i < horizon_h:
                out[i] = None if v is None else float(v)
    return out


def _convert(var: str, values: list[float | None], uom: str) -> list[float | None]:
    if var in ("wspd10",) and uom.endswith("km_h-1"):
        return [None if v is None else v / 3.6 for v in values]
    return values


def parse(
    payload: dict[str, Any], station_id: str, tz: str, received_at: datetime, horizon_h: int = 192
) -> pd.DataFrame:
    props = payload["properties"]
    run_at = datetime.fromisoformat(props["updateTime"]).replace(minute=0, second=0, microsecond=0)
    rows: list[dict[str, Any]] = []
    for api_name, var in HOURLY.items():
        block = props.get(api_name) or {}
        entries = block.get("values") or []
        if not entries:
            continue
        values = _convert(
            var,
            _hourly(entries, run_at, horizon_h, total=var in PERIOD_TOTALS),
            str(block.get("uom", "")),
        )
        if any(v is not None for v in values):
            rows.append(
                {
                    "model": "nws",
                    "station_id": station_id,
                    "run_at": run_at,
                    "received_at": received_at,
                    "source": "api.weather.gov",
                    "var": var,
                    "step_h": 0,
                    "values": values,
                }
            )
    zone = ZoneInfo(tz)
    day0 = run_at.astimezone(zone).date()
    for api_name, var in DAILY.items():
        entries = (props.get(api_name) or {}).get("values") or []
        if not entries:
            continue
        by_day: dict[int, float] = {}
        for e in entries:
            start, hours = _span(e["validTime"])
            # A max period runs from morning to evening; a min period runs from the evening
            # before through dawn. The midpoint falls on the day the value belongs to.
            mid = start + timedelta(hours=hours / 2)
            offset = (mid.astimezone(zone).date() - day0).days
            if e.get("value") is not None and offset >= 0:
                by_day[offset] = float(e["value"])
        if not by_day:
            continue
        n = max(by_day) + 1
        values_d: list[float | None] = [by_day.get(i) for i in range(n)]
        rows.append(
            {
                "model": "nws",
                "station_id": station_id,
                "run_at": run_at,
                "received_at": received_at,
                "source": "api.weather.gov",
                "var": var,
                "step_h": 0,
                "values": values_d,
            }
        )
    return schemas.validate_runs(pd.DataFrame(rows, columns=schemas.RUN_COLUMNS))
