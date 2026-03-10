"""MT5MarketFeed — implements MarketDataPort using MetaTrader 5.

All MetaTrader5 imports are lazy (inside methods) so this module
is importable on Linux/macOS for testing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from market.domain.entities import Candle, CandleSeries
from market.domain.value_objects import Timeframe

logger = logging.getLogger(__name__)

_TF_MAP: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 16385,
    Timeframe.H4: 16388,
    Timeframe.D1: 16408,
}


class MT5MarketFeed:
    """Fetches candles and current prices from a connected MT5 terminal."""

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int = 200,
    ) -> CandleSeries:
        import MetaTrader5 as mt5  # type: ignore[import]

        mt5_tf = _TF_MAP[timeframe]
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None:
            raise RuntimeError(f"copy_rates_from_pos failed: {mt5.last_error()}")

        candles = [
            Candle(
                time=datetime.fromtimestamp(r.time, tz=timezone.utc),
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.tick_volume),
                timeframe=timeframe,
            )
            for r in rates
        ]
        return CandleSeries(instrument_symbol=symbol, timeframe=timeframe, candles=candles)

    async def get_current_price(self, symbol: str) -> float:
        import MetaTrader5 as mt5  # type: ignore[import]

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed")
        return float(tick.bid)
