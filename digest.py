"""Digest the archive, the settlements and the scores into the static site's data:
data/site/index.json (stations, record, scorecards) and data/site/stations/<station>.json
(observed hours, every model's latest run, the NWS series, the settlements, the latest model
forecasts, the discussion). The page at app/ draws these files from the data branch and
computes nothing; temperatures here are Fahrenheit.

Run: python digest.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from score import BUCKETS, bucket, floor_hour, stem_time
from vaguada import daily, localday, stations
from vaguada.parsers import afd, iem_asos, nws, open_meteo
from vaguada.parsers.schemas import c_to_f

OBS_HOURS = 120
MIN_PAIRS = 20
MODELS = ("nbm", "hrrr", "gfs", "ifs", "icon")


def newest(d: Path, suffix: str = ".gz") -> Path | None:
    files = sorted(d.glob(f"*{suffix}")) if d.is_dir() else []
    return files[-1] if files else None


def load_gz(p: Path) -> bytes:
    return gzip.decompress(p.read_bytes())


def observed(out: Path, st: dict[str, Any], now: datetime) -> list[list[object]]:
    """[[epoch seconds, temp_f], ...] for the last OBS_HOURS, from the archived observation files."""
    sid = st["station_id"]
    frames = []
    d = out / "asos" / sid
    for p in sorted(d.glob("*.gz"))[-OBS_HOURS:] if d.is_dir() else []:
        if stem_time(p) < now - timedelta(hours=OBS_HOURS + 3):
            continue
        frames.append(iem_asos.parse(load_gz(p).decode(), stem_time(p), {iem_asos.iem_id(sid): sid}))
    if not frames:
        return []
    obs = pd.concat(frames, ignore_index=True)
    obs = obs[obs["var"] == "t2m"].drop_duplicates(["valid_at"], keep="last").sort_values("valid_at")
    obs = obs[obs["valid_at"] >= now - timedelta(hours=OBS_HOURS)]
    return [
        [int(t.timestamp()), round(c_to_f(v), 1)] for t, v in zip(obs["valid_at"], obs["value"], strict=True)
    ]


def models(out: Path, st: dict[str, Any]) -> dict[str, dict[str, object]]:
    """Each model's latest run: hourly temperature and its daily extremes."""
    sid, tz = st["station_id"], st["tz"]
    p = newest(out / "openmeteo" / sid)
    if p is None:
        return {}
    fetched = floor_hour(stem_time(p))
    runs = open_meteo.parse(json.loads(load_gz(p)), sid, fetched, fetched, deep=True)
    dailies = daily.model_daily_extremes(runs, tz)
    out_: dict[str, dict[str, object]] = {}
    for _, r in runs[runs["var"] == "t2m"].iterrows():
        t0 = int(pd.Timestamp(r["run_at"]).timestamp())
        values = [None if v is None else round(c_to_f(v), 1) for v in r["values"]]
        md = dailies[dailies["model"] == r["model"]]
        out_[str(r["model"])] = {
            "issued": p.stem,
            "t": [t0 + 3600 * i for i in range(len(values))],
            "temp_f": values,
            "days": [d.isoformat() for d in md["local_day"]],
            "tmax_f": [round(c_to_f(v)) for v in md["tmax"]],
            "tmin_f": [round(c_to_f(v)) for v in md["tmin"]],
        }
    return out_


def nws_series(out: Path, st: dict[str, Any]) -> dict[str, object] | None:
    sid, tz = st["station_id"], st["tz"]
    p = newest(out / "nws_grid" / sid)
    if p is None:
        return None
    runs = nws.parse(json.loads(load_gz(p)), sid, tz, stem_time(p))
    by = {str(r["var"]): r for _, r in runs.iterrows()}
    if "t2m" not in by:
        return None
    t2m = by["t2m"]
    t0 = int(pd.Timestamp(t2m["run_at"]).timestamp())
    day0 = localday.local_day_of(t2m["run_at"].to_pydatetime(), tz)
    n = (
        max(len(by[v]["values"]) for v in ("tmax", "tmin") if v in by)
        if ("tmax" in by or "tmin" in by)
        else 0
    )
    return {
        "issued": pd.Timestamp(t2m["run_at"]).strftime("%Y-%m-%dT%H:%MZ"),
        "t": [t0 + 3600 * i for i in range(len(t2m["values"]))],
        "temp_f": [None if v is None else round(c_to_f(v), 1) for v in t2m["values"]],
        "days": [(day0 + timedelta(days=i)).isoformat() for i in range(n)],
        "tmax_f": [
            None
            if i >= len(by["tmax"]["values"]) or by["tmax"]["values"][i] is None
            else round(c_to_f(by["tmax"]["values"][i]))
            for i in range(n)
        ]
        if "tmax" in by
        else [],
        "tmin_f": [
            None
            if i >= len(by["tmin"]["values"]) or by["tmin"]["values"][i] is None
            else round(c_to_f(by["tmin"]["values"][i]))
            for i in range(n)
        ]
        if "tmin" in by
        else [],
    }


def settlements(out: Path, sid: str, days: int = 30) -> list[dict[str, object]]:
    path = out / "settlements" / f"{sid}.csv"
    if not path.exists():
        return []
    with path.open() as f:
        rows = list(csv.DictReader(f))
    best: dict[tuple[str, str], dict[str, object]] = {}
    for r in rows:
        key = (r["local_day"], r["target"])
        if key not in best or (r["final"] == "1" and best[key]["final"] == 0):
            best[key] = {
                "day": r["local_day"],
                "target": r["target"],
                "value_f": int(r["value_f"]),
                "final": int(r["final"]),
            }
    return sorted(best.values(), key=lambda r: (str(r["day"]), str(r["target"])))[-2 * days :]


def forecasts(out: Path, sid: str) -> dict[str, dict[str, object]]:
    """The latest file per model product: rows as written, plus the issue instant."""
    d = out / "forecasts"
    out_: dict[str, dict[str, object]] = {}
    for model_dir in sorted(d.glob("*")) if d.is_dir() else []:
        p = newest(model_dir / sid, ".csv")
        if p is None:
            continue
        with p.open() as f:
            rows = list(csv.DictReader(f))
        out_[model_dir.name] = {"issued": p.stem, "rows": rows}
    return out_


def discussion(out: Path, st: dict[str, Any], office: str | None) -> dict[str, object] | None:
    if not office:
        return None
    p = newest(out / "afd" / office)
    if p is None:
        return None
    df = afd.parse(load_gz(p).decode(errors="replace"), office, stem_time(p))
    if df.empty:
        return None
    r = df.sort_values("issued_at").iloc[-1]
    return {
        "office": office,
        "issued": pd.Timestamp(r["issued_at"]).strftime("%Y-%m-%dT%H:%MZ"),
        "text": r["text"],
    }


def office_of(out: Path, sid: str) -> str | None:
    p = out / "nws_points" / f"{sid}.json"
    if not p.exists():
        return None
    try:
        return nws.resolve_grid(json.loads(p.read_bytes()))[0]
    except (KeyError, ValueError):
        return None


def scorecards(out: Path) -> dict[str, list[dict[str, object]]]:
    path = out / "scores" / "daily.csv"
    if not path.exists():
        return {"by_lead": [], "by_station": []}
    with path.open() as f:
        rows = list(csv.DictReader(f))
    groups: dict[str, dict[tuple[str, ...], list[dict[str, str]]]] = {
        "by_lead": defaultdict(list),
        "by_station": defaultdict(list),
    }
    for r in rows:
        groups["by_lead"][(r["product"], r["target"], bucket(float(r["lead_h"])))].append(r)
        groups["by_station"][(r["product"], r["target"], r["station"])].append(r)
    out_: dict[str, list[dict[str, object]]] = {}
    for name, g in groups.items():
        cells: list[dict[str, object]] = []
        for key, rs in sorted(g.items()):
            cov = [int(x["in90"]) for x in rs if x["in90"] != ""]
            cells.append(
                {
                    "product": key[0],
                    "target": key[1],
                    ("lead" if name == "by_lead" else "station"): key[2],
                    "n": len(rs),
                    "mae": round(sum(float(x["crps"]) for x in rs) / len(rs), 2),
                    "bias": round(sum(float(x["q50"]) - float(x["obs_f"]) for x in rs) / len(rs), 2),
                    "cov90": round(sum(cov) / len(cov), 2) if cov else None,
                    "thin": len(rs) < MIN_PAIRS,
                }
            )
        out_[name] = cells
    return out_


def build(out: Path, now: datetime) -> dict[str, Any]:
    site = out / "site"
    (site / "stations").mkdir(parents=True, exist_ok=True)
    index_stations = []
    archive_days: set[str] = set()
    for st in stations.load():
        if not st["active"]:
            continue
        sid = st["station_id"]
        files = list((out / "openmeteo" / sid).glob("*.gz")) if (out / "openmeteo" / sid).is_dir() else []
        archive_days |= {p.stem[:8] for p in files}
        office = office_of(out, sid)
        row = {
            "station": sid,
            "name": st["name"],
            "lat": st["lat"],
            "lon": st["lon"],
            "tz": st["tz"],
            "depth": st["depth"],
            "settles": st["settles"],
            "office": office,
        }
        index_stations.append(row)
        (site / "stations" / f"{sid}.json").write_text(
            json.dumps(
                {
                    **row,
                    "obs": observed(out, st, now),
                    "models": models(out, st),
                    "nws": nws_series(out, st),
                    "settlements": settlements(out, sid),
                    "forecasts": forecasts(out, sid),
                    "discussion": discussion(out, st, office) if st["depth"] == "deep" else None,
                }
            )
        )
    index: dict[str, Any] = {
        "built": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_start": min(archive_days) if archive_days else None,
        "archive_days": len(archive_days),
        "buckets": [f"{lo}-{hi}" for lo, hi in BUCKETS],
        "min_pairs": MIN_PAIRS,
        "models": list(MODELS),
        "stations": index_stations,
        "scores": scorecards(out),
    }
    (site / "index.json").write_text(json.dumps(index))
    return index


if __name__ == "__main__":
    idx = build(Path(sys.argv[1] if len(sys.argv) > 1 else "data"), datetime.now(UTC))
    print(
        f"site: {len(idx['stations'])} stations, record since {idx['record_start']}, "
        f"{idx['archive_days']} archive days, "
        f"{len(idx['scores']['by_lead'])} scorecard cells"
    )
