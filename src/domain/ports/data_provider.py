from abc import ABC, abstractmethod

from ..entities import CandleSeries
from ..value_objects import Timeframe


class IDataProvider(ABC):
    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int = 200,
    ) -> CandleSeries: ...

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float: ...
