"""Forex market schedule utilities.

Forex operates 24/5:
  Opens:  Sunday  22:00 UTC  (Sydney session start)
  Closes: Friday  22:00 UTC  (New York session end)
  Closed: Saturday all day + Sunday before 22:00 UTC

Candle alignment:
  Signals are evaluated only at the OPEN of a new bar, never mid-candle.
  This avoids acting on incomplete data and mirrors how professional
  trading desks operate (analyse the closed candle, decide at the open).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .value_objects import Timeframe


def is_forex_open(dt: datetime | None = None) -> bool:
    """True if the Forex spot market is open at the given UTC datetime.

    Closed window: Friday 22:00 UTC → Sunday 22:00 UTC.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    weekday = dt.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun
    hour = dt.hour

    if weekday == 5:                # Saturday — always closed
        return False
    if weekday == 4 and hour >= 22: # Friday ≥22:00 UTC — closed
        return False
    if weekday == 6 and hour < 22:  # Sunday <22:00 UTC — closed
        return False
    return True


def is_weekend(dt: datetime | None = None) -> bool:
    """True during the Forex weekend closure (Fri 22:00 → Sun 22:00 UTC)."""
    return not is_forex_open(dt)


def next_candle_open(timeframe: Timeframe, dt: datetime | None = None) -> datetime:
    """UTC datetime of the next candle boundary after *dt*.

    Always returns a strictly future boundary: if *dt* falls exactly on a
    bar boundary the following boundary (+1 period) is returned, because the
    current bar just opened — there is nothing new to act on yet.

    Examples (H1 timeframe):
      01:00:00 → 02:00:00  (just opened, wait for next)
      01:01:40 → 02:00:00
      01:59:59 → 02:00:00
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    period = timeframe.minutes * 60          # period in seconds
    ts = dt.timestamp()
    boundary = math.floor(ts / period) * period
    next_ts = boundary + period              # always the *next* boundary
    return datetime.fromtimestamp(next_ts, tz=timezone.utc)


def seconds_until_next_candle(timeframe: Timeframe, dt: datetime | None = None) -> float:
    """Seconds until the next candle opens. Always returns a value > 0."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    nxt = next_candle_open(timeframe, dt)
    return max(1.0, (nxt - dt).total_seconds())


def seconds_until_market_open(dt: datetime | None = None) -> float:
    """Seconds until the next Forex session open (Sunday 22:00 UTC).

    Returns 0.0 if the market is already open.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if is_forex_open(dt):
        return 0.0

    # Advance to next Sunday 22:00 UTC
    days_until_sunday = (6 - dt.weekday()) % 7  # Sunday == 6
    candidate = (dt + timedelta(days=days_until_sunday)).replace(
        hour=22, minute=0, second=0, microsecond=0
    )
    # Guard: if candidate is in the past (shouldn't happen given is_forex_open check)
    if candidate <= dt:
        candidate += timedelta(weeks=1)
    return (candidate - dt).total_seconds()
