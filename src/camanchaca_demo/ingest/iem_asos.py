"""Hourly METAR observations from the IEM ASOS archive, several stations per request.

`report_type=3` keeps routine hourly reports only. Values are stored in SI: Celsius,
m/s, metres, millimetres, hectopascals, cloud cover in percent.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import httpx
import pandas as pd

from camanchaca_demo.ingest.feed import f_to_c
from camanchaca_demo.store import schemas

API_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
FIELDS = [
    "tmpf",
    "dwpf",
    "relh",
    "sknt",
    "gust",
    "drct",
    "mslp",
    "alti",
    "vsby",
    "p01i",
    "skyc1",
    "skyc2",
    "skyc3",
    "skyc4",
]
COVER = {"CLR": 0.0, "SKC": 0.0, "FEW": 25.0, "SCT": 50.0, "BKN": 75.0, "OVC": 100.0, "VV": 100.0}


def iem_id(station_id: str) -> str:
    """`asos:KLAX` -> `LAX`. IEM drops the K prefix for CONUS ASOS sites."""
    code = station_id.split(":", 1)[1]
    return code[1:] if len(code) == 4 and code.startswith("K") else code


def fetch(client: httpx.Client, station_ids: list[str], start: datetime, end: datetime) -> str:
    params: list[tuple[str, Any]] = [("station", iem_id(s)) for s in station_ids]
    params += [
        ("data", ",".join(FIELDS)),
        ("year1", start.year),
        ("month1", start.month),
        ("day1", start.day),
        ("hour1", start.hour),
        ("year2", end.year),
        ("month2", end.month),
        ("day2", end.day),
        ("hour2", end.hour),
        ("tz", "UTC"),
        ("format", "onlycomma"),
        ("latlon", "no"),
        ("missing", "M"),
        ("trace", "T"),
        ("report_type", 3),
    ]
    r = client.get(API_URL, params=params)
    r.raise_for_status()
    return r.text


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace({"M": None, "T": "0.005"}), errors="coerce")


def parse(csv_text: str, received_at: datetime, id_map: dict[str, str]) -> pd.DataFrame:
    """`id_map` goes from the IEM id (`LAX`) back to the station id (`asos:KLAX`)."""
    text = csv_text.strip()
    if not text or text.startswith("#") and "\n" not in text:
        return schemas.empty(schemas.OBS_COLUMNS)
    df = pd.read_csv(io.StringIO(text), comment="#", dtype=str)
    if df.empty or "valid" not in df.columns:
        return schemas.empty(schemas.OBS_COLUMNS)
    df["valid_at"] = pd.to_datetime(df["valid"], utc=True, errors="coerce")
    df = df.dropna(subset=["valid_at"])
    df["station_id"] = df["station"].map(id_map)
    df = df.dropna(subset=["station_id"])

    cols: dict[str, tuple[pd.Series, float | None]] = {}
    cols["t2m"] = (_num(df["tmpf"]).map(f_to_c), 0.1)
    cols["td2m"] = (_num(df["dwpf"]).map(f_to_c), 0.1)
    cols["rh2m"] = (_num(df["relh"]), None)
    cols["wspd10"] = (_num(df["sknt"]) * 0.514444, None)
    cols["gust10"] = (_num(df["gust"]) * 0.514444, None)
    cols["wdir10"] = (_num(df["drct"]), None)
    cols["pres"] = (_num(df["mslp"]), None)  # sea-level pressure, when reported
    cols["alti"] = (_num(df["alti"]) * 33.8639, None)  # altimeter setting, hPa
    cols["vis"] = (_num(df["vsby"]) * 1609.344, None)
    cols["precip"] = (_num(df["p01i"]) * 25.4, None)
    sky = pd.concat([df[c].map(COVER) for c in ("skyc1", "skyc2", "skyc3", "skyc4")], axis=1).max(
        axis=1
    )
    cols["cloud"] = (sky, None)

    frames = []
    for var, (series, precision) in cols.items():
        part = pd.DataFrame(
            {
                "station_id": df["station_id"],
                "valid_at": df["valid_at"],
                "received_at": received_at,
                "source": "iem-asos",
                "var": var,
                "value": series.astype(float),
                "precision": pd.Series(precision, index=df.index, dtype="float64"),
            }
        )
        part = part.dropna(subset=["value"])
        if len(part):
            frames.append(part)
    out = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=schemas.OBS_COLUMNS)
    )
    out = out.drop_duplicates(["station_id", "valid_at", "var"], keep="last").reset_index(drop=True)
    return schemas.validate_obs(out[schemas.OBS_COLUMNS])
