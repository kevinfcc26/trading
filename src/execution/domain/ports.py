"""BrokerPort — Protocol replacing the legacy IBroker ABC."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from trading.domain.entities import Order, Position


class BrokerPort(Protocol):
    """Structural protocol for all broker adapters.

    Concrete implementations:
    - MT5Adapter     (live trading via MetaTrader 5)
    - PaperBroker    (simulation / dry-run)
    - IBKRAdapter    (stub for Interactive Brokers)

    Any class that implements these methods satisfies BrokerPort
    without inheriting from it.
    """

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def is_connected(self) -> bool: ...

    async def get_balance(self) -> float: ...

    async def submit_order(self, order: Order) -> Order:
        """Submit an order. Returns the filled order."""
        ...

    async def cancel_order(self, order_id: UUID) -> None: ...

    async def fetch_positions(self, symbol: str | None = None) -> list[Position]: ...

    async def close_position(self, position: Position) -> Position: ...
