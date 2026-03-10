"""TradingEnv — Gymnasium RL environment for training trading agents.

Observation space: [open, high, low, close, volume, rsi, macd, ema_diff]  (last N bars)
Action space: Discrete(3) → 0=SELL, 1=HOLD, 2=BUY

Reward: realized PnL per step, penalized for over-trading.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_WINDOW = 20   # bars in observation window
_FEATURES = 8  # per bar: open, high, low, close, volume, rsi, macd, ema_diff


def _try_import_gymnasium():
    try:
        import gymnasium as gym  # type: ignore[import]
        return gym
    except ImportError:
        raise ImportError(
            "gymnasium is required for RL training: pip install gymnasium"
        )


class TradingEnv:
    """Gymnasium-compatible trading environment for Forex.

    Usage:
        env = TradingEnv(candles_df)
        obs, info = env.reset()
        while True:
            action = policy(obs)       # 0=SELL, 1=HOLD, 2=BUY
            obs, reward, done, trunc, info = env.step(action)
            if done: break
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        candles_df,       # pd.DataFrame with columns: open, high, low, close, volume
        window: int = _WINDOW,
        initial_balance: float = 10_000.0,
        commission_pct: float = 0.0001,
        max_position_size: float = 0.01,  # lots
    ) -> None:
        gym = _try_import_gymnasium()

        self._df = candles_df.reset_index(drop=True)
        self._window = window
        self._initial_balance = initial_balance
        self._commission_pct = commission_pct
        self._max_lot = max_position_size

        n_features = window * _FEATURES
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(3)

        self._step_idx: int = 0
        self._balance: float = initial_balance
        self._position: int = 0       # -1=short, 0=flat, 1=long
        self._entry_price: float = 0.0
        self._total_trades: int = 0

    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict]:
        self._step_idx = self._window
        self._balance = self._initial_balance
        self._position = 0
        self._entry_price = 0.0
        self._total_trades = 0
        return self._observe(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        row = self._df.iloc[self._step_idx]
        price = float(row["close"])
        reward = 0.0

        # Close existing position
        if self._position != 0:
            pnl = self._position * (price - self._entry_price) * self._max_lot * 100_000.0
            pnl -= abs(price * self._commission_pct * self._max_lot * 100_000.0)
            self._balance += pnl
            reward = pnl / self._initial_balance   # normalised reward
            self._position = 0

        # Open new position based on action
        desired = action - 1  # 0→-1, 1→0, 2→1
        if desired != 0:
            self._position = desired
            self._entry_price = price
            self._total_trades += 1
            # Small penalty for over-trading
            reward -= 0.0001

        self._step_idx += 1
        done = self._step_idx >= len(self._df)
        truncated = False

        obs = self._observe() if not done else np.zeros(self._window * _FEATURES, dtype=np.float32)
        info = {"balance": self._balance, "total_trades": self._total_trades}
        return obs, reward, done, truncated, info

    def _observe(self) -> np.ndarray:
        """Build an observation vector from the last _window bars."""
        start = self._step_idx - self._window
        window_df = self._df.iloc[start : self._step_idx].copy()

        # Simple feature extraction — mirrors MLStrategy feature set
        closes = window_df["close"].values.astype(np.float64)
        opens = window_df["open"].values.astype(np.float64)
        highs = window_df["high"].values.astype(np.float64)
        lows = window_df["low"].values.astype(np.float64)
        volumes = window_df["volume"].values.astype(np.float64)

        # Normalise by last close
        last_close = closes[-1] if closes[-1] != 0 else 1.0
        norm_close = closes / last_close - 1
        norm_open = opens / last_close - 1
        norm_high = highs / last_close - 1
        norm_low = lows / last_close - 1
        norm_volume = volumes / (volumes.mean() + 1e-10) - 1

        # RSI (simplified)
        delta = np.diff(closes, prepend=closes[0])
        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)
        avg_gain = np.convolve(gains, np.ones(14) / 14, mode="same")
        avg_loss = np.convolve(losses, np.ones(14) / 14, mode="same")
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = (100 - 100 / (1 + rs)) / 100 - 0.5  # centred

        # EMA diff
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        ema_diff = (ema20 - ema50) / last_close

        # MACD
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        macd = (ema12 - ema26) / last_close

        features = np.stack([
            norm_open, norm_high, norm_low, norm_close, norm_volume, rsi, macd, ema_diff
        ], axis=1).flatten().astype(np.float32)

        return features


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Simple EMA using exponential smoothing."""
    k = 2 / (period + 1)
    ema = np.zeros_like(values)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = values[i] * k + ema[i - 1] * (1 - k)
    return ema
