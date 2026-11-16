"""The one place that knows what a local day is.

Every timestamp stored or passed around is UTC and tz-aware. A station's local calendar
day, the issue slots inside it, the lead to its end, and which (target, day) pairs a slot
forecasts are all derived here and nowhere else.

Slots are 00:00, 06:00, 12:00 and 18:00 local. A target is scored at the six slots before
its typical time: the high (afternoon) at day-ahead 06, 12, 18 and same-day 00, 06, 12; the
low (dawn) at 18:00 two days before, then 00, 06, 12, 18 the day before and 00 on the day.
The 18:00 slot also issues days 2 through 5 for both targets.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

SLOT_HOURS: tuple[int, ...] = (0, 6, 12, 18)
TARGETS: tuple[str, ...] = ("tmax", "tmin")
MAX_DAYS_AHEAD = 5


def _aware(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise ValueError("naive datetime; every timestamp must be tz-aware")
    return t


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    """UTC start (inclusive) and end (exclusive) of a local calendar day."""
    zone = ZoneInfo(tz)
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_day_of(t: datetime, tz: str) -> date:
    return _aware(t).astimezone(ZoneInfo(tz)).date()


def slot_time(day: date, hour: int, tz: str) -> datetime:
    """The UTC instant of a local slot. On a spring-forward day a slot inside the gap does
    not exist; the slots used here (00, 06, 12, 18) never fall in a US gap."""
    if hour not in SLOT_HOURS:
        raise ValueError(f"not a slot hour: {hour}")
    return datetime(day.year, day.month, day.day, hour, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def slot_at(t: datetime, tz: str) -> tuple[date, int] | None:
    """If the instant is exactly a local slot, return (local_day, slot_hour); else None.
    Used by the hourly job: floor the clock to the hour and ask each station."""
    local = _aware(t).astimezone(ZoneInfo(tz))
    if local.minute or local.second or local.microsecond or local.hour not in SLOT_HOURS:
        return None
    # A fall-back day repeats 01:00; slot hours are never inside that fold, but keep the
    # round trip honest: the instant must map back to itself.
    if slot_time(local.date(), local.hour, tz) != t.astimezone(UTC):
        return None
    return local.date(), local.hour


def lead_h(as_of: datetime, day: date, tz: str) -> float:
    """Hours from an instant to the end of a station's local day. Positive for every
    forecast the system issues; negative only after the day has closed."""
    _, end = day_bounds(day, tz)
    return (end - _aware(as_of).astimezone(UTC)).total_seconds() / 3600.0


def targets_for_slot(day: date, hour: int) -> list[tuple[str, date]]:
    """The (target, local_day) pairs a slot issues, in scoring order."""
    if hour not in SLOT_HOURS:
        raise ValueError(f"not a slot hour: {hour}")
    out: list[tuple[str, date]] = []
    d1, d2 = day + timedelta(days=1), day + timedelta(days=2)
    # The high: same day until noon, day-ahead from 06:00.
    if hour in (0, 6, 12):
        out.append(("tmax", day))
    if hour in (6, 12, 18):
        out.append(("tmax", d1))
    # The low: the day itself only at 00:00; the day ahead all day; two days ahead at 18:00.
    if hour == 0:
        out.append(("tmin", day))
    out.append(("tmin", d1))
    if hour == 18:
        out.append(("tmin", d2))
    # The evening slot carries the longer leads for both targets.
    if hour == 18:
        for n in range(2, MAX_DAYS_AHEAD + 1):
            dn = day + timedelta(days=n)
            if ("tmax", dn) not in out:
                out.append(("tmax", dn))
            if ("tmin", dn) not in out:
                out.append(("tmin", dn))
    return out
