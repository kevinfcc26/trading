"""TAStrategy — wraps the existing TASignalGenerator into the new StrategyPort."""
from __future__ import annotations

import logging

import pandas_ta as ta  # type: ignore[import]

from market.domain.entities import CandleSeries
from strategy.domain.entities import Direction, Signal, SignalSource

logger = logging.getLogger(__name__)

_MIN_CANDLES = 50


class TAStrategy:
    """Technical Analysis strategy using RSI, MACD, Bollinger Bands, EMA."""

    def __init__(
        self,
        rsi_period: int = 14,
        ema_fast: int = 20,
        ema_slow: int = 50,
        bb_period: int = 20,
    ) -> None:
        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.bb_period = bb_period

    async def generate(self, candles: CandleSeries, **kwargs) -> Signal:
        if len(candles) < _MIN_CANDLES:
            return Signal(
                instrument_symbol=candles.instrument_symbol,
                timeframe=candles.timeframe,
                direction=Direction.HOLD,
                confidence=0.0,
                source=SignalSource.TA,
                context={"error": "Not enough candles"},
            )

        df = candles.to_dataframe()
        df.ta.rsi(length=self.rsi_period, append=True)
        df.ta.macd(append=True)
        df.ta.bbands(length=self.bb_period, append=True)
        df.ta.ema(length=self.ema_fast, append=True)
        df.ta.ema(length=self.ema_slow, append=True)

        last = df.iloc[-1]

        rsi_col = f"RSI_{self.rsi_period}"
        ema_fast_col = f"EMA_{self.ema_fast}"
        ema_slow_col = f"EMA_{self.ema_slow}"
        macd_col = "MACD_12_26_9"
        macd_signal_col = "MACDs_12_26_9"
        bb_upper_col = f"BBU_{self.bb_period}_2.0"
        bb_lower_col = f"BBL_{self.bb_period}_2.0"

        rsi = float(last.get(rsi_col, 50))
        close = float(last["close"])
        ema_fast_val = float(last.get(ema_fast_col, close))
        ema_slow_val = float(last.get(ema_slow_col, close))
        macd_val = float(last.get(macd_col, 0))
        macd_sig = float(last.get(macd_signal_col, 0))
        bb_upper = float(last.get(bb_upper_col, close * 1.01))
        bb_lower = float(last.get(bb_lower_col, close * 0.99))

        buy_score = 0
        sell_score = 0
        total_conditions = 4

        if rsi < 30:
            buy_score += 1
        elif rsi > 70:
            sell_score += 1

        if ema_fast_val > ema_slow_val:
            buy_score += 1
        else:
            sell_score += 1

        if macd_val > macd_sig:
            buy_score += 1
        else:
            sell_score += 1

        if close <= bb_lower:
            buy_score += 1
        elif close >= bb_upper:
            sell_score += 1

        if buy_score > sell_score:
            direction = Direction.BUY
            confidence = buy_score / total_conditions
        elif sell_score > buy_score:
            direction = Direction.SELL
            confidence = sell_score / total_conditions
        else:
            direction = Direction.HOLD
            confidence = 0.0

        context = {
            "rsi": rsi,
            "ema_fast": ema_fast_val,
            "ema_slow": ema_slow_val,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "close": close,
        }

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=direction,
            confidence=confidence,
            source=SignalSource.TA,
            context=context,
        )
