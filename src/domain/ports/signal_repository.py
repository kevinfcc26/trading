from abc import ABC, abstractmethod
from uuid import UUID

from ..entities import AggregatedSignal


class ISignalRepository(ABC):
    @abstractmethod
    async def save(self, signal: AggregatedSignal) -> AggregatedSignal: ...

    @abstractmethod
    async def get_by_id(self, signal_id: UUID) -> AggregatedSignal | None: ...
