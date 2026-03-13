"""PaperBrokerAdapter — simulates order execution for dry-run and backtesting."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from market.domain.entities import Candle, CandleSeries
from market.domain.value_objects import Timeframe
from trading.domain.entities import Direction, Order, OrderStatus, Position

logger = logging.getLogger(__name__)


class PaperBrokerAdapter:
    """In-memory broker that simulates fills at current price.

    Used for:
    - Live dry-run mode (no real orders sent)
    - Backtesting simulation via BacktestEngine
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        spread_pips: float = 0.0002,
        commission_per_lot: float = 7.0,
        slippage_pips: float = 0.0001,
    ) -> None:
        self._balance = initial_balance
        self._spread = spread_pips
        self._commission_per_lot = commission_per_lot
        self._slippage = slippage_pips
        self._positions: list[Position] = []
        self._connected = False
        self._current_price: float = 0.0

    # ── BrokerPort ───────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        logger.info("PaperBroker connected (initial balance=%.2f)", self._balance)

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("PaperBroker disconnected")

    async def is_connected(self) -> bool:
        return self._connected

    async def get_balance(self) -> float:
        return self._balance

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 1000
    ) -> CandleSeries:
        """Generate synthetic random-walk OHLCV candles for backtesting without MT5."""
        _TF_MINUTES = {
            "M1": 1, "M5": 5, "M15": 15,
            "H1": 60, "H4": 240, "D1": 1440,
        }
        tf_minutes = _TF_MINUTES.get(timeframe.value, 60)
        now = datetime.now(tz=timezone.utc)
        candles: list[Candle] = []
        price = 1.1000
        for i in range(count):
            t = now - timedelta(minutes=tf_minutes * (count - i))
            change = random.gauss(0, 0.0005)
            open_ = round(price, 5)
            close = round(open_ + change, 5)
            high = round(max(open_, close) + abs(random.gauss(0, 0.0002)), 5)
            low = round(min(open_, close) - abs(random.gauss(0, 0.0002)), 5)
            volume = random.uniform(100, 1000)
            candles.append(Candle(
                time=t, open=open_, high=high, low=low,
                close=close, volume=volume, timeframe=timeframe,
            ))
            price = close
        logger.info(
            "PaperBroker: generated %d synthetic candles for %s %s",
            count, symbol, timeframe.value,
        )
        return CandleSeries(instrument_symbol=symbol, timeframe=timeframe, candles=candles)

    # Backwards compat alias
    async def get_account_balance(self) -> float:
        return self._balance

    def set_current_price(self, price: float) -> None:
        """Called by BacktestEngine to advance the simulated price."""
        self._current_price = price

    async def submit_order(self, order: Order) -> Order:
        fill_price = self._apply_slippage(order.direction)

        # Simulate commission
        commission = self._commission_per_lot * order.volume

        position = Position(
            instrument_symbol=order.instrument_symbol,
            side=order.direction,
            volume=order.volume,
            entry_price=fill_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            signal_id=order.signal_id,
            broker_position_id=str(uuid4()),
            is_open=True,
        )
        self._positions.append(position)

        order.broker_order_id = position.broker_position_id
        order.status = OrderStatus.FILLED

        logger.info(
            "PaperBroker: filled %s %s @ %.5f vol=%.2f commission=%.2f",
            order.direction.value,
            order.instrument_symbol,
            fill_price,
            order.volume,
            commission,
        )
        return order

    async def cancel_order(self, order_id: UUID) -> None:
        logger.info("PaperBroker: cancel_order %s (no-op for market orders)", order_id)

    async def fetch_positions(self, symbol: str | None = None) -> list[Position]:
        if symbol:
            return [p for p in self._positions if p.instrument_symbol == symbol and p.is_open]
        return [p for p in self._positions if p.is_open]

    async def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        return await self.fetch_positions(symbol)

    async def close_position(self, position: Position) -> Position:
        fill_price = self._apply_slippage(
            Direction.SELL if position.side == Direction.BUY else Direction.BUY
        )

        multiplier = 1.0 if position.side == Direction.BUY else -1.0
        pnl = multiplier * (fill_price - position.entry_price) * position.volume * 100_000.0

        self._balance += pnl
        position.is_open = False

        logger.info(
            "PaperBroker: closed %s @ %.5f PnL=%.2f balance=%.2f",
            position.instrument_symbol,
            fill_price,
            pnl,
            self._balance,
        )
        return position

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _apply_slippage(self, direction: Direction) -> float:
        """Apply spread + slippage to the current price."""
        price = self._current_price
        if direction == Direction.BUY:
            return price + self._spread + self._slippage
        return price - self._slippage
