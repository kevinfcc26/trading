"""Pure mapping functions: MT5 raw structs ↔ trading domain entities."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from market.domain.value_objects import Timeframe
from trading.domain.entities import Direction, Order, OrderStatus, Position

# Mirrored constants (no MT5 import here — keeps mapper testable)
_MT5_ORDER_TYPE_BUY = 0
_MT5_ORDER_TYPE_SELL = 1


def mt5_tick_to_price(tick: Any) -> float:
    return float(tick["bid"])


def mt5_candles_to_domain(
    rates: list[Any],
    symbol: str,
    timeframe: Timeframe,
):
    from market.domain.entities import Candle as MarketCandle

    return [
        MarketCandle(
            time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["tick_volume"]),
            timeframe=timeframe,
        )
        for r in rates
    ]


def mt5_position_to_domain(pos: Any) -> Position:
    side = Direction.BUY if pos["type"] == _MT5_ORDER_TYPE_BUY else Direction.SELL
    return Position(
        broker_position_id=str(pos["ticket"]),
        instrument_symbol=str(pos["symbol"]),
        side=side,
        volume=float(pos["volume"]),
        entry_price=float(pos["price_open"]),
        stop_loss=float(pos["sl"]) if pos["sl"] else None,
        take_profit=float(pos["tp"]) if pos["tp"] else None,
        opened_at=datetime.fromtimestamp(pos["time"], tz=timezone.utc),
        is_open=True,
    )


_TF_MAP: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 16385,
    Timeframe.H4: 16388,
    Timeframe.D1: 16408,
}


def timeframe_to_mt5(tf: Timeframe) -> int:
    return _TF_MAP[tf]
