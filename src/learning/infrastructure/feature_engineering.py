"""Feature engineering for XGBoost model training."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Single source of truth for feature column order — imported by ml_strategy.py
FEATURE_NAMES: list[str] = [
    "rsi_14",
    "ema_diff",
    "macd",
    "macd_signal",
    "bb_width",
    "close",
    "volume",
]

_REQUIRED_OHLCV = {"open", "high", "low", "close", "volume"}


class FeatureEngineer:
    """Transforms raw OHLCV DataFrames into model-ready features and labels."""

    def load_csv(self, path: str | Path) -> pd.DataFrame:
        """Load OHLCV CSV.  Raises FileNotFoundError or ValueError on bad input."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Training data not found: {p}")

        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]

        missing = _REQUIRED_OHLCV - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        return df

    def build_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute technical indicators and return a clean feature DataFrame.

        Returns columns in FEATURE_NAMES order with all NaN rows dropped.
        """
        import pandas_ta as ta  # type: ignore[import]

        work = df.copy()
        work.columns = [c.lower() for c in work.columns]

        # Compute indicators using pandas_ta
        work.ta.rsi(length=14, append=True)
        work.ta.macd(append=True)
        work.ta.ema(length=20, append=True)
        work.ta.ema(length=50, append=True)
        work.ta.bbands(length=20, append=True)

        # Build derived columns
        work["rsi_14"] = work["RSI_14"]
        work["ema_diff"] = work["EMA_20"] - work["EMA_50"]
        work["macd"] = work["MACD_12_26_9"]
        work["macd_signal"] = work["MACDs_12_26_9"]
        work["bb_width"] = work["BBU_20_2.0_2.0"] - work["BBL_20_2.0_2.0"]
        # "close" and "volume" already lowercase

        features = work[FEATURE_NAMES].dropna()
        logger.debug("Feature matrix: %d rows, %d cols", len(features), len(features.columns))
        return features

    def generate_labels(
        self,
        df: pd.DataFrame,
        horizon: int = 5,
        threshold: float = 0.0002,
    ) -> pd.Series:
        """Generate 3-class labels from forward returns.

        Classes: 0=SELL, 1=HOLD, 2=BUY.
        Last `horizon` rows are excluded to avoid lookahead leakage.
        """
        close = df["close"] if "close" in df.columns else df["Close"]
        forward_return = (close.shift(-horizon) - close) / close

        # Drop last `horizon` rows (NaN forward return)
        forward_return = forward_return.iloc[:-horizon]

        labels = pd.Series(1, index=forward_return.index, dtype=int)
        labels[forward_return > threshold] = 2   # BUY
        labels[forward_return < -threshold] = 0  # SELL

        return labels
