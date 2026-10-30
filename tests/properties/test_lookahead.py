"""The lookahead property: a read at `as_of` equals the read over the frame with every row
received after `as_of` removed, and each key appears once as the latest-received survivor.
Hypothesis draws observation rows with corrections and a random `as_of`."""

from datetime import UTC, datetime, timedelta

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from camanchaca_demo.store.read import FrameStore
from tests.store_contract import check_journal, check_store

T0 = datetime(2026, 7, 15, 0, tzinfo=UTC)
SID = "asos:KTEST"

row = st.fixed_dictionaries(
    {
        "valid_h": st.integers(0, 48),
        "delay_h": st.floats(0, 48, allow_nan=False),
        "value": st.floats(-30, 50, allow_nan=False),
        "var": st.sampled_from(["t2m", "td2m"]),
    }
)


def frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_id": SID,
            "valid_at": [T0 + timedelta(hours=int(r["valid_h"])) for r in rows],  # type: ignore[call-overload]
            "received_at": [
                T0 + timedelta(hours=int(r["valid_h"]) + float(r["delay_h"]))  # type: ignore[call-overload]
                for r in rows
            ],
            "source": "test",
            "var": [str(r["var"]) for r in rows],
            "value": [float(r["value"]) for r in rows],  # type: ignore[arg-type]
            "precision": None,
        }
    )


@given(rows=st.lists(row, min_size=1, max_size=60), as_of_h=st.floats(0, 100, allow_nan=False))
@settings(max_examples=200, deadline=None)
def test_read_at_as_of_equals_filtered_read(rows: list[dict[str, object]], as_of_h: float) -> None:
    store = FrameStore()
    df = frame(rows)
    store.write_observations(df)
    as_of = T0 + timedelta(hours=as_of_h)
    got = store.observations(SID, T0, as_of)

    visible = df[(df.received_at <= as_of) & (df.valid_at <= as_of)]
    # Equal keys with equal received_at are the same row (duplicate key, ignored on write).
    expected = (
        visible.sort_values(["valid_at", "var", "received_at"], ascending=[True, True, False])
        .drop_duplicates(["valid_at", "var"], keep="first")
        .sort_values(["valid_at", "var"])
    )
    assert len(got) == len(expected)
    assert not got.duplicated(["valid_at", "source", "var"]).any()
    assert (got["received_at"] <= as_of).all()
    g = got.sort_values(["valid_at", "var"]).reset_index(drop=True)
    e = expected.reset_index(drop=True)
    assert g["received_at"].tolist() == e["received_at"].tolist()
    assert g["value"].tolist() == e["value"].tolist()


@given(
    rows=st.lists(row, min_size=1, max_size=40),
    as_of_h=st.floats(0, 100, allow_nan=False),
    extra=st.lists(row, min_size=0, max_size=20),
)
@settings(max_examples=100, deadline=None)
def test_rows_received_later_change_nothing(
    rows: list[dict[str, object]], as_of_h: float, extra: list[dict[str, object]]
) -> None:
    as_of = T0 + timedelta(hours=as_of_h)
    a = FrameStore()
    a.write_observations(frame(rows))
    before = a.observations(SID, T0, as_of)
    if extra:
        late = frame(extra)
        delay = pd.to_timedelta(late["received_at"] - T0)
        late["received_at"] = as_of + timedelta(seconds=1) + delay
        a.write_observations(late)
    after = a.observations(SID, T0, as_of)
    pd.testing.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True))


def test_frame_store_meets_the_contract() -> None:
    check_store(FrameStore())


def test_frame_store_journal() -> None:
    check_journal(FrameStore())
