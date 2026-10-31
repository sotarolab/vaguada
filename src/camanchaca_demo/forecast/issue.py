"""The one path. The hourly job and the backtest both call `issue_slot()` for a slot, and
`issue()` for an instant with explicit targets (the hourly nowcast rows at deep stations)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from camanchaca_demo import localday
from camanchaca_demo.forecast.base import Forecaster, Inputs
from camanchaca_demo.store.read import Store

log = logging.getLogger(__name__)
HISTORY_H = 72


def inputs_at(store: Store, station_id: str, tz: str, as_of: datetime) -> Inputs:
    return Inputs(
        station_id=station_id,
        tz=tz,
        as_of=as_of,
        obs=store.observations(station_id, as_of - timedelta(hours=HISTORY_H), as_of),
        runs=store.latest_runs(station_id, as_of),
        settlements=store.settlements(station_id, as_of),
    )


def issue(
    store: Store,
    station_id: str,
    tz: str,
    as_of: datetime,
    targets: list[tuple[str, date]],
    forecasters: Sequence[Forecaster],
    received_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Predictions for the given (target, day) pairs from every forecaster.

    `as_of` is the label on the row, the slot instant. The read happens at `received_at`
    when given (the hourly job passes the moment it ran, a few seconds to minutes after the
    slot, so it sees what it just fetched) and at `as_of` otherwise (a backtest). The instant
    read is stored on the row. Returns the rows written. A forecaster that raises is skipped."""
    read_at = received_at or as_of
    inp = inputs_at(store, station_id, tz, read_at)
    rows: list[dict[str, Any]] = []
    for target, day in targets:
        for f in forecasters:
            try:
                p = f.predict(target, day, inp)
            except Exception as exc:  # noqa: BLE001  a forecaster must not stop the slot
                log.warning("%s failed for %s %s %s: %s", f.name, station_id, target, day, exc)
                continue
            if p is None:
                continue
            rows.append(
                {
                    "forecaster": f.name,
                    "version": f.version,
                    "station_id": station_id,
                    "target": target,
                    "local_day": day,
                    "as_of": as_of,
                    "received_at": read_at,
                    "quantiles": p.quantiles,
                    "features": {**p.features, "lead_h": localday.lead_h(as_of, day, tz)},
                }
            )
    store.write_predictions(rows)
    return rows


def issue_slot(
    store: Store,
    station_id: str,
    tz: str,
    slot_day: date,
    slot_hour: int,
    forecasters: Sequence[Forecaster],
    received_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """The slot form: every (target, day) the slot covers, read at the slot instant."""
    as_of = localday.slot_time(slot_day, slot_hour, tz)
    targets = localday.targets_for_slot(slot_day, slot_hour)
    return issue(store, station_id, tz, as_of, targets, forecasters, received_at)
