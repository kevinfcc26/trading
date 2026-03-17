"""DryRunBrokerAdapter — real market data from MT5, simulated order execution.

Use this instead of PaperBrokerAdapter when you want a dry-run that reflects
real market conditions (candles, prices, account balance) while never sending
real orders to the broker.

Data path  : MT5Adapter  (get_candles, get_balance, get_current_price)
Order path : PaperBrokerAdapter (submit_order, close_position, positions)
"""
from __future__ import annotations

import logging
from uuid import UUID

from market.domain.entities import CandleSeries
from market.domain.value_objects import Timeframe
from trading.domain.entities import Order, Position

logger = logging.getLogger(__name__)


class DryRunBrokerAdapter:
    """Satisfies BrokerPort + MarketDataPort structurally."""

    def __init__(self, mt5_adapter, paper_adapter) -> None:
        self._mt5 = mt5_adapter
        self._paper = paper_adapter

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        await self._mt5.connect()
        await self._paper.connect()
        logger.info("DryRunBroker connected — real data, simulated fills")

    async def disconnect(self) -> None:
        await self._mt5.disconnect()
        await self._paper.disconnect()

    async def is_connected(self) -> bool:
        return await self._mt5.is_connected()

    # ── Market data — delegated to MT5 (real) ─────────────────────────────────

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, count: int = 200
    ) -> CandleSeries:
        return await self._mt5.get_candles(symbol, timeframe, count)

    async def get_current_price(self, symbol: str) -> float:
        return await self._mt5.get_current_price(symbol)

    # ── Account data — real MT5 balance (read-only) ───────────────────────────

    async def get_balance(self) -> float:
        return await self._mt5.get_balance()

    async def get_account_balance(self) -> float:
        return await self._mt5.get_balance()

    # ── Order execution — delegated to Paper (simulated) ─────────────────────

    async def submit_order(self, order: Order) -> Order:
        return await self._paper.submit_order(order)

    async def cancel_order(self, order_id: UUID) -> None:
        return await self._paper.cancel_order(order_id)

    async def fetch_positions(self, symbol: str | None = None) -> list[Position]:
        return await self._paper.fetch_positions(symbol)

    async def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        return await self._paper.get_open_positions(symbol)

    async def close_position(self, position: Position) -> Position:
        return await self._paper.close_position(position)

    def set_current_price(self, price: float) -> None:
        """Keep paper adapter price in sync with the last real MT5 price."""
        self._paper.set_current_price(price)
