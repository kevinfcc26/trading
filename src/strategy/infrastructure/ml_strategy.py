"""MLStrategy — wraps MLModelAdapter into the new StrategyPort."""
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


def _extract_features(candles: CandleSeries):
    """Extract model features from CandleSeries — mirrors legacy feature_engineer."""
    import pandas_ta as ta  # type: ignore[import]

    df = candles.to_dataframe()
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.bbands(length=20, append=True)

    last = df.iloc[-1]
    close = float(last["close"])
    ema_fast = float(last.get("EMA_20", close))
    ema_slow = float(last.get("EMA_50", close))
    bb_upper = float(last.get("BBU_20_2.0", close * 1.01))
    bb_lower = float(last.get("BBL_20_2.0", close * 0.99))

    features = np.array(
        [
            float(last.get("RSI_14", 50)),
            ema_fast - ema_slow,
            float(last.get("MACD_12_26_9", 0)),
            float(last.get("MACDs_12_26_9", 0)),
            bb_upper - bb_lower,
            close,
            float(last.get("volume", 0)),
        ]
    ).reshape(1, -1)
    return features


class MLStrategy:
    def __init__(self, model_path: str | Path) -> None:
        self._model_path = Path(model_path)
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

        context = {
            "proba_sell": float(probas[0]),
            "proba_hold": float(probas[1]),
            "proba_buy": float(probas[2]),
        }

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=direction,
            confidence=confidence,
            source=SignalSource.ML,
            context=context,
        )
