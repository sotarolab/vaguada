"""The NWS daily climate report (CLI), the settlement for the daily high and low.

Issued twice: a preliminary product in the late afternoon that says "valid today as of
5 PM", and a final product the next morning for the full day. Both are stored as rows;
`final` tells them apart and `received_at` orders them (decision 0002). The product text
goes to `products`, the parsed values to `settlements`, in Celsius.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd

from camanchaca_demo.ingest.feed import f_to_c
from camanchaca_demo.store import schemas

AFOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"

_WMO = re.compile(r"^\w{4}\d{2} (K\w{3}) (\d{2})(\d{2})(\d{2})", re.M)
_ISSUED = re.compile(
    r"^(\d{3,4}) (AM|PM) ([A-Z]{3,4}) \w{3} (\w{3}) (\d{1,2}) (\d{4})", re.M | re.I
)
_SUMMARY_DAY = re.compile(r"CLIMATE SUMMARY FOR (\w+) (\d{1,2}) (\d{4})")
_VALID = re.compile(r"VALID (TODAY|YESTERDAY)? ?AS OF (\d{3,4}) (AM|PM)", re.I)
_TEMP_BLOCK = re.compile(
    r"TEMPERATURE\s*\(F\)(.*?)(?:PRECIPITATION|SNOWFALL|DEGREE DAYS|WIND \(|$)", re.S
)
_ROW = re.compile(r"^\s*(MAXIMUM|MINIMUM)\s+(-?\d+|MM)", re.M)

_TZ = {
    "EST": -5,
    "EDT": -4,
    "CST": -6,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
    "AKST": -9,
    "AKDT": -8,
    "HST": -10,
}
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "JANUARY",
            "FEBRUARY",
            "MARCH",
            "APRIL",
            "MAY",
            "JUNE",
            "JULY",
            "AUGUST",
            "SEPTEMBER",
            "OCTOBER",
            "NOVEMBER",
            "DECEMBER",
        ],
        start=1,
    )
}
_MON3 = {k[:3]: v for k, v in _MONTHS.items()}


def fetch(client: httpx.Client, pil: str, limit: int = 3) -> str:
    r = client.get(AFOS_URL, params={"pil": pil, "limit": limit})
    r.raise_for_status()
    return r.text


def split_products(text: str) -> list[str]:
    return [
        p.strip()
        for p in text.split("\x01")
        if "CLIMATE" in p or "FORECAST DISCUSSION" in p or len(p.strip()) > 200
    ]


def issued_at(product: str) -> datetime | None:
    """From the '530 PM MDT THU OCT 29 2026' line, as UTC."""
    m = _ISSUED.search(product)
    if not m:
        return None
    hhmm, ampm, tzabbr, mon, day, year = m.groups()
    ampm, tzabbr, mon = ampm.upper(), tzabbr.upper(), mon.upper()
    hhmm = hhmm.zfill(4)
    hour, minute = int(hhmm[:2]) % 12 + (12 if ampm == "PM" else 0), int(hhmm[2:])
    offset = _TZ.get(tzabbr)
    if offset is None or mon not in _MON3:
        return None
    local = datetime(
        int(year), _MON3[mon], int(day), hour, minute, tzinfo=timezone(timedelta(hours=offset))
    )
    return local.astimezone(UTC)


def office(product: str) -> str | None:
    m = _WMO.search(product)
    return m.group(1) if m else None


def parse_one(product: str, station_id: str, received_at: datetime) -> list[dict[str, Any]]:
    """Settlement rows (tmax, tmin in Celsius) from one CLI product, or [] if unparseable."""
    md = _SUMMARY_DAY.search(product)
    if not md or md.group(1).upper() not in _MONTHS:
        return []
    local_day = date(int(md.group(3)), _MONTHS[md.group(1).upper()], int(md.group(2)))
    mv = _VALID.search(product)
    final = not (mv and (mv.group(1) or "").upper() == "TODAY")
    mb = _TEMP_BLOCK.search(product)
    if not mb:
        return []
    rows = []
    for label, val in _ROW.findall(mb.group(1)):
        if val == "MM":
            continue
        rows.append(
            {
                "station_id": station_id,
                "local_day": local_day,
                "target": "tmax" if label == "MAXIMUM" else "tmin",
                "received_at": received_at,
                "value": f_to_c(float(val)),
                "source": "nws-cli",
                "final": final,
            }
        )
    return rows


def parse(
    text: str, pil: str, station_id: str, received_at: datetime
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(settlements, products) from the raw AFOS response holding one or more products."""
    settle: list[dict[str, Any]] = []
    prods: list[dict[str, Any]] = []
    for product in split_products(text):
        at = issued_at(product)
        off = office(product)
        if at is None or off is None:
            continue
        prods.append(
            {
                "pil": pil,
                "issued_at": at,
                "office": off,
                "received_at": received_at,
                "text": product,
            }
        )
        settle.extend(
            {**row, "issued_at": at} for row in parse_one(product, station_id, received_at)
        )
    # One response can hold the preliminary and the final report of the same day. Both are
    # kept (decision 0002): one row per (day, target, final), the latest issued of each. Rows
    # from one fetch share `received_at`, which is in the key, so they are spaced a
    # microsecond apart in issue order to stay distinct rows.
    sdf = pd.DataFrame(settle, columns=[*schemas.SETTLEMENT_COLUMNS, "issued_at"])
    if len(sdf):
        sdf = (
            sdf.sort_values("issued_at")
            .drop_duplicates(["station_id", "local_day", "target", "final"], keep="last")
            .reset_index(drop=True)
        )
        order = sdf["issued_at"].rank(method="dense").astype(int) - 1
        sdf["received_at"] = [received_at + timedelta(microseconds=int(k)) for k in order]
        sdf = sdf.drop(columns="issued_at")
    s = schemas.validate_settlements(sdf.drop(columns="issued_at", errors="ignore"))
    p = schemas.validate_products(pd.DataFrame(prods, columns=schemas.PRODUCT_COLUMNS))
    return s, p
