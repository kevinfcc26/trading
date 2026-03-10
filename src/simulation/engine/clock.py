"""SimulatedClock — controls simulated time during backtesting."""
from __future__ import annotations

from datetime import datetime


class SimulatedClock:
    """A clock that advances bar-by-bar during backtest replay.

    The BacktestEngine calls advance() after each candle is processed.
    All components that need the current time should call now().
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now: datetime = start or datetime.utcnow()

    def advance(self, to: datetime) -> None:
        """Advance the clock to the given timestamp."""
        if to < self._now:
            raise ValueError(f"Cannot advance clock backwards: {to} < {self._now}")
        self._now = to

    def now(self) -> datetime:
        return self._now
