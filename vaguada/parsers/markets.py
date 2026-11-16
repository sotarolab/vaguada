"""Public bracket prices for the daily high, where a market exists (decision 0005).

Prices only. No key, no account, nothing that trades. Prices arrive in cents and are
stored as probabilities. `as_of` is the slot the sample belongs to.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from vaguada.parsers import schemas

API_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
_DAY = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})-")
_MON = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1
    )
}


def url(series: str, limit: int = 100) -> str:
    return f"{API_URL}?{urlencode({'series_ticker': series, 'status': 'open', 'limit': limit})}"


def market_day(ticker: str) -> date | None:
    m = _DAY.search(ticker)
    if not m:
        return None
    yy, mon, dd = m.groups()
    if mon not in _MON:
        return None
    try:
        return date(2000 + int(yy), _MON[mon], int(dd))
    except ValueError:
        return None


def _prob(cents: Any) -> float | None:
    return None if cents is None else float(cents) / 100.0


def parse(payload: dict[str, Any], station_id: str, as_of: datetime, received_at: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for m in payload.get("markets", []):
        day = market_day(str(m.get("ticker", "")))
        if day is None:
            continue
        rows.append(
            {
                "ticker": m["ticker"],
                "as_of": as_of,
                "station_id": station_id,
                "local_day": day,
                "bracket_lo": None if m.get("floor_strike") is None else float(m["floor_strike"]),
                "bracket_hi": None if m.get("cap_strike") is None else float(m["cap_strike"]),
                "received_at": received_at,
                "yes_bid": _prob(m.get("yes_bid")),
                "yes_ask": _prob(m.get("yes_ask")),
                "last_price": _prob(m.get("last_price")),
            }
        )
    return schemas.validate_markets(pd.DataFrame(rows, columns=schemas.MARKET_COLUMNS))
