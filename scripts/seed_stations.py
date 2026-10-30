"""Seed or refresh the stations table from data/stations.csv.

Resolves each station's NWS office and grid point once, through the points endpoint, and
writes everything with an upsert. Rerunning is safe.

    python scripts/seed_stations.py            # every row in the file
    python scripts/seed_stations.py --no-nws   # skip the office lookup
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from camanchaca_demo.config import settings
from camanchaca_demo.ingest import nws
from camanchaca_demo.ingest.feed import client
from camanchaca_demo.store.engine import make_engine
from camanchaca_demo.store.read import PgStore

log = logging.getLogger("seed")
CSV = Path(__file__).resolve().parents[1] / "data" / "stations.csv"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-nws", action="store_true", help="skip the NWS office and grid lookup")
    args = ap.parse_args()

    cfg = settings()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL is not set")
    df = pd.read_csv(CSV, dtype={"settlement_source": str, "market_series": str})
    df = df.where(pd.notna(df), None)
    for col in ("nws_office", "nws_grid_x", "nws_grid_y"):
        if col not in df.columns:
            df[col] = None

    if not args.no_nws:
        with client(cfg.user_agent, cfg.http_timeout_s) as c:
            for i, row in df.iterrows():
                try:
                    office, x, y = nws.resolve_grid(c, float(row["lat"]), float(row["lon"]))
                    df.at[i, "nws_office"] = office
                    df.at[i, "nws_grid_x"] = x
                    df.at[i, "nws_grid_y"] = y
                    log.info("%s -> %s %d,%d", row["station_id"], office, x, y)
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s: NWS lookup failed: %s", row["station_id"], exc)

    store = PgStore(make_engine(cfg.database_url), cfg.db_schema)
    n = store.upsert_stations(df)
    log.info("%d stations written", n)


if __name__ == "__main__":
    main()
