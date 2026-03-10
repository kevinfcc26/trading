"""Trading application use cases."""
from __future__ import annotations

import logging
from uuid import UUID

from events.bus.event_bus import EventBus
from events.trading_events import PositionClosed, PositionOpened, TradeCompleted
from trading.domain.entities import Direction, Order, OrderStatus, Position, Trade
from trading.domain.ports import TradeRepository
from trading.domain.services import calculate_pnl

logger = logging.getLogger(__name__)


class OpenTradeUseCase:
    """Create a Trade record when an order is filled."""

    def __init__(
        self,
        trade_repository: TradeRepository,
        event_bus: EventBus,
    ) -> None:
        self._repo = trade_repository
        self._bus = event_bus

    async def execute(self, order: Order, fill_price: float) -> Trade:
        trade = Trade(
            instrument_symbol=order.instrument_symbol,
            side=order.direction,
            volume=order.volume,
            entry_price=fill_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            signal_id=order.signal_id,
        )
        await self._repo.save(trade)

        await self._bus.publish(
            PositionOpened(
                position_id=trade.id,
                symbol=trade.instrument_symbol,
                direction=trade.side.value,
                volume=trade.volume,
                entry_price=fill_price,
            )
        )
        logger.info("Trade opened: %s %s @ %.5f", trade.side, trade.instrument_symbol, fill_price)
        return trade


class CloseTradeUseCase:
    """Close a trade and record realized PnL."""

    def __init__(
        self,
        trade_repository: TradeRepository,
        event_bus: EventBus,
    ) -> None:
        self._repo = trade_repository
        self._bus = event_bus

    async def execute(self, trade: Trade, exit_price: float) -> Trade:
        from datetime import datetime

        pnl = calculate_pnl(trade.side, trade.entry_price, exit_price, trade.volume)
        trade.exit_price = exit_price
        trade.realized_pnl = pnl
        trade.closed_at = datetime.utcnow()

        await self._repo.save(trade)

        await self._bus.publish(
            TradeCompleted(
                trade_id=trade.id,
                symbol=trade.instrument_symbol,
                direction=trade.side.value,
                volume=trade.volume,
                entry_price=trade.entry_price,
                exit_price=exit_price,
                realized_pnl=pnl,
                commission=trade.commission,
                swap=trade.swap,
            )
        )
        logger.info("Trade closed: %s PnL=%.2f", trade.instrument_symbol, pnl)
        return trade


class GetPortfolioUseCase:
    """Return a summary of current open trades."""

    def __init__(self, trade_repository: TradeRepository) -> None:
        self._repo = trade_repository

    async def execute(self, symbol: str | None = None) -> list[Trade]:
        return await self._repo.get_open_trades(symbol)
