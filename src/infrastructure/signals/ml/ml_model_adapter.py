"""
MLModelAdapter — wraps a trained XGBoost 3-class classifier.
Classes: 0=SELL, 1=HOLD, 2=BUY  (must match training label encoding)
"""
import logging
from pathlib import Path

import joblib  # type: ignore[import]
import numpy as np

from domain.entities import CandleSeries, Direction, Signal, SignalSource
from domain.ports import ISignalGenerator

from .feature_engineer import FEATURE_NAMES, extract_features

logger = logging.getLogger(__name__)

_CLASS_TO_DIRECTION = {0: Direction.SELL, 1: Direction.HOLD, 2: Direction.BUY}


class MLModelAdapter(ISignalGenerator):
    def __init__(self, model_path: str | Path) -> None:
        self._model_path = Path(model_path)
        self._model = None

    def _load_model(self):
        if self._model is None:
            logger.info("Loading ML model from %s", self._model_path)
            self._model = joblib.load(self._model_path)
        return self._model

    async def generate(self, candles: CandleSeries) -> Signal:
        model = self._load_model()
        features = extract_features(candles)

        probas = model.predict_proba(features)[0]   # shape (3,)
        class_idx = int(np.argmax(probas))
        direction = _CLASS_TO_DIRECTION[class_idx]
        confidence = float(probas[class_idx])

        context = {
            "proba_sell": float(probas[0]),
            "proba_hold": float(probas[1]),
            "proba_buy": float(probas[2]),
            "features": dict(zip(FEATURE_NAMES, features[0].tolist())),
        }

        return Signal(
            instrument_symbol=candles.instrument_symbol,
            timeframe=candles.timeframe,
            direction=direction,
            confidence=confidence,
            source=SignalSource.ML,
            context=context,
        )
