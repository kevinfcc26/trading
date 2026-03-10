from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from ..value_objects import Timeframe


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: Timeframe


@dataclass
class CandleSeries:
    instrument_symbol: str
    timeframe: Timeframe
    candles: list[Candle] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.candles:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "time": c.time,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in self.candles
            ]
        ).set_index("time")

    def __len__(self) -> int:
        return len(self.candles)
