"""The stations, from the CSV beside this file. A station is a row; depth and settlement are
columns. `load()` returns plain dicts with typed fields."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

CSV = Path(__file__).with_name("stations.csv")


def load(path: Path = CSV) -> list[dict[str, Any]]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append(
            {
                **r,
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "elev_m": float(r["elev_m"]) if r.get("elev_m") else None,
                "settles": r["settles"].lower() == "true",
                "active": r["active"].lower() == "true",
                "tier": int(r["tier"]),
                "settlement_source": r.get("settlement_source") or None,
                "market_series": r.get("market_series") or None,
            }
        )
    return out


def by_id(path: Path = CSV) -> dict[str, dict[str, Any]]:
    return {s["station_id"]: s for s in load(path)}
