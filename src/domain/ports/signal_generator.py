from abc import ABC, abstractmethod

from ..entities import CandleSeries, Signal


class ISignalGenerator(ABC):
    @abstractmethod
    async def generate(self, candles: CandleSeries) -> Signal: ...
