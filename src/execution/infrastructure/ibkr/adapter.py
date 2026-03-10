"""IBKRAdapter — stub for Interactive Brokers (not yet implemented)."""
from __future__ import annotations

import logging
from uuid import UUID

from trading.domain.entities import Order, Position

logger = logging.getLogger(__name__)


class IBKRAdapter:
    """Placeholder for future IBKR implementation via ib_insync."""

    async def connect(self) -> None:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def disconnect(self) -> None:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def is_connected(self) -> bool:
        return False

    async def get_balance(self) -> float:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def submit_order(self, order: Order) -> Order:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def cancel_order(self, order_id: UUID) -> None:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def fetch_positions(self, symbol: str | None = None) -> list[Position]:
        raise NotImplementedError("IBKRAdapter is not yet implemented")

    async def close_position(self, position: Position) -> Position:
        raise NotImplementedError("IBKRAdapter is not yet implemented")
