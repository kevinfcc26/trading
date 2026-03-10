"""SignalAggregator — preserved and migrated from legacy domain/services/."""
from __future__ import annotations

from .entities import AggregatedSignal, Direction, Signal, SignalSource


def _direction_score(direction: Direction, confidence: float) -> float:
    """Map (direction, confidence) → signed score: BUY=+conf, SELL=-conf, HOLD=0."""
    if direction == Direction.BUY:
        return confidence
    if direction == Direction.SELL:
        return -confidence
    return 0.0


class SignalAggregator:
    """Combines TA, ML, and Claude signals using weighted voting + Claude veto."""

    def __init__(
        self,
        weight_ta: float = 0.25,
        weight_ml: float = 0.35,
        weight_claude: float = 0.40,
        min_threshold: float = 0.60,
        claude_veto_threshold: float = 0.70,
    ) -> None:
        total = weight_ta + weight_ml + weight_claude
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        self.weight_ta = weight_ta
        self.weight_ml = weight_ml
        self.weight_claude = weight_claude
        self.min_threshold = min_threshold
        self.claude_veto_threshold = claude_veto_threshold

    def aggregate(
        self,
        ta_signal: Signal,
        ml_signal: Signal,
        claude_signal: Signal,
    ) -> AggregatedSignal:
        # Weighted vote
        score = (
            _direction_score(ta_signal.direction, ta_signal.confidence) * self.weight_ta
            + _direction_score(ml_signal.direction, ml_signal.confidence) * self.weight_ml
            + _direction_score(claude_signal.direction, claude_signal.confidence) * self.weight_claude
        )

        if score > 0:
            consensus_direction = Direction.BUY
        elif score < 0:
            consensus_direction = Direction.SELL
        else:
            consensus_direction = Direction.HOLD

        consensus_confidence = abs(score)
        override_reason = ""

        # Claude VETO: Claude is confident and disagrees with consensus
        if (
            claude_signal.confidence >= self.claude_veto_threshold
            and claude_signal.direction != consensus_direction
            and claude_signal.direction != Direction.HOLD
        ):
            override_reason = (
                f"Claude VETO: confidence={claude_signal.confidence:.2f} "
                f"overrides consensus={consensus_direction.value}"
            )
            final_direction = claude_signal.direction
            final_confidence = claude_signal.confidence
        else:
            final_direction = consensus_direction
            final_confidence = consensus_confidence

        # Below actionable threshold → HOLD
        if final_confidence < self.min_threshold:
            final_direction = Direction.HOLD

        return AggregatedSignal(
            instrument_symbol=ta_signal.instrument_symbol,
            timeframe=ta_signal.timeframe,
            direction=final_direction,
            confidence=final_confidence,
            source=SignalSource.AGGREGATED,
            reasoning=claude_signal.reasoning,
            component_signals=[ta_signal, ml_signal, claude_signal],
            override_reason=override_reason,
        )
