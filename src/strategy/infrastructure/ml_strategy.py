"""MLStrategy — wraps XGBoost model into the StrategyPort."""
from __future__ import annotations

import logging
from pathlib import Path

import joblib  # type: ignore[import]
import numpy as np

from learning.infrastructure.feature_engineering import FEATURE_NAMES
from market.domain.entities import CandleSeries
from strategy.domain.entities import Direction, Signal, SignalSource

logger = logging.getLogger(__name__)

_CLASS_TO_DIRECTION = {0: Direction.SELL, 1: Direction.HOLD, 2: Direction.BUY}


def _extract_features(candles: CandleSeries) -> np.ndarray:
    """Extract features matching FEATURE_NAMES exactly — mirrors FeatureEngineer."""
    import pandas_ta as ta  # type: ignore[import]

    df = candles.to_dataframe()

    # Compute indicators
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.bbands(length=20, append=True)
    df.ta.atr(length=14, percent=False, append=True)

    last = df.iloc[-1]
    close = float(last["close"])
    ema200 = float(last.get("EMA_200", close))
    bb_upper = float(last.get("BBU_20_2.0_2.0", close * 1.01))
    bb_lower = float(last.get("BBL_20_2.0_2.0", close * 0.99))
    bb_width = bb_upper - bb_lower

    rsi_now = float(last.get("RSI_14", 50))
    rsi_5ago = float(df["RSI_14"].iloc[-6]) if len(df) >= 6 else rsi_now

    vol = float(last.get("volume", 0))
    vol_avg = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else (vol or 1.0)

    high = float(last["high"])
    low_ = float(last["low"])
    open_ = float(last["open"])
    candle_range = (high - low_) or 1e-10

    hour = float(df.index[-1].hour) if hasattr(df.index[-1], "hour") else 12.0

    macd = float(last.get("MACD_12_26_9", 0))
    macd_sig = float(last.get("MACDs_12_26_9", 0))

    # Momentum: lagged returns and trend consistency
    closes = df["close"]
    ret_1 = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2]) if len(df) >= 2 else 0.0
    ret_3 = float((closes.iloc[-1] - closes.iloc[-4]) / closes.iloc[-4]) if len(df) >= 4 else 0.0
    ret_5 = float((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6]) if len(df) >= 6 else 0.0
    opens = df["open"]
    trend_5 = float(
        ((closes.iloc[-5:] > opens.iloc[-5:]).mean() * 2 - 1) if len(df) >= 5 else 0.0
    )

    # Must match FEATURE_NAMES order exactly
    features = np.array([
        rsi_now,                                        # rsi_14
        (rsi_now - rsi_5ago) / 5,                       # rsi_slope
        float(last.get("EMA_20", close)) - float(last.get("EMA_50", close)),  # ema_diff
        (close - ema200) / close,                       # ema200_dist
        macd,                                           # macd
        macd_sig,                                       # macd_signal
        macd - macd_sig,                                # macd_hist
        bb_width,                                       # bb_width
        (close - bb_lower) / (bb_width + 1e-10),        # bb_pos
        float(last.get("ATRr_14", 0)),                  # atr_14
        (close - open_) / candle_range,                 # body_ratio
        vol / (vol_avg + 1e-10),                        # volume_ratio
        hour,                                           # hour
        ret_1,                                          # ret_1
        ret_3,                                          # ret_3
        ret_5,                                          # ret_5
        trend_5,                                        # trend_5
    ], dtype=float).reshape(1, -1)

    return features


class MLStrategy:
    def __init__(self, model_path: str | Path) -> None:
        self._model_path = Path(model_path)
        if not self._model_path.exists():
            raise FileNotFoundError(f"ML model not found: {self._model_path}")
        self._model = None

    def _load_model(self):
        if self._model is None:
            logger.info("Loading ML model from %s", self._model_path)
            self._model = joblib.load(self._model_path)
        return self._model

    async def generate(self, candles: CandleSeries, **kwargs) -> Signal:
        model = self._load_model()
        features = _extract_features(candles)

        probas = model.predict_proba(features)[0]
        class_idx = int(np.argmax(probas))
        direction = _CLASS_TO_DIRECTION[class_idx]
        confidence = float(probas[class_idx])

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=direction,
            confidence=confidence,
            source=SignalSource.ML,
            context={
                "proba_sell": float(probas[0]),
                "proba_hold": float(probas[1]),
                "proba_buy": float(probas[2]),
            },
        )
