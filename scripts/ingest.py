"""The hourly job.

    python scripts/ingest.py --now                       # this hour, every station whose slot it is
    python scripts/ingest.py --now 2026-10-30T18:00Z     # a given hour
    python scripts/ingest.py --now --stations asos:KLAX --force   # one station, slot or not

Deep stations are fetched every hour. Slot stations are fetched only when the hour is one
of their local slots. Every feed goes through `run_feed`, so a failing source writes a
heartbeat row and nothing else stops.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from camanchaca_demo import localday
from camanchaca_demo.config import settings
from camanchaca_demo.ingest import afd, iem_asos, iem_cli, markets, nws, open_meteo
from camanchaca_demo.ingest.feed import client, run_feed
from camanchaca_demo.store import schemas
from camanchaca_demo.store.engine import make_engine
from camanchaca_demo.store.read import PgStore, Store

log = logging.getLogger("ingest")


def parse_now(value: str | None) -> datetime:
    if value in (None, "", "now"):
        now = datetime.now(UTC)
    else:
        now = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def select_stations(
    stations: pd.DataFrame, now: datetime, only: list[str] | None, force: bool
) -> pd.DataFrame:
    df = stations[stations["active"].astype(bool)]
    if only:
        df = df[df["station_id"].isin(only)]
    if force:
        return df
    keep = [
        bool(r["depth"] == "deep" or localday.slot_at(now, str(r["tz"]))) for _, r in df.iterrows()
    ]
    return df[keep]


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and pd.isna(value)) and value != ""


def ingest_observations(
    store: Store, c: httpx.Client, ids: list[str], now: datetime, received: datetime
) -> None:
    id_map = {iem_asos.iem_id(s): s for s in ids}
    run_feed(
        store,
        "iem-asos",
        lambda: iem_asos.parse(
            iem_asos.fetch(c, ids, now - timedelta(hours=3), now), received, id_map
        ),
        store.write_observations,
        schemas.empty(schemas.OBS_COLUMNS),
        received,
    )


def ingest_station(
    store: Store,
    c: httpx.Client,
    st: pd.Series,
    now: datetime,
    received: datetime,
    offices_done: set[str],
) -> None:
    sid, deep, tz = str(st["station_id"]), st["depth"] == "deep", str(st["tz"])
    lat, lon = float(st["lat"]), float(st["lon"])

    run_feed(
        store,
        f"open-meteo:{sid}",
        lambda: open_meteo.parse(open_meteo.fetch(c, lat, lon, deep), sid, now, received, deep),
        store.write_model_runs,
        schemas.empty(schemas.RUN_COLUMNS),
        received,
    )

    office = st.get("nws_office")
    if _present(office) and _present(st.get("nws_grid_x")):
        office_s, x, y = str(office), int(st["nws_grid_x"]), int(st["nws_grid_y"])
        run_feed(
            store,
            f"nws:{sid}",
            lambda: nws.parse(nws.fetch(c, office_s, x, y), sid, tz, received),
            store.write_model_runs,
            schemas.empty(schemas.RUN_COLUMNS),
            received,
        )
        if deep and office_s not in offices_done:
            offices_done.add(office_s)
            run_feed(
                store,
                f"afd:{office_s}",
                lambda: afd.parse(afd.fetch(c, office_s), office_s, received),
                store.write_products,
                schemas.empty(schemas.PRODUCT_COLUMNS),
                received,
            )

    series = st.get("market_series")
    if _present(series):
        series_s = str(series)
        run_feed(
            store,
            f"markets:{sid}",
            lambda: markets.parse(markets.fetch(c, series_s), sid, now, received),
            store.write_markets,
            schemas.empty(schemas.MARKET_COLUMNS),
            received,
        )

    pil = st.get("settlement_source")
    if bool(st["settles"]) and _present(pil):
        pil_s = str(pil)

        def _cli() -> pd.DataFrame:
            s, p = iem_cli.parse(iem_cli.fetch(c, pil_s), pil_s, sid, received)
            store.write_products(p)
            return s

        run_feed(
            store,
            f"cli:{sid}",
            _cli,
            store.write_settlements,
            schemas.empty(schemas.SETTLEMENT_COLUMNS),
            received,
        )


def run(
    store: Store, stations: pd.DataFrame, now: datetime, user_agent: str, timeout_s: float
) -> None:
    received = datetime.now(UTC)
    offices_done: set[str] = set()
    with client(user_agent, timeout_s) as c:
        ingest_observations(store, c, list(stations["station_id"]), now, received)
        for _, st in stations.iterrows():
            ingest_station(store, c, st, now, received, offices_done)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", nargs="?", const="now", default="now", help="UTC hour to run as")
    ap.add_argument("--stations", default=None, help="comma-separated station ids")
    ap.add_argument("--force", action="store_true", help="ignore slot gating")
    args = ap.parse_args()

    cfg = settings()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL is not set")
    now = parse_now(args.now)
    store = PgStore(make_engine(cfg.database_url), cfg.db_schema)
    only = args.stations.split(",") if args.stations else None
    chosen = select_stations(store.stations(), now, only, args.force)
    log.info("%s: %d stations selected", now.isoformat(), len(chosen))
    if chosen.empty:
        return
    run(store, chosen, now, cfg.user_agent, cfg.http_timeout_s)


if __name__ == "__main__":
    main()
