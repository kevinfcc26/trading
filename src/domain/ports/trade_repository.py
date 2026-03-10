from abc import ABC, abstractmethod
from uuid import UUID

from ..entities import Trade


class ITradeRepository(ABC):
    @abstractmethod
    async def save(self, trade: Trade) -> Trade: ...

    @abstractmethod
    async def get_by_id(self, trade_id: UUID) -> Trade | None: ...

    @abstractmethod
    async def get_open_trades(self, symbol: str | None = None) -> list[Trade]: ...

    @abstractmethod
    async def update(self, trade: Trade) -> Trade: ...
