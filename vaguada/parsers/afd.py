"""The Area Forecast Discussion, as text with its issue time, one per office."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from vaguada.parsers import schemas
from vaguada.parsers.iem_cli import AFOS_URL, issued_at, office, split_products


def url(nws_office: str, limit: int = 2) -> str:
    return f"{AFOS_URL}?{urlencode({'pil': f'AFD{nws_office}', 'limit': limit})}"


def parse(text: str, nws_office: str, received_at: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for product in split_products(text):
        at = issued_at(product)
        if at is None:
            continue
        rows.append(
            {
                "pil": f"AFD{nws_office}",
                "issued_at": at,
                "office": office(product) or nws_office,
                "received_at": received_at,
                "text": product,
            }
        )
    return schemas.validate_products(pd.DataFrame(rows, columns=schemas.PRODUCT_COLUMNS))
