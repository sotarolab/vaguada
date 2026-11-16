"""Point forecasts from Open-Meteo, five models in one request per station.

Open-Meteo does not say which cycle it served, so `run_at` is the hour of the fetch and
the array starts at that hour (decision 0004). Surface variables for every station;
pressure-level profiles for deep stations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from vaguada.parsers import schemas

API_URL = "https://api.open-meteo.com/v1/forecast"
MODELS = ["gfs_global", "gfs_hrrr", "ncep_nbm_conus", "ecmwf_ifs025", "icon_global"]
SHORT = {
    "gfs_global": "gfs",
    "gfs_hrrr": "hrrr",
    "ncep_nbm_conus": "nbm",
    "ecmwf_ifs025": "ifs",
    "icon_global": "icon",
}

SURFACE = {
    "temperature_2m": "t2m",
    "dew_point_2m": "td2m",
    "cloud_cover": "cloud",
    "precipitation": "precip",
    "visibility": "vis",
    "wind_speed_10m": "wspd10",
    "wind_direction_10m": "wdir10",
}
LEVELS = (1000, 925, 850, 700, 500)
PROFILE = {
    "temperature": "t",
    "geopotential_height": "z",
    "wind_speed": "wspd",
    "wind_direction": "wdir",
    "relative_humidity": "rh",
}


def variables(deep: bool) -> dict[str, str]:
    """API hourly name -> stored var name."""
    out = dict(SURFACE)
    if deep:
        out["boundary_layer_height"] = "blh"
        for p in LEVELS:
            for api, var in PROFILE.items():
                out[f"{api}_{p}hPa"] = f"{var}_{p}"
    return out


def url(lat: float, lon: float, deep: bool, days: int = 7) -> str:
    q = urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(variables(deep)),
            "models": ",".join(MODELS),
            "forecast_days": days,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }
    )
    return f"{API_URL}?{q}"


def parse(
    payload: dict[str, Any], station_id: str, run_at: datetime, received_at: datetime, deep: bool
) -> pd.DataFrame:
    """One row per (model, var). With several models in one request Open-Meteo suffixes
    every hourly key with the model name. The array is sliced to start at `run_at`."""
    hourly = payload.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []), utc=True)
    if len(times) == 0:
        return schemas.empty(schemas.RUN_COLUMNS)
    start = int((times >= run_at).argmax()) if (times >= run_at).any() else len(times)
    rows: list[dict[str, Any]] = []
    for api_name, var in variables(deep).items():
        for model in MODELS:
            series = hourly.get(f"{api_name}_{model}")
            if series is None:
                continue
            values = [None if v is None else float(v) for v in series[start:]]
            if not any(v is not None for v in values):
                continue
            rows.append(
                {
                    "model": SHORT[model],
                    "station_id": station_id,
                    "run_at": run_at,
                    "received_at": received_at,
                    "source": "open-meteo",
                    "var": var,
                    "step_h": 0,
                    "values": values,
                }
            )
    return schemas.validate_runs(pd.DataFrame(rows, columns=schemas.RUN_COLUMNS))
