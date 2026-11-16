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

import bisect
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
PERSIST_DAYS = 5
# shortcut: no climatology baseline yet; needs per-station daily normals (NCEI), add when the
# first month of scores exists

Values = dict[tuple[str, date], float]


def stem_time(path: Path) -> datetime:
    return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def floor_hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def crps(members: list[float], y: float) -> float:
    """Fair ensemble CRPS (Hersbach 2000) over the members, as hapi scores it; one member is
    the absolute error."""
    xs = sorted(members)
    n = len(xs)
    spread = 2 * sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1)) / (n * n)
    return sum(abs(x - y) for x in xs) / n - 0.5 * spread * n / max(n - 1, 1)


class Archive:
    """One station's archived files, listed once, with each file's daily values parsed once."""

    def __init__(self, out: Path, st: dict[str, Any]) -> None:
        self.st = st
        self.sid, self.tz = st["station_id"], st["tz"]
        self.files: dict[str, list[tuple[datetime, Path]]] = {}
        for product in ("openmeteo", "nws_grid"):
            d = out / product / self.sid
            self.files[product] = sorted((stem_time(p), p) for p in d.glob("*.gz")) if d.is_dir() else []
        self.rows = self._settlement_rows(out / "settlements" / f"{self.sid}.csv")
        self._parsed: dict[Path, dict[str, Values]] = {}

    @staticmethod
    def _settlement_rows(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open() as f:
            rows = list(csv.DictReader(f))
        return [
            {
                "day": date.fromisoformat(r["local_day"]),
                "target": r["target"],
                "value": int(r["value_f"]),
                "final": r["final"] == "1",
                "issued": parse_iso(r["issued_at"]),
                "received": parse_iso(r["received_at"]),
            }
            for r in rows
        ]

    def truth(self) -> dict[tuple[date, str], tuple[int, bool]]:
        """{(day, target): (value_f, final)}: a final report beats a preliminary one, and among
        reports of the same kind the latest issued wins."""
        best: dict[tuple[date, str], dict[str, Any]] = {}
        for r in self.rows:
            key = (r["day"], r["target"])
            cur = best.get(key)
            if cur is None or (r["final"], r["issued"]) > (cur["final"], cur["issued"]):
                best[key] = r
        return {k: (r["value"], r["final"]) for k, r in best.items()}

    def settled_before(self, t: datetime) -> dict[tuple[date, str], int]:
        """What had settled by t: the latest issued report row fetched before t per (day, target)."""
        known: dict[tuple[date, str], dict[str, Any]] = {}
        for r in self.rows:
            if r["received"] > t:
                continue
            key = (r["day"], r["target"])
            if key not in known or r["issued"] > known[key]["issued"]:
                known[key] = r
        return {k: r["value"] for k, r in known.items()}

    def newest_before(self, product: str, t: datetime) -> Path | None:
        files = self.files[product]
        i = bisect.bisect_right([ft for ft, _ in files], t)
        return files[i - 1][1] if i else None

    def parsed(self, product: str, p: Path) -> dict[str, Values]:
        """{product: {(target, day): value_f}} for one archived file, cached."""
        if p not in self._parsed:
            payload = json.loads(gzip.decompress(p.read_bytes()))
            fetched = floor_hour(stem_time(p))  # the array is placed on the clock from this hour
            out: dict[str, Values] = defaultdict(dict)
            if product == "openmeteo":
                runs = open_meteo.parse(payload, self.sid, fetched, fetched, deep=True)
                for _, r in daily.model_daily_extremes(runs, self.tz).iterrows():
                    if r["n_hours"] >= 18:
                        out[f"raw_{r['model']}"][("tmax", r["local_day"])] = c_to_f(r["tmax"])
                        out[f"raw_{r['model']}"][("tmin", r["local_day"])] = c_to_f(r["tmin"])
            else:
                runs = nws.parse(payload, self.sid, self.tz, fetched)
                for _, r in runs[runs["var"].isin(["tmax", "tmin"])].iterrows():
                    day0 = localday.local_day_of(r["run_at"].to_pydatetime(), self.tz)
                    for i, v in enumerate(r["values"]):
                        if v is not None:
                            out["nws"][(str(r["var"]), day0 + timedelta(days=i))] = c_to_f(float(v))
            self._parsed[p] = dict(out)
        return self._parsed[p]

    def baselines_at(self, t: datetime) -> dict[str, Values]:
        """{product: {(target, day): value_f}} from the newest files fetched before t."""
        products: dict[str, Values] = {}
        for product in ("openmeteo", "nws_grid"):
            p = self.newest_before(product, t)
            if p is not None:
                products.update(self.parsed(product, p))
        known = self.settled_before(t)
        persistence: Values = {}
        for target in ("tmax", "tmin"):
            days = sorted(d for (d, tg) in known if tg == target)
            if not days:
                continue
            last = days[-1]  # the most recent settled day is what persists
            for ahead in range(1, PERSIST_DAYS + 1):
                persistence[(target, last + timedelta(days=ahead))] = float(known[(last, target)])
        if persistence:
            products["persistence"] = persistence
        return products


def read_forecast(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _row(
    product: str,
    sid: str,
    t: datetime,
    target: str,
    d: date,
    lead: float,
    obs: int,
    final: bool,
    q50: float,
    score_: float,
    in90: int | str,
) -> dict[str, object]:
    return {
        "product": product,
        "station": sid,
        "issue": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": target,
        "date": d.isoformat(),
        "lead_h": round(lead, 1),
        "obs_f": obs,
        "q50": round(q50, 1),
        "crps": round(score_, 2),
        "in90": in90,
        "report": "final" if final else "preliminary",
    }


def score_station(out: Path, st: dict[str, Any], now: datetime) -> list[dict[str, object]]:
    sid, tz = st["station_id"], st["tz"]
    archive = Archive(out, st)
    truth = archive.truth()
    if not truth:
        return []
    rows: list[dict[str, object]] = []
    first = min(d for d, _ in truth)
    day = first - timedelta(days=PERSIST_DAYS)
    today = localday.local_day_of(now, tz)
    while day <= today:
        for hour in localday.SLOT_HOURS:
            t = localday.slot_time(day, hour, tz)
            if t > now:
                break
            for product, values in archive.baselines_at(t).items():
                for (target, d), v in values.items():
                    if (d, target) not in truth:
                        continue
                    lead = localday.lead_h(t, d, tz)
                    if lead <= 0 or lead > BUCKETS[-1][1]:
                        continue
                    obs, final = truth[(d, target)]
                    rows.append(_row(product, sid, t, target, d, lead, obs, final, v, abs(v - obs), ""))
        day += timedelta(days=1)
    for p in sorted((out / "forecasts").glob(f"*/{sid}/*.csv")) if (out / "forecasts").is_dir() else []:
        product = p.parent.parent.name
        t = datetime.strptime(p.stem, "%Y-%m-%dT%HZ").replace(tzinfo=UTC)
        for r in read_forecast(p):
            d, target = date.fromisoformat(r["date"]), r["target"]
            qs = {q: float(r[q]) for q in QUANTILES if r.get(q)}
            if (d, target) not in truth or "q50" not in qs:
                continue
            obs, final = truth[(d, target)]
            in90: int | str = int(qs["q05"] <= obs <= qs["q95"]) if "q05" in qs and "q95" in qs else ""
            rows.append(
                _row(
                    product,
                    sid,
                    t,
                    target,
                    d,
                    float(r["lead_h"]),
                    obs,
                    final,
                    qs["q50"],
                    crps(list(qs.values()), obs),
                    in90,
                )
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
    return g.agg(n=("crps", "size"), mae=("crps", "mean"), cov90=("in90n", "mean")).reset_index().round(2)


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
