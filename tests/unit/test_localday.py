"""Claims about local days, slots and leads. These hold for every station time zone across
DST transitions; hypothesis draws the dates."""

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from camanchaca_demo import localday

ZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Detroit",
    "America/Boise",
    "America/Indiana/Indianapolis",
    "America/Kentucky/Louisville",
]
DAYS = st.dates(min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))


@given(day=DAYS, tz=st.sampled_from(ZONES))
@settings(max_examples=300)
def test_day_bounds_round_trip(day: date, tz: str) -> None:
    start, end = localday.day_bounds(day, tz)
    assert start.tzinfo is UTC and end.tzinfo is UTC
    assert localday.local_day_of(start, tz) == day
    assert localday.local_day_of(end - timedelta(microseconds=1), tz) == day
    assert localday.local_day_of(end, tz) == day + timedelta(days=1)
    assert (end - start) in (timedelta(hours=23), timedelta(hours=24), timedelta(hours=25))


@given(day=DAYS, tz=st.sampled_from(ZONES))
@settings(max_examples=300)
def test_every_local_day_has_exactly_four_slots(day: date, tz: str) -> None:
    start, end = localday.day_bounds(day, tz)
    t = start
    hits = []
    while t < end:
        s = localday.slot_at(t, tz)
        if s is not None:
            hits.append(s)
        t += timedelta(hours=1)
    assert hits == [(day, h) for h in localday.SLOT_HOURS]


@given(day=DAYS, tz=st.sampled_from(ZONES), hour=st.sampled_from(localday.SLOT_HOURS))
@settings(max_examples=300)
def test_slot_time_and_slot_at_agree(day: date, tz: str, hour: int) -> None:
    t = localday.slot_time(day, hour, tz)
    assert localday.slot_at(t, tz) == (day, hour)
    assert localday.slot_at(t + timedelta(minutes=1), tz) is None


def test_lead_to_end_of_day_on_dst_days() -> None:
    tz = "America/Denver"
    spring, fall = date(2026, 3, 8), date(2026, 11, 1)
    assert localday.lead_h(localday.slot_time(spring, 18, tz), spring, tz) == 6
    assert localday.lead_h(localday.slot_time(fall, 18, tz), fall, tz) == 6
    assert localday.lead_h(localday.slot_time(spring, 0, tz), spring, tz) == 23
    assert localday.lead_h(localday.slot_time(fall, 0, tz), fall, tz) == 25
    # Day-ahead from the evening slot: 6 h to midnight plus the whole next day.
    assert localday.lead_h(localday.slot_time(spring, 18, tz), spring + timedelta(days=1), tz) == 30


def test_lead_is_negative_once_the_day_has_closed() -> None:
    tz = "America/Chicago"
    day = date(2026, 7, 15)
    _, end = localday.day_bounds(day, tz)
    assert localday.lead_h(end + timedelta(hours=2), day, tz) == -2


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        localday.local_day_of(datetime(2026, 7, 15, 12), "America/Chicago")  # noqa: DTZ001


def test_targets_per_slot_match_the_schedule() -> None:
    d = date(2026, 7, 15)
    d1, d2 = d + timedelta(days=1), d + timedelta(days=2)
    assert localday.targets_for_slot(d, 0) == [("tmax", d), ("tmin", d), ("tmin", d1)]
    assert localday.targets_for_slot(d, 6) == [("tmax", d), ("tmax", d1), ("tmin", d1)]
    assert localday.targets_for_slot(d, 12) == [("tmax", d), ("tmax", d1), ("tmin", d1)]
    evening = localday.targets_for_slot(d, 18)
    assert evening[:3] == [("tmax", d1), ("tmin", d1), ("tmin", d2)]
    assert ("tmax", d2) in evening
    assert ("tmax", d + timedelta(days=5)) in evening
    assert ("tmin", d + timedelta(days=5)) in evening
    assert len(evening) == len(set(evening))


def test_each_target_day_is_issued_at_six_short_slots_plus_the_evening_long_leads() -> None:
    """Across six consecutive days of slots, a given (target, day) appears at exactly the
    six short-lead slots the plan names, plus the 18:00 issues from two to five days out."""
    d = date(2026, 7, 15)
    issued: dict[tuple[str, date], list[tuple[int, int]]] = {}
    for offset in range(-6, 1):
        day = d + timedelta(days=offset)
        for h in localday.SLOT_HOURS:
            for target, tday in localday.targets_for_slot(day, h):
                if tday == d:
                    issued.setdefault((target, d), []).append((offset, h))
    long_leads = [(-5, 18), (-4, 18), (-3, 18), (-2, 18)]
    short_high = [(-1, 6), (-1, 12), (-1, 18), (0, 0), (0, 6), (0, 12)]
    assert issued[("tmax", d)] == long_leads + short_high
    assert issued[("tmin", d)] == long_leads + [(-1, 0), (-1, 6), (-1, 12), (-1, 18), (0, 0)]
