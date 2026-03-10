"""
Feature extraction pipeline for the XGBoost model.
Input: CandleSeries  →  Output: numpy feature array (1 row = latest candle).
"""
import numpy as np
import pandas as pd
import pandas_ta as ta  # type: ignore[import]

from domain.entities import CandleSeries

FEATURE_NAMES = [
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_pct",
    "ema_20",
    "ema_50",
    "ema_ratio",
    "returns_1",
    "returns_5",
    "returns_10",
    "volume_ratio",
    "atr_14",
    "close_vs_ema20",
    "close_vs_ema50",
]


def extract_features(candles: CandleSeries) -> np.ndarray:
    """Return a 2-D array shaped (1, n_features) for the latest candle."""
    df = candles.to_dataframe().copy()

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.bbands(length=20, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.atr(length=14, append=True)

    df["returns_1"] = df["close"].pct_change(1)
    df["returns_5"] = df["close"].pct_change(5)
    df["returns_10"] = df["close"].pct_change(10)
    df["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

    last = df.iloc[-1]
    close = float(last["close"])
    bb_upper = float(last.get("BBU_20_2.0", close * 1.01))
    bb_lower = float(last.get("BBL_20_2.0", close * 0.99))
    bb_range = bb_upper - bb_lower if bb_upper != bb_lower else 1.0
    ema20 = float(last.get("EMA_20", close))
    ema50 = float(last.get("EMA_50", close))

    features = [
        float(last.get("RSI_14", 50)),
        float(last.get("MACD_12_26_9", 0)),
        float(last.get("MACDs_12_26_9", 0)),
        float(last.get("MACDh_12_26_9", 0)),
        (close - bb_lower) / bb_range,
        ema20,
        ema50,
        ema20 / ema50 if ema50 else 1.0,
        float(last.get("returns_1", 0)),
        float(last.get("returns_5", 0)),
        float(last.get("returns_10", 0)),
        float(last.get("volume_ratio", 1)),
        float(last.get("ATRr_14", 0)),
        (close - ema20) / ema20 if ema20 else 0.0,
        (close - ema50) / ema50 if ema50 else 0.0,
    ]

    return np.array([features], dtype=np.float32)
