"""Datetime <-> hours-from-scenario-start helpers.

The engine works in floating-point hours measured from the scenario start
(PeriodStartDate). E.g. day-2 06:00 with a Monday-00:00 start = 30.0.
"""
from __future__ import annotations

from datetime import datetime, timedelta

_DT_FMT = "%Y-%m-%dT%H:%M:%S"


def parse_dt(value: str) -> datetime:
    """Parse a full ISO-ish datetime, tolerating fractional seconds."""
    return datetime.strptime(str(value).split(".")[0], _DT_FMT)


def parse_time_of_day(value: str) -> float:
    """Parse 'HH:MM:SS' (or 'HH:MM') into fractional hours (0..24)."""
    parts = [int(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.append(0)
    h, m, s = parts[:3]
    return h + m / 60.0 + s / 3600.0


def hours_from(start: datetime, dt: datetime) -> float:
    return (dt - start).total_seconds() / 3600.0


def day_window_hours(start: datetime, date_str: str, tod_start: str, tod_end: str) -> tuple[float, float]:
    """Resolve a (Date + time-of-day start/end) window to hour offsets.

    Handles windows that cross midnight (end <= start -> end is next day).
    """
    day = parse_dt(date_str)
    s_off = parse_time_of_day(tod_start)
    e_off = parse_time_of_day(tod_end)
    start_dt = day + timedelta(hours=s_off)
    end_dt = day + timedelta(hours=e_off + (24.0 if e_off <= s_off else 0.0))
    return hours_from(start, start_dt), hours_from(start, end_dt)
