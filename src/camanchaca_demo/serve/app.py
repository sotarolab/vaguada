"""The service. Routes read tables; nothing computes here. Serves the built client at `/`
when `client/dist` exists."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from camanchaca_demo.config import settings
from camanchaca_demo.serve import models as m
from camanchaca_demo.serve.page import build_page, to_station
from camanchaca_demo.store.engine import make_engine
from camanchaca_demo.store.read import PgStore

app = FastAPI(title="camanchaca-demo", version="0.1.0")
_store: PgStore | None = None


def store() -> PgStore:
    global _store
    if _store is None:
        cfg = settings()
        if not cfg.database_url:
            raise HTTPException(503, "DATABASE_URL is not set")
        _store = PgStore(make_engine(cfg.database_url), cfg.db_schema)
    return _store


@app.get("/healthz", response_model=m.Health)
def healthz() -> m.Health:
    try:
        beats = store().heartbeats()
    except Exception as exc:  # noqa: BLE001
        return m.Health(
            ok=False,
            db=False,
            feeds=[
                m.FeedStatus(
                    feed="db", last_success=None, last_error=str(exc)[:200], rows=0, updated_at=None
                )
            ],
        )
    feeds = [
        m.FeedStatus(
            feed=str(r["feed"]),
            last_success=None if pd.isna(r["last_success"]) else r["last_success"],
            last_error=None if pd.isna(r["last_error"]) else str(r["last_error"]),
            rows=int(r["rows"]),
            updated_at=None if pd.isna(r["updated_at"]) else r["updated_at"],
        )
        for _, r in beats.iterrows()
    ]
    return m.Health(ok=all(f.last_error is None for f in feeds), db=True, feeds=feeds)


@app.get("/api/stations", response_model=list[m.Station])
def stations() -> list[m.Station]:
    df = store().stations()
    return [to_station(r) for _, r in df[df["active"].astype(bool)].iterrows()]


@app.get("/api/station/{station_id}", response_model=m.StationPage)
def station(
    station_id: str,
    as_of: datetime | None = Query(default=None, description="Point in time; default now"),
    hours_back: int = Query(default=48, ge=1, le=240),
    hours_ahead: int = Query(default=120, ge=1, le=192),
) -> m.StationPage:
    if as_of is not None and as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    page = build_page(store(), station_id, as_of, hours_back, hours_ahead)
    if page is None:
        raise HTTPException(404, f"unknown station {station_id}")
    return page


@app.get("/api/journal/{station_id}", response_model=list[m.JournalEntry])
def journal(station_id: str, limit: int = Query(default=60, ge=1, le=500)) -> list[m.JournalEntry]:
    df = store().journal(station_id, datetime.now(UTC), limit)
    return [
        m.JournalEntry(
            station_id=str(r["station_id"]),
            local_day=r["local_day"],
            created_at=pd.Timestamp(r["created_at"]).to_pydatetime(),
            uncertainty=None if pd.isna(r["uncertainty"]) else int(r["uncertainty"]),
            tags=list(r["tags"] or []),
            text=str(r["text"] or ""),
        )
        for _, r in df.iterrows()
    ]


@app.post("/api/journal", response_model=m.JournalEntry, status_code=201)
def add_journal(entry: m.JournalNew) -> m.JournalEntry:
    """The one write route: a person's reading of a day (decision 0006)."""
    row = m.JournalEntry(created_at=datetime.now(UTC), **entry.model_dump())
    store().write_journal(row.model_dump())
    return row


DIST = Path(__file__).resolve().parents[3] / "client" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
