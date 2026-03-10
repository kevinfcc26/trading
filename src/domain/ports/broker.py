from abc import ABC, abstractmethod

from ..entities import Order, Position


class IBroker(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit an order. Returns the order with broker_order_id and FILLED status."""
        ...

    @abstractmethod
    async def get_open_positions(self, symbol: str | None = None) -> list[Position]: ...

    @abstractmethod
    async def close_position(self, position: Position) -> Position: ...

    @abstractmethod
    async def get_account_balance(self) -> float: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...
