"""The read contract both stores must satisfy. Called by the in-memory test and by the
Postgres integration test with the same rows, so the two cannot drift."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from camanchaca_demo.store.read import Store

SID = "test:CONTRACT"
T0 = datetime(2026, 7, 15, 0, tzinfo=UTC)


def obs(valid_h: int, received_h: float, value: float, var: str = "t2m") -> dict[str, object]:
    return {
        "station_id": SID,
        "valid_at": T0 + timedelta(hours=valid_h),
        "received_at": T0 + timedelta(hours=received_h),
        "source": "test",
        "var": var,
        "value": value,
        "precision": None,
    }


def check_store(store: Store) -> None:
    # Observations: a correction is a later row; reads at as_of see the right one.
    rows = [obs(1, 1.5, 10.0), obs(1, 3.0, 11.0), obs(2, 2.5, 12.0), obs(2, 2.5, 99.0)]
    n = store.write_observations(pd.DataFrame(rows))
    assert n == 3  # the exact duplicate key is ignored
    assert store.write_observations(pd.DataFrame(rows)) == 0  # idempotent
    # A re-fetch later with the same value is not a correction; a changed value is.
    assert store.write_observations(pd.DataFrame([obs(1, 9.0, 11.0)])) == 0
    assert store.write_observations(pd.DataFrame([obs(1, 9.0, 11.5)])) == 1

    early = store.observations(SID, T0, T0 + timedelta(hours=2))
    assert early[early.valid_at == T0 + timedelta(hours=1)]["value"].tolist() == [10.0]
    assert (early.valid_at != T0 + timedelta(hours=2)).all()  # received at 2.5 h, not yet

    late = store.observations(SID, T0, T0 + timedelta(hours=4))
    assert late[late.valid_at == T0 + timedelta(hours=1)]["value"].tolist() == [11.0]
    assert len(late[late.valid_at == T0 + timedelta(hours=2)]) == 1

    # Model runs: latest run per (model, var) among those received by as_of.
    runs = pd.DataFrame(
        [
            {
                "model": "gfs",
                "station_id": SID,
                "run_at": T0,
                "received_at": T0 + timedelta(hours=1),
                "source": "test",
                "var": "t2m",
                "step_h": 0,
                "values": [1.0, 2.0],
            },
            {
                "model": "gfs",
                "station_id": SID,
                "run_at": T0 + timedelta(hours=6),
                "received_at": T0 + timedelta(hours=7),
                "source": "test",
                "var": "t2m",
                "step_h": 0,
                "values": [3.0, 4.0],
            },
        ]
    )
    assert store.write_model_runs(runs) == 2
    at6 = store.latest_runs(SID, T0 + timedelta(hours=6, minutes=30))
    assert at6["run_at"].tolist() == [T0]  # the 06 run exists but was not received yet
    at8 = store.latest_runs(SID, T0 + timedelta(hours=8))
    assert at8["run_at"].tolist() == [T0 + timedelta(hours=6)]
    assert list(at8["values"].iloc[0]) == [3.0, 4.0]
    assert len(store.runs_between(SID, T0, T0 + timedelta(hours=8))) == 2

    # Settlements: preliminary then final; the read at as_of returns the latest received.
    day = date(2026, 7, 15)
    settle = pd.DataFrame(
        [
            {
                "station_id": SID,
                "local_day": day,
                "target": "tmax",
                "received_at": T0 + timedelta(hours=25),
                "value": 30.0,
                "source": "test",
                "final": False,
            },
            {
                "station_id": SID,
                "local_day": day,
                "target": "tmax",
                "received_at": T0 + timedelta(hours=33),
                "value": 30.6,
                "source": "test",
                "final": True,
            },
        ]
    )
    assert store.write_settlements(settle) == 2
    s1 = store.settlements(SID, T0 + timedelta(hours=26))
    assert s1["value"].tolist() == [30.0] and not bool(s1["final"].iloc[0])
    s2 = store.settlements(SID, T0 + timedelta(hours=40), days=[day])
    assert s2["value"].tolist() == [30.6] and bool(s2["final"].iloc[0])
    again = settle.iloc[[1]].assign(received_at=T0 + timedelta(hours=50))
    assert store.write_settlements(again) == 0  # same final value re-fetched: no row

    # Markets: latest sample per ticker at as_of.
    mk = pd.DataFrame(
        [
            {
                "ticker": "T-1",
                "as_of": T0,
                "station_id": SID,
                "local_day": day,
                "bracket_lo": 70.0,
                "bracket_hi": 71.0,
                "received_at": T0,
                "yes_bid": 0.1,
                "yes_ask": 0.2,
                "last_price": None,
            },
            {
                "ticker": "T-1",
                "as_of": T0 + timedelta(hours=6),
                "station_id": SID,
                "local_day": day,
                "bracket_lo": 70.0,
                "bracket_hi": 71.0,
                "received_at": T0 + timedelta(hours=6),
                "yes_bid": 0.3,
                "yes_ask": 0.4,
                "last_price": 0.35,
            },
        ]
    )
    assert store.write_markets(mk) == 2
    m = store.markets(SID, day, T0 + timedelta(hours=3))
    assert m["yes_bid"].tolist() == [0.1]
    m = store.markets(SID, day, T0 + timedelta(hours=9))
    assert m["yes_bid"].tolist() == [0.3]

    # Predictions: duplicate keys ignored.
    pred = {
        "forecaster": "persistence",
        "version": "1",
        "station_id": SID,
        "target": "tmax",
        "local_day": day,
        "as_of": T0,
        "received_at": T0,
        "quantiles": {"p50": 29.0},
        "features": {},
    }
    assert store.write_predictions([pred]) == 1
    assert store.write_predictions([pred]) == 0


def check_journal(store: Store) -> None:
    """The one table a person writes: append-only, read back newest first."""
    note = {
        "station_id": SID,
        "local_day": date(2026, 7, 15),
        "created_at": T0 + timedelta(hours=30),
        "uncertainty": 4,
        "tags": ["marine layer"],
        "text": "models split on the burn-off",
    }
    assert store.write_journal(note) == 1
    assert store.write_journal(note) == 0
    later = {**note, "created_at": T0 + timedelta(hours=31), "text": "burned off by noon"}
    assert store.write_journal(later) == 1
    j = store.journal(SID, T0 + timedelta(hours=40))
    assert j["text"].tolist() == ["burned off by noon", "models split on the burn-off"]
    assert store.journal(SID, T0 + timedelta(hours=30, minutes=30))["text"].tolist() == [
        "models split on the burn-off"
    ]
