"""
MT5Adapter — implements IBroker + IDataProvider.
All MT5 imports are inside methods so the module is importable on Linux/Mac.
"""
import logging

from domain.entities import CandleSeries, Direction, Order, OrderStatus, Position
from domain.ports import IBroker, IDataProvider
from domain.value_objects import Timeframe

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


class MT5Adapter(IBroker, IDataProvider):
    def __init__(self, connection: MT5ConnectionManager) -> None:
        self._conn = connection

    # ── IBroker ──────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        await self._conn.connect()

    async def disconnect(self) -> None:
        await self._conn.disconnect()

    async def is_connected(self) -> bool:
        return self._conn.is_connected

    async def get_account_balance(self) -> float:
        import MetaTrader5 as mt5  # type: ignore[import]

        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info() failed: {mt5.last_error()}")
        return float(info.balance)

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
            "comment": f"brocker:{order.id}",
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != 10009:
            raise RuntimeError(f"order_send failed: {mt5.last_error()}, result={result}")

        order.broker_order_id = str(result.order)
        order.status = OrderStatus.FILLED
        logger.info("Order filled: %s %s vol=%s", order.direction, order.instrument_symbol, order.volume)
        return order

    async def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        import MetaTrader5 as mt5  # type: ignore[import]

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []
        return [mt5_position_to_domain(p) for p in positions]

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
            "comment": f"close:{position.id}",
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != 10009:
            raise RuntimeError(f"close_position failed: {mt5.last_error()}")

        position.is_open = False
        return position

    # ── IDataProvider ────────────────────────────────────────────────────────

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

    async def get_current_price(self, symbol: str) -> float:
        import MetaTrader5 as mt5  # type: ignore[import]

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed")
        return mt5_tick_to_price(tick)
