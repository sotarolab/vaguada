"""Claims about daily extremes. Read these before the code.

1. The high and low of a local day are the max and min of the hourly values whose valid time
   falls inside that local day, in the station's zone. A DST day has 23 or 25 hours and is
   still one day.
2. The running extreme at an instant uses only values valid at or before that instant, and
   never exceeds the day's final extreme.
3. A model run's daily extremes come from its hourly array placed on the clock at
   run_at + step_h + i, grouped by local day the same way.
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from camanchaca_demo import localday
from camanchaca_demo.features.daily import daily_extremes, model_daily_extremes, running_extreme

TZ = "America/Los_Angeles"


def hourly_obs(start: datetime, values: list[float], var: str = "t2m") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_id": "asos:KLAX",
            "valid_at": [start + timedelta(hours=i) for i in range(len(values))],
            "received_at": start + timedelta(hours=len(values)),
            "source": "test",
            "var": var,
            "value": values,
            "precision": None,
        }
    )


def test_daily_extremes_group_by_local_day() -> None:
    day = date(2026, 7, 15)
    start, _ = localday.day_bounds(day, TZ)
    # 48 hours from local midnight: the first day peaks at 30, the second at 20.
    values = [10.0 + (i % 24) * 0.8 if i < 24 else 5.0 + (i % 24) * 0.6 for i in range(48)]
    d = daily_extremes(hourly_obs(start, values), TZ)
    assert d["local_day"].tolist() == [day, day + timedelta(days=1)]
    assert d["tmax"].tolist() == [max(values[:24]), max(values[24:])]
    assert d["tmin"].tolist() == [min(values[:24]), min(values[24:])]
    assert d["n_hours"].tolist() == [24, 24]


def test_dst_day_is_one_day_with_25_hours() -> None:
    day = date(2026, 11, 1)  # fall back in the US
    start, end = localday.day_bounds(day, TZ)
    n = int((end - start).total_seconds() // 3600)
    assert n == 25
    d = daily_extremes(hourly_obs(start, [float(i) for i in range(n)]), TZ)
    assert len(d) == 1 and d["n_hours"].iloc[0] == 25 and d["tmax"].iloc[0] == 24.0


@given(st.lists(st.floats(-20, 45, allow_nan=False), min_size=1, max_size=24), st.integers(0, 23))
@settings(max_examples=200, deadline=None)
def test_running_extreme_never_exceeds_the_day(values: list[float], hour: int) -> None:
    day = date(2026, 7, 15)
    start, _ = localday.day_bounds(day, TZ)
    obs = hourly_obs(start, values)
    full = daily_extremes(obs, TZ).iloc[0]
    hi, lo, n = running_extreme(obs, day, TZ, start + timedelta(hours=hour))
    assert n == min(hour + 1, len(values))
    assert hi is not None and lo is not None
    assert hi <= full["tmax"] and lo >= full["tmin"]
    assert hi == max(values[: hour + 1]) and lo == min(values[: hour + 1])


def test_running_extreme_before_the_day_is_empty() -> None:
    day = date(2026, 7, 15)
    start, _ = localday.day_bounds(day, TZ)
    obs = hourly_obs(start, [20.0, 21.0])
    assert running_extreme(obs, day, TZ, start - timedelta(minutes=1)) == (None, None, 0)


def test_model_daily_extremes_place_the_array_on_the_clock() -> None:
    day = date(2026, 7, 15)
    start, _ = localday.day_bounds(day, TZ)
    run_at = start + timedelta(hours=6)  # a run at 06:00 local, 18 hours left in the day
    values = [15.0 + i for i in range(18)] + [10.0 + i for i in range(24)]
    runs = pd.DataFrame(
        [
            {
                "model": "gfs",
                "station_id": "asos:KLAX",
                "run_at": pd.Timestamp(run_at),
                "received_at": pd.Timestamp(run_at),
                "source": "test",
                "var": "t2m",
                "step_h": 0,
                "values": values,
            }
        ]
    )
    md = model_daily_extremes(runs, TZ)
    assert md["local_day"].tolist() == [day, day + timedelta(days=1)]
    assert md["tmax"].tolist() == [32.0, 33.0]
    assert md["n_hours"].tolist() == [18, 24]


def test_empty_inputs_give_empty_frames() -> None:
    empty = hourly_obs(datetime(2026, 7, 15, tzinfo=UTC), [])
    assert daily_extremes(empty, TZ).empty
    assert model_daily_extremes(pd.DataFrame(columns=["var"]), TZ).empty
