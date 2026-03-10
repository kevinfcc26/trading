"""Template for developing and testing custom indicators.

Copy this file and implement your indicator logic.
No infrastructure dependencies are allowed here.

Once validated, promote to strategy/infrastructure/<your_strategy>.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class CustomIndicatorTemplate:
    """Template: implement your indicator here.

    Input: pd.DataFrame with columns: open, high, low, close, volume (indexed by time)
    Output: pd.Series with the indicator values (same index)
    """

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the indicator and return a Series aligned with df.index."""
        # --- YOUR IMPLEMENTATION HERE ---
        # Example: simple momentum
        return df["close"].pct_change(self.period)

    def signal(self, df: pd.DataFrame, threshold: float = 0.0) -> pd.Series:
        """Return +1 (buy), -1 (sell), or 0 (hold) for each bar."""
        values = self.compute(df)
        result = pd.Series(0, index=df.index)
        result[values > threshold] = 1
        result[values < -threshold] = -1
        return result


def backtest_indicator(
    df: pd.DataFrame,
    indicator: CustomIndicatorTemplate,
    initial_balance: float = 10_000.0,
) -> dict:
    """Quick backtest of an indicator signal on OHLCV data.

    Returns summary statistics without running the full BacktestEngine.
    Useful for rapid indicator research in notebooks.
    """
    signals = indicator.signal(df)
    pnl_series = []
    position = 0
    entry = 0.0

    for i in range(1, len(df)):
        sig = signals.iloc[i - 1]
        price = df["close"].iloc[i]

        if position != 0 and sig != position:
            # Close position
            pnl = position * (price - entry) * 10_000.0  # simplified 1-lot PnL in pips
            pnl_series.append(pnl)
            position = 0

        if sig != 0 and position == 0:
            position = sig
            entry = price

    wins = [p for p in pnl_series if p > 0]
    losses = [p for p in pnl_series if p <= 0]
    total_pnl = sum(pnl_series)

    return {
        "total_trades": len(pnl_series),
        "win_rate": len(wins) / len(pnl_series) if pnl_series else 0.0,
        "total_pnl_pips": total_pnl,
        "avg_win_pips": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss_pips": sum(losses) / len(losses) if losses else 0.0,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else float("inf"),
    }
