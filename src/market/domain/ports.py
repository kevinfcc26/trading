"""Market domain ports (Protocols)."""
from __future__ import annotations

from typing import Protocol

from .entities import CandleSeries
from .value_objects import Timeframe


class MarketDataPort(Protocol):
    """Protocol for fetching market data from any data source."""

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int = 200,
    ) -> CandleSeries: ...

    async def get_current_price(self, symbol: str) -> float: ...
