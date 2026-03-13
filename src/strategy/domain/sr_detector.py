"""SRDetector — swing-based Support/Resistance detection.

Pure domain service: operates only on OHLC price lists (floats).
No pandas, no external dependencies.
"""
from __future__ import annotations

import logging

from market.domain.entities import CandleSeries
from market.domain.value_objects import Timeframe
from strategy.domain.value_objects import SRContext, SupportResistanceLevel

logger = logging.getLogger(__name__)


class SRDetector:
    """Detects swing-based S/R levels from a CandleSeries.

    Algorithm:
    1. Find swing highs (local maxima) and swing lows (local minima)
    2. Cluster nearby price levels (within tolerance_pct)
    3. Score each cluster by touch count and recency
    4. Filter to top max_levels by strength
    5. Classify as support/resistance/both based on proximity to current price
    """

    def __init__(
        self,
        swing_window: int = 5,
        tolerance_pct: float = 0.001,   # 0.1% = ~10 pips on EURUSD
        max_levels: int = 8,
        min_touches: int = 2,
        rr_min: float = 2.0,
        at_level_tolerance_pct: float = 0.0005,  # 5 pips
    ) -> None:
        self._swing_window = swing_window
        self._tolerance_pct = tolerance_pct
        self._max_levels = max_levels
        self._min_touches = min_touches
        self._rr_min = rr_min
        self._at_level_tolerance = at_level_tolerance_pct

    def detect(self, candles: CandleSeries, current_price: float) -> SRContext:
        highs = [c.high for c in candles.candles]
        lows = [c.low for c in candles.candles]
        closes = [c.close for c in candles.candles]
        n = len(highs)

        if n < self._swing_window * 2 + 1:
            return self._empty_context(candles.instrument_symbol, current_price, candles.timeframe)

        swing_highs = self._find_swings(highs, is_high=True)
        swing_lows = self._find_swings(lows, is_high=False)

        # Add psychological round numbers
        round_levels = self._round_number_levels(current_price)

        # Cluster and score
        raw_levels = self._cluster_and_score(
            swing_highs, swing_lows, round_levels, closes, n, candles.timeframe
        )

        # Filter by min_touches and sort by strength desc
        raw_levels = [lv for lv in raw_levels if lv.touch_count >= self._min_touches]
        raw_levels.sort(key=lambda lv: lv.strength, reverse=True)
        levels = tuple(raw_levels[: self._max_levels])

        # Classify nearest support/resistance
        resistances = sorted(
            [lv for lv in levels if lv.price > current_price],
            key=lambda lv: lv.price,
        )
        supports = sorted(
            [lv for lv in levels if lv.price <= current_price],
            key=lambda lv: lv.price,
            reverse=True,
        )

        nearest_resistance = resistances[0] if resistances else None
        nearest_support = supports[0] if supports else None

        tolerance = current_price * self._at_level_tolerance
        at_resistance = nearest_resistance is not None and (
            nearest_resistance.price - current_price
        ) <= tolerance
        at_support = nearest_support is not None and (
            current_price - nearest_support.price
        ) <= tolerance

        pip_to_support = (
            (current_price - nearest_support.price) if nearest_support else 0.0
        )
        pip_to_resistance = (
            (nearest_resistance.price - current_price) if nearest_resistance else 0.0
        )

        # R:R viable per direction:
        # BUY:  reward = pip_to_resistance, risk = pip_to_support  → R:R = res/sup
        # SELL: reward = pip_to_support,    risk = pip_to_resistance → R:R = sup/res
        # rr_viable = True if EITHER direction gives acceptable R:R
        rr_viable = False
        if nearest_support and nearest_resistance and pip_to_support > 0 and pip_to_resistance > 0:
            buy_rr = pip_to_resistance / pip_to_support
            sell_rr = pip_to_support / pip_to_resistance
            rr_viable = buy_rr >= self._rr_min or sell_rr >= self._rr_min

        return SRContext(
            symbol=candles.instrument_symbol,
            current_price=current_price,
            levels=levels,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            at_support=at_support,
            at_resistance=at_resistance,
            rr_viable=rr_viable,
            pip_to_support=pip_to_support,
            pip_to_resistance=pip_to_resistance,
        )

    def _find_swings(self, prices: list[float], is_high: bool) -> list[tuple[int, float]]:
        """Return (bar_index, price) for each swing high or low."""
        w = self._swing_window
        swings = []
        for i in range(w, len(prices) - w):
            window = prices[i - w : i + w + 1]
            if is_high and prices[i] == max(window):
                swings.append((i, prices[i]))
            elif not is_high and prices[i] == min(window):
                swings.append((i, prices[i]))
        return swings

    def _cluster_and_score(
        self,
        swing_highs: list[tuple[int, float]],
        swing_lows: list[tuple[int, float]],
        round_levels: list[float],
        closes: list[float],
        total_bars: int,
        timeframe: Timeframe,
    ) -> list[SupportResistanceLevel]:
        # Combine all price points
        all_points: list[tuple[int, float, str]] = []
        for idx, price in swing_highs:
            all_points.append((idx, price, "resistance"))
        for idx, price in swing_lows:
            all_points.append((idx, price, "support"))
        for price in round_levels:
            all_points.append((total_bars - 1, price, "both"))  # recency = now

        if not all_points:
            return []

        # Sort by price
        all_points.sort(key=lambda x: x[1])

        # Cluster nearby levels
        clusters: list[list[tuple[int, float, str]]] = []
        current_cluster: list[tuple[int, float, str]] = [all_points[0]]

        for point in all_points[1:]:
            ref_price = current_cluster[0][1]
            if abs(point[1] - ref_price) / ref_price <= self._tolerance_pct:
                current_cluster.append(point)
            else:
                clusters.append(current_cluster)
                current_cluster = [point]
        clusters.append(current_cluster)

        levels = []
        for cluster in clusters:
            cluster_price = sum(p for _, p, _ in cluster) / len(cluster)
            touch_count = len(cluster)
            # Recency: most recent touch index in cluster
            last_touch_idx = max(idx for idx, _, _ in cluster)
            recency_weight = 0.5 + 0.5 * (last_touch_idx / total_bars)
            strength = min(1.0, (touch_count / 5.0) * recency_weight)

            # Classify: majority type in cluster
            types = [t for _, _, t in cluster]
            type_counts = {t: types.count(t) for t in set(types)}
            level_type = max(type_counts, key=type_counts.get)

            levels.append(
                SupportResistanceLevel(
                    price=round(cluster_price, 5),
                    strength=round(strength, 4),
                    level_type=level_type,
                    timeframe=timeframe,
                    touch_count=touch_count,
                )
            )
        return levels

    def _round_number_levels(self, current_price: float) -> list[float]:
        """Return the nearest 00 and 50 pip levels around current price."""
        # For EURUSD at 1.0873 → 1.0850, 1.0900
        base = round(current_price * 100) / 100  # round to 2 decimal places
        step = 0.005  # 50 pips
        levels = []
        for multiplier in range(-3, 4):
            level = round(base + multiplier * step, 5)
            if level > 0:
                levels.append(level)
        return levels

    def _empty_context(
        self, symbol: str, current_price: float, timeframe: Timeframe
    ) -> SRContext:
        return SRContext(
            symbol=symbol,
            current_price=current_price,
            levels=(),
            nearest_support=None,
            nearest_resistance=None,
            at_support=False,
            at_resistance=False,
            rr_viable=False,
            pip_to_support=0.0,
            pip_to_resistance=0.0,
        )
