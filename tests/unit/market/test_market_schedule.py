"""Tests for market_schedule — Forex open/close logic and candle alignment."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market.domain.market_schedule import (
    is_forex_open,
    is_weekend,
    next_candle_open,
    seconds_until_market_open,
    seconds_until_next_candle,
)
from market.domain.value_objects import Timeframe


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ── is_forex_open ──────────────────────────────────────────────────────────

class TestIsForexOpen:
    def test_monday_morning_is_open(self) -> None:
        # Monday 09:00 UTC
        assert is_forex_open(_utc(2025, 1, 6, 9)) is True

    def test_wednesday_midnight_is_open(self) -> None:
        assert is_forex_open(_utc(2025, 1, 8, 0)) is True

    def test_friday_before_close_is_open(self) -> None:
        # Friday 21:59 UTC — still open
        assert is_forex_open(_utc(2025, 1, 10, 21, 59)) is True

    def test_friday_at_22_is_closed(self) -> None:
        assert is_forex_open(_utc(2025, 1, 10, 22)) is False

    def test_friday_after_22_is_closed(self) -> None:
        assert is_forex_open(_utc(2025, 1, 10, 23)) is False

    def test_saturday_is_closed(self) -> None:
        assert is_forex_open(_utc(2025, 1, 11, 12)) is False

    def test_sunday_before_22_is_closed(self) -> None:
        assert is_forex_open(_utc(2025, 1, 12, 21, 59)) is False

    def test_sunday_at_22_is_open(self) -> None:
        assert is_forex_open(_utc(2025, 1, 12, 22)) is True

    def test_sunday_after_22_is_open(self) -> None:
        assert is_forex_open(_utc(2025, 1, 12, 23)) is True


# ── is_weekend ────────────────────────────────────────────────────────────

class TestIsWeekend:
    def test_weekend_is_inverse_of_open(self) -> None:
        saturday = _utc(2025, 1, 11, 14)
        tuesday = _utc(2025, 1, 7, 14)
        assert is_weekend(saturday) is True
        assert is_weekend(tuesday) is False


# ── next_candle_open ──────────────────────────────────────────────────────

class TestNextCandleOpen:
    def test_h1_mid_candle(self) -> None:
        # 01:30 → next open is 02:00
        now = _utc(2025, 1, 7, 1, 30, 0)
        nxt = next_candle_open(Timeframe.H1, now)
        assert nxt == _utc(2025, 1, 7, 2, 0, 0)

    def test_h1_one_second_before_close(self) -> None:
        now = _utc(2025, 1, 7, 1, 59, 59)
        nxt = next_candle_open(Timeframe.H1, now)
        assert nxt == _utc(2025, 1, 7, 2, 0, 0)

    def test_h1_exactly_on_boundary_returns_next(self) -> None:
        # Exactly at 02:00:00 — current candle just opened, next is 03:00
        now = _utc(2025, 1, 7, 2, 0, 0)
        nxt = next_candle_open(Timeframe.H1, now)
        assert nxt == _utc(2025, 1, 7, 3, 0, 0)

    def test_m15_mid_candle(self) -> None:
        # 01:07 → next M15 open is 01:15
        now = _utc(2025, 1, 7, 1, 7, 0)
        nxt = next_candle_open(Timeframe.M15, now)
        assert nxt == _utc(2025, 1, 7, 1, 15, 0)

    def test_h4_mid_candle(self) -> None:
        # 05:30 → next H4 open is 08:00
        now = _utc(2025, 1, 7, 5, 30, 0)
        nxt = next_candle_open(Timeframe.H4, now)
        assert nxt == _utc(2025, 1, 7, 8, 0, 0)

    def test_next_candle_is_always_in_future(self) -> None:
        for tf in Timeframe:
            now = _utc(2025, 1, 7, 12, 34, 56)
            nxt = next_candle_open(tf, now)
            assert nxt > now, f"next_candle_open({tf}) must be strictly after now"


# ── seconds_until_next_candle ─────────────────────────────────────────────

class TestSecondsUntilNextCandle:
    def test_returns_positive(self) -> None:
        now = _utc(2025, 1, 7, 10, 15, 30)
        secs = seconds_until_next_candle(Timeframe.H1, now)
        assert secs > 0

    def test_h1_at_quarter_past(self) -> None:
        # 10:15:00 → 45 minutes until 11:00
        now = _utc(2025, 1, 7, 10, 15, 0)
        secs = seconds_until_next_candle(Timeframe.H1, now)
        assert secs == pytest.approx(45 * 60, abs=1)


# ── seconds_until_market_open ─────────────────────────────────────────────

class TestSecondsUntilMarketOpen:
    def test_returns_zero_when_open(self) -> None:
        tuesday = _utc(2025, 1, 7, 10, 0, 0)
        assert seconds_until_market_open(tuesday) == 0.0

    def test_saturday_noon_to_sunday_22(self) -> None:
        saturday_noon = _utc(2025, 1, 11, 12, 0, 0)
        secs = seconds_until_market_open(saturday_noon)
        expected_reopen = _utc(2025, 1, 12, 22, 0, 0)
        expected_secs = (expected_reopen - saturday_noon).total_seconds()
        assert secs == pytest.approx(expected_secs, abs=1)

    def test_friday_after_close_to_sunday_22(self) -> None:
        friday_23 = _utc(2025, 1, 10, 23, 0, 0)
        secs = seconds_until_market_open(friday_23)
        expected_reopen = _utc(2025, 1, 12, 22, 0, 0)
        expected_secs = (expected_reopen - friday_23).total_seconds()
        assert secs == pytest.approx(expected_secs, abs=1)

    def test_sunday_before_open_to_sunday_22(self) -> None:
        sunday_morning = _utc(2025, 1, 12, 8, 0, 0)
        secs = seconds_until_market_open(sunday_morning)
        expected_reopen = _utc(2025, 1, 12, 22, 0, 0)
        expected_secs = (expected_reopen - sunday_morning).total_seconds()
        assert secs == pytest.approx(expected_secs, abs=1)
