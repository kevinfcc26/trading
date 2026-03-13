"""Feature engineering for XGBoost model training."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Single source of truth for feature column order — imported by ml_strategy.py
FEATURE_NAMES: list[str] = [
    "rsi_14",       # RSI momentum oscillator (0–100)
    "rsi_slope",    # RSI 5-bar slope — direction of momentum
    "ema_diff",     # EMA20 - EMA50 — short-term trend
    "ema200_dist",  # (close - EMA200) / close — macro trend distance
    "macd",         # MACD value
    "macd_signal",  # MACD signal line
    "macd_hist",    # MACD histogram (acceleration)
    "bb_width",     # BB upper - lower (volatility)
    "bb_pos",       # (close - BBL) / bb_width — position within bands
    "atr_14",       # Average True Range (raw volatility)
    "body_ratio",   # (close - open) / (high - low) — candle strength
    "volume_ratio", # volume / 20-bar avg volume — relative activity
    "hour",         # hour of day 0–23 — session context
    "ret_1",        # 1-bar return — immediate momentum
    "ret_3",        # 3-bar return — short momentum
    "ret_5",        # 5-bar return — medium momentum
    "trend_5",      # fraction of last 5 bars bullish (-1 to +1)
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

        # Compute indicators
        work.ta.rsi(length=14, append=True)
        work.ta.macd(append=True)
        work.ta.ema(length=20, append=True)
        work.ta.ema(length=50, append=True)
        work.ta.ema(length=200, append=True)
        work.ta.bbands(length=20, append=True)
        work.ta.atr(length=14, percent=False, append=True)

        # Build derived columns
        work["rsi_14"] = work["RSI_14"]
        work["rsi_slope"] = (work["RSI_14"] - work["RSI_14"].shift(5)) / 5
        work["ema_diff"] = work["EMA_20"] - work["EMA_50"]
        work["ema200_dist"] = (work["close"] - work["EMA_200"]) / work["close"]
        work["macd"] = work["MACD_12_26_9"]
        work["macd_signal"] = work["MACDs_12_26_9"]
        work["macd_hist"] = work["MACD_12_26_9"] - work["MACDs_12_26_9"]
        work["bb_width"] = work["BBU_20_2.0_2.0"] - work["BBL_20_2.0_2.0"]
        work["bb_pos"] = (work["close"] - work["BBL_20_2.0_2.0"]) / (
            work["bb_width"] + 1e-10
        )
        work["atr_14"] = work["ATRr_14"]
        work["body_ratio"] = (work["close"] - work["open"]) / (
            work["high"] - work["low"] + 1e-10
        )
        vol_avg = work["volume"].rolling(20).mean()
        work["volume_ratio"] = work["volume"] / (vol_avg + 1e-10)

        # Hour of day — try datetime index first, then "time" column
        if hasattr(work.index, "hour"):
            work["hour"] = work.index.hour.astype(float)
        elif "time" in work.columns:
            work["hour"] = pd.to_datetime(work["time"]).dt.hour.astype(float)
        else:
            work["hour"] = 12.0

        # Price momentum — most predictive features for direction
        work["ret_1"] = work["close"].pct_change(1)
        work["ret_3"] = work["close"].pct_change(3)
        work["ret_5"] = work["close"].pct_change(5)
        # Trend consistency: fraction of last 5 bars that closed above open
        work["trend_5"] = (
            (work["close"] > work["open"]).rolling(5).mean() * 2 - 1  # -1 to +1
        )

        features = work[FEATURE_NAMES].dropna()
        logger.debug("Feature matrix: %d rows, %d cols", len(features), len(features.columns))
        return features

    def generate_labels(
        self,
        df: pd.DataFrame,
        horizon: int = 5,
        threshold: float = 0.0015,
    ) -> pd.Series:
        """Generate 3-class labels from forward returns.

        Classes: 0=SELL, 1=HOLD, 2=BUY.
        Last `horizon` rows are excluded to avoid lookahead leakage.
        Default threshold=0.0015 (~15 pips on EURUSD H1) filters noise.
        """
        close = df["close"] if "close" in df.columns else df["Close"]
        forward_return = (close.shift(-horizon) - close) / close

        forward_return = forward_return.iloc[:-horizon]

        labels = pd.Series(1, index=forward_return.index, dtype=int)
        labels[forward_return > threshold] = 2   # BUY
        labels[forward_return < -threshold] = 0  # SELL

        return labels
