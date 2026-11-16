"""Score every forecast of the daily high and low against the settled climate report. Forecasts
come from two places: model files under data/forecasts/<model>/<station>/<issue>.csv
(date,target,lead_h,q05,q25,q50,q75,q95 in Fahrenheit), and the baselines this script builds
from the archive at every local issue slot: each raw model's daily extreme, the NWS daily
series, and persistence. A baseline at slot t uses only files fetched before t, which is the
same rule a backtest follows. One row per (product, station, issue, target, day) in
data/scores/daily.csv; the pooled table is printed.

Run: python score.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from vaguada import daily, localday, stations
from vaguada.parsers import nws, open_meteo
from vaguada.parsers.schemas import c_to_f

COLUMNS = [
    "product",
    "station",
    "issue",
    "target",
    "date",
    "lead_h",
    "obs_f",
    "q50",
    "crps",
    "in90",
    "report",
]
BUCKETS = [(0, 6), (6, 12), (12, 24), (24, 48), (48, 72), (72, 120)]
QUANTILES = ("q05", "q25", "q50", "q75", "q95")
# shortcut: no climatology baseline yet; needs per-station daily normals (NCEI), add when the
# first month of scores exists


def stem_time(path: Path) -> datetime:
    return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def newest_before(d: Path, t: datetime) -> Path | None:
    files = [p for p in d.glob("*.gz") if stem_time(p) <= t] if d.is_dir() else []
    return max(files, key=stem_time) if files else None


def crps(members: list[float], y: float) -> float:
    """Fair ensemble CRPS (Hersbach 2000) over the members, as hapi scores it; one member is
    the absolute error."""
    xs = sorted(members)
    n = len(xs)
    spread = 2 * sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1)) / (n * n)
    return sum(abs(x - y) for x in xs) / n - 0.5 * spread * n / max(n - 1, 1)


def read_settlements(out: Path, station: str) -> dict[tuple[date, str], tuple[int, bool]]:
    """{(day, target): (value_f, final)}; a final report wins over a preliminary one."""
    path = out / "settlements" / f"{station}.csv"
    if not path.exists():
        return {}
    best: dict[tuple[date, str], tuple[int, bool]] = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            key = (date.fromisoformat(r["local_day"]), r["target"])
            final = r["final"] == "1"
            if key not in best or (final and not best[key][1]):
                best[key] = (int(r["value_f"]), final)
    return best


def settled_before(out: Path, station: str, t: datetime) -> dict[tuple[date, str], int]:
    """What had settled by t: the newest report row fetched before t per (day, target)."""
    path = out / "settlements" / f"{station}.csv"
    if not path.exists():
        return {}
    known: dict[tuple[date, str], tuple[datetime, int]] = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            received = datetime.strptime(r["received_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if received > t:
                continue
            key = (date.fromisoformat(r["local_day"]), r["target"])
            issued = datetime.strptime(r["issued_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if key not in known or issued > known[key][0]:
                known[key] = (issued, int(r["value_f"]))
    return {k: v for k, (_, v) in known.items()}


def baselines_at(out: Path, st: dict[str, Any], t: datetime) -> dict[str, dict[tuple[str, date], float]]:
    """{product: {(target, day): value_f}} from the newest files fetched before t."""
    sid, tz = st["station_id"], st["tz"]
    products: dict[str, dict[tuple[str, date], float]] = defaultdict(dict)
    p = newest_before(out / "openmeteo" / sid, t)
    if p is not None:
        payload = json.loads(gzip.decompress(p.read_bytes()))
        runs = open_meteo.parse(payload, sid, stem_time(p), stem_time(p), deep=True)
        for _, r in daily.model_daily_extremes(runs, tz).iterrows():
            if r["n_hours"] >= 18:
                products[f"raw_{r['model']}"][("tmax", r["local_day"])] = c_to_f(r["tmax"])
                products[f"raw_{r['model']}"][("tmin", r["local_day"])] = c_to_f(r["tmin"])
    p = newest_before(out / "nws_grid" / sid, t)
    if p is not None:
        payload = json.loads(gzip.decompress(p.read_bytes()))
        runs = nws.parse(payload, sid, tz, stem_time(p))
        for _, r in runs[runs["var"].isin(["tmax", "tmin"])].iterrows():
            day0 = localday.local_day_of(r["run_at"].to_pydatetime(), tz)
            for i, v in enumerate(r["values"]):
                if v is not None:
                    products["nws"][(str(r["var"]), day0 + timedelta(days=i))] = c_to_f(float(v))
    known = settled_before(out, sid, t)
    for (day, target), v in known.items():
        for ahead in range(1, 6):
            products["persistence"].setdefault((target, day + timedelta(days=ahead)), float(v))
    return products


def read_forecast(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def score_station(out: Path, st: dict[str, Any], now: datetime) -> list[dict[str, object]]:
    sid, tz = st["station_id"], st["tz"]
    truth = read_settlements(out, sid)
    if not truth:
        return []
    rows: list[dict[str, object]] = []
    first = min(d for d, _ in truth)
    # Baselines at every local slot from the first settled day to now.
    day = first - timedelta(days=5)
    today = localday.local_day_of(now, tz)
    while day <= today:
        for hour in localday.SLOT_HOURS:
            t = localday.slot_time(day, hour, tz)
            if t > now:
                break
            products = baselines_at(out, st, t)
            for product, values in products.items():
                for (target, d), v in values.items():
                    if (d, target) not in truth:
                        continue
                    lead = localday.lead_h(t, d, tz)
                    if lead <= 0 or lead > BUCKETS[-1][1]:
                        continue
                    obs, final = truth[(d, target)]
                    rows.append(
                        {
                            "product": product,
                            "station": sid,
                            "issue": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "target": target,
                            "date": d.isoformat(),
                            "lead_h": round(lead, 1),
                            "obs_f": obs,
                            "q50": round(v, 1),
                            "crps": round(abs(v - obs), 2),
                            "in90": "",
                            "report": "final" if final else "preliminary",
                        }
                    )
        day += timedelta(days=1)
    # Model files: one per issue instant.
    for p in sorted((out / "forecasts").glob(f"*/{sid}/*.csv")) if (out / "forecasts").is_dir() else []:
        product = p.parent.parent.name
        t = datetime.strptime(p.stem, "%Y-%m-%dT%HZ").replace(tzinfo=UTC)
        for r in read_forecast(p):
            d, target = date.fromisoformat(r["date"]), r["target"]
            if (d, target) not in truth:
                continue
            obs, final = truth[(d, target)]
            qs = [float(r[q]) for q in QUANTILES if r.get(q) not in (None, "")]
            rows.append(
                {
                    "product": product,
                    "station": sid,
                    "issue": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "target": target,
                    "date": d.isoformat(),
                    "lead_h": round(float(r["lead_h"]), 1),
                    "obs_f": obs,
                    "q50": round(float(r["q50"]), 1),
                    "crps": round(crps(qs, obs), 2),
                    "in90": int(float(r["q05"]) <= obs <= float(r["q95"]))
                    if "q05" in r and "q95" in r
                    else "",
                    "report": "final" if final else "preliminary",
                }
            )
    return rows


def bucket(lead_h: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= lead_h < hi:
            return f"{lo}-{hi}"
    return f"{BUCKETS[-1][0]}-{BUCKETS[-1][1]}"


def pooled(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["product", "target", "bucket", "n", "mae", "cov90"])
    df = pd.DataFrame(rows)
    df["bucket"] = df["lead_h"].astype(float).map(bucket)
    df["in90n"] = pd.to_numeric(df["in90"], errors="coerce")
    g = df.groupby(["product", "target", "bucket"])
    return (
        g.agg(n=("crps", "size"), mae=("crps", "mean"), cov90=("in90n", "mean"))
        .reset_index()
        .round({"mae": 2, "cov90": 2})
    )


def main(out: Path) -> int:
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    for st in stations.load():
        if st["settles"]:
            rows.extend(score_station(out, st, now))
    path = out / "scores" / "daily.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{now:%Y-%m-%dT%H:%MZ} scored {len(rows)} forecast rows")
    print(pooled(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
