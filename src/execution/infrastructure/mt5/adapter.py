"""MT5Adapter — implements BrokerPort + MarketDataPort using MetaTrader 5.

All MetaTrader5 imports are lazy (inside methods) — importable on Linux/macOS.
"""
from __future__ import annotations

import logging
from uuid import UUID

from market.domain.entities import CandleSeries
from market.domain.value_objects import Timeframe
from trading.domain.entities import Direction, Order, OrderStatus, Position

from .connection import MT5ConnectionManager
from .mapper import (
    mt5_candles_to_domain,
    mt5_position_to_domain,
    mt5_tick_to_price,
    timeframe_to_mt5,
)

logger = logging.getLogger(__name__)

_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_ACTION_DEAL = 1
_ORDER_FILLING_IOC = 1


class MT5Adapter:
    """Satisfies BrokerPort and MarketDataPort structurally."""

    def __init__(self, connection: MT5ConnectionManager) -> None:
        self._conn = connection

    # ── BrokerPort ───────────────────────────────────────────────────────────

    async def connect(self) -> None:
        await self._conn.connect()

    async def disconnect(self) -> None:
        await self._conn.disconnect()

    async def is_connected(self) -> bool:
        return self._conn.is_connected

    async def get_balance(self) -> float:
        import MetaTrader5 as mt5  # type: ignore[import]

        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info() failed: {mt5.last_error()}")
        return float(info.balance)

    # Backwards compat alias
    async def get_account_balance(self) -> float:
        return await self.get_balance()

    async def submit_order(self, order: Order) -> Order:
        import MetaTrader5 as mt5  # type: ignore[import]

        order_type = _ORDER_TYPE_BUY if order.direction == Direction.BUY else _ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(order.instrument_symbol)
        price = float(tick.ask) if order.direction == Direction.BUY else float(tick.bid)

        request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": order.instrument_symbol,
            "volume": order.volume,
            "type": order_type,
            "price": price,
            "sl": order.stop_loss or 0.0,
            "tp": order.take_profit or 0.0,
            "type_filling": _ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != 10009:
            raise RuntimeError(f"order_send failed: {mt5.last_error()}, result={result}")

        order.broker_order_id = str(result.order)
        order.status = OrderStatus.FILLED
        logger.info("Order filled: %s %s vol=%s", order.direction, order.instrument_symbol, order.volume)
        return order

    async def cancel_order(self, order_id: UUID) -> None:
        raise NotImplementedError("MT5 market orders cannot be cancelled after submission")

    async def fetch_positions(self, symbol: str | None = None) -> list[Position]:
        import MetaTrader5 as mt5  # type: ignore[import]

        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []
        return [mt5_position_to_domain(p) for p in positions]

    # Backwards compat alias
    async def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        return await self.fetch_positions(symbol)

    async def close_position(self, position: Position) -> Position:
        import MetaTrader5 as mt5  # type: ignore[import]

        close_type = _ORDER_TYPE_SELL if position.side == Direction.BUY else _ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(position.instrument_symbol)
        price = float(tick.bid) if position.side == Direction.BUY else float(tick.ask)

        request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": position.instrument_symbol,
            "volume": position.volume,
            "type": close_type,
            "position": int(position.broker_position_id),
            "price": price,
            "type_filling": _ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != 10009:
            raise RuntimeError(f"close_position failed: {mt5.last_error()}")

        position.is_open = False
        return position

    # ── MarketDataPort ────────────────────────────────────────────────────────

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int = 200,
    ) -> CandleSeries:
        import MetaTrader5 as mt5  # type: ignore[import]

        mt5_tf = timeframe_to_mt5(timeframe)
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None:
            raise RuntimeError(f"copy_rates_from_pos failed: {mt5.last_error()}")

        candles = mt5_candles_to_domain(rates, symbol, timeframe)
        return CandleSeries(instrument_symbol=symbol, timeframe=timeframe, candles=candles)

    async def get_closed_pnl(self, symbol: str, broker_position_id: str) -> float | None:
        """Return realized PnL for a closed position, or None if not found."""
        import MetaTrader5 as mt5
        from datetime import datetime, timezone, timedelta

        date_from = datetime.now(timezone.utc) - timedelta(days=7)
        date_to = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(date_from, date_to, group=symbol)
        if not deals:
            return None
        total = 0.0
        found = False
        for deal in deals:
            if str(deal.position_id) == str(broker_position_id):
                total += deal.profit
                found = True
        return total if found else None

    async def get_current_price(self, symbol: str) -> float:
        import MetaTrader5 as mt5  # type: ignore[import]

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed")
        return mt5_tick_to_price(tick)
