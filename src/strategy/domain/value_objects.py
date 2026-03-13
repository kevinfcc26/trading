"""Strategy domain value objects — MultiTimeframeContext, SRContext."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market.domain.value_objects import Timeframe
from strategy.domain.entities import Direction
from shared_kernel.value_object import ValueObject


@dataclass(frozen=True)
class TimeframeAnalysis(ValueObject):
    timeframe: Timeframe
    trend: Direction          # BUY = uptrend, SELL = downtrend, HOLD = ranging
    trend_strength: float     # 0.0–1.0
    ema_fast: float
    ema_slow: float
    close: float
    candle_count: int


@dataclass(frozen=True)
class MultiTimeframeContext(ValueObject):
    symbol: str
    analysis_time: datetime
    d1: TimeframeAnalysis
    h4: TimeframeAnalysis
    h1: TimeframeAnalysis

    @property
    def trend_alignment(self) -> float:
        """0.0–1.0 — how many of D1/H4/H1 agree on the same non-HOLD direction."""
        directions = [self.d1.trend, self.h4.trend, self.h1.trend]
        non_hold = [d for d in directions if d != Direction.HOLD]
        if not non_hold:
            return 0.0
        majority = max(set(non_hold), key=non_hold.count)
        aligned = sum(1 for d in directions if d == majority)
        return aligned / 3.0

    @property
    def dominant_bias(self) -> Direction:
        """D1 drives the macro bias; HOLD only if D1 is ranging."""
        if self.d1.trend != Direction.HOLD:
            return self.d1.trend
        if self.h4.trend != Direction.HOLD:
            return self.h4.trend
        return Direction.HOLD


@dataclass(frozen=True)
class SupportResistanceLevel(ValueObject):
    price: float
    strength: float       # 0.0–1.0
    level_type: str       # "support" | "resistance" | "both"
    timeframe: Timeframe
    touch_count: int


@dataclass(frozen=True)
class SRContext(ValueObject):
    symbol: str
    current_price: float
    levels: tuple[SupportResistanceLevel, ...]
    nearest_support: SupportResistanceLevel | None
    nearest_resistance: SupportResistanceLevel | None
    at_support: bool
    at_resistance: bool
    rr_viable: bool          # nearest S and R give >= min_rr
    pip_to_support: float
    pip_to_resistance: float
