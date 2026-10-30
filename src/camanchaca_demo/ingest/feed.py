"""Feeds never raise. A feed is a function that returns a frame; this wrapper runs it,
writes the heartbeat row, and returns an empty frame on any failure."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pandas as pd

from camanchaca_demo.store.read import Store

log = logging.getLogger(__name__)


def run_feed(
    store: Store,
    name: str,
    fetch: Callable[[], pd.DataFrame],
    write: Callable[[pd.DataFrame], int],
    empty: pd.DataFrame,
    at: datetime | None = None,
) -> pd.DataFrame:
    """Run one feed. `at` is when it ran (wall clock); it defaults to now."""
    stamp = at or datetime.now(UTC)
    try:
        frame = fetch()
        rows = write(frame)
        _beat(store, name, True, rows, None, stamp)
        log.info("%s: %d rows", name, rows)
        return frame
    except Exception as exc:  # noqa: BLE001  the whole point: nothing escapes a feed
        log.warning("%s failed: %s", name, exc)
        _beat(store, name, False, 0, f"{type(exc).__name__}: {exc}", stamp)
        return empty


def _beat(store: Store, name: str, ok: bool, rows: int, error: str | None, at: datetime) -> None:
    """The heartbeat write is itself guarded: a store failure must not escape either."""
    try:
        store.heartbeat(name, ok, rows, error, at)
    except Exception as exc:  # noqa: BLE001
        log.error("heartbeat for %s could not be written: %s", name, exc)


def client(user_agent: str, timeout_s: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout_s, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0
