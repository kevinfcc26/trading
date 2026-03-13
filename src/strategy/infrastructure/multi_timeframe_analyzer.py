"""MultiTimeframeAnalyzer — fetches D1/H4/H1 candles and builds MultiTimeframeContext."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas_ta as ta  # type: ignore[import]

from market.domain.entities import CandleSeries
from market.domain.value_objects import Timeframe
from strategy.domain.entities import Direction
from strategy.domain.value_objects import MultiTimeframeContext, TimeframeAnalysis

logger = logging.getLogger(__name__)

_HIGHER_TF_MAP: dict[Timeframe, list[Timeframe]] = {
    Timeframe.M1:  [Timeframe.M15, Timeframe.H1,  Timeframe.H4],
    Timeframe.M5:  [Timeframe.H1,  Timeframe.H4,  Timeframe.D1],
    Timeframe.M15: [Timeframe.H1,  Timeframe.H4,  Timeframe.D1],
    Timeframe.H1:  [Timeframe.H4,  Timeframe.D1,  Timeframe.D1],  # H1 entry: H4 + D1
    Timeframe.H4:  [Timeframe.D1,  Timeframe.D1,  Timeframe.D1],
    Timeframe.D1:  [Timeframe.D1,  Timeframe.D1,  Timeframe.D1],
}


class MultiTimeframeAnalyzer:
    """Fetches candles for multiple timeframes and builds a MultiTimeframeContext.

    For H1 entry: D1 (macro trend) + H4 (swing structure) + H1 (momentum).
    """

    def __init__(self, broker) -> None:
        """broker: any object with async get_candles(symbol, timeframe, count) method."""
        self._broker = broker

    async def analyze(
        self, symbol: str, entry_timeframe: Timeframe
    ) -> MultiTimeframeContext:
        # Always fetch D1 and H4 as the higher timeframes
        d1_candles = await self._broker.get_candles(symbol, Timeframe.D1, count=200)
        h4_candles = await self._broker.get_candles(symbol, Timeframe.H4, count=200)
        h1_candles = await self._broker.get_candles(symbol, Timeframe.H1, count=200)

        d1_analysis = _analyze_trend(d1_candles)
        h4_analysis = _analyze_trend(h4_candles)
        h1_analysis = _analyze_trend(h1_candles)

        return MultiTimeframeContext(
            symbol=symbol,
            analysis_time=datetime.now(tz=timezone.utc),
            d1=d1_analysis,
            h4=h4_analysis,
            h1=h1_analysis,
        )


def _analyze_trend(candles: CandleSeries) -> TimeframeAnalysis:
    """Compute trend direction from EMA crossover + price structure."""
    if len(candles) < 60:
        last_close = candles.candles[-1].close if candles.candles else 0.0
        return TimeframeAnalysis(
            timeframe=candles.timeframe,
            trend=Direction.HOLD,
            trend_strength=0.0,
            ema_fast=last_close,
            ema_slow=last_close,
            close=last_close,
            candle_count=len(candles),
        )

    df = candles.to_dataframe()
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)

    last = df.iloc[-1]
    close = float(last["close"])
    ema_fast = float(last.get("EMA_20", close))
    ema_slow = float(last.get("EMA_50", close))

    # Trend direction from EMA crossover
    if ema_fast > ema_slow and close > ema_slow:
        trend = Direction.BUY
    elif ema_fast < ema_slow and close < ema_slow:
        trend = Direction.SELL
    else:
        trend = Direction.HOLD

    # Trend strength: how far EMA fast is from EMA slow (normalized)
    if ema_slow > 0:
        spread = abs(ema_fast - ema_slow) / ema_slow
        trend_strength = min(1.0, spread / 0.005)  # 0.5% spread = full strength
    else:
        trend_strength = 0.0

    return TimeframeAnalysis(
        timeframe=candles.timeframe,
        trend=trend,
        trend_strength=round(trend_strength, 4),
        ema_fast=round(ema_fast, 5),
        ema_slow=round(ema_slow, 5),
        close=round(close, 5),
        candle_count=len(candles),
    )
