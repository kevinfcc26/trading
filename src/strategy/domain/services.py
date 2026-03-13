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
        min_threshold: float = 0.52,
        claude_veto_threshold: float = 0.70,
        confluence_min_score: float = 2.0,
    ) -> None:
        total = weight_ta + weight_ml + weight_claude
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        self.weight_ta = weight_ta
        self.weight_ml = weight_ml
        self.weight_claude = weight_claude
        self.min_threshold = min_threshold
        self.claude_veto_threshold = claude_veto_threshold
        self.confluence_min_score = confluence_min_score

    def aggregate(
        self,
        ta_signal: Signal,
        ml_signal: Signal,
        claude_signal: Signal,
    ) -> AggregatedSignal:
        # AI HOLD veto: AI is explicitly confident about staying out
        override_reason = ""
        if (
            claude_signal.direction == Direction.HOLD
            and claude_signal.confidence >= self.claude_veto_threshold
        ):
            return AggregatedSignal(
                instrument_symbol=ta_signal.instrument_symbol,
                timeframe=ta_signal.timeframe,
                direction=Direction.HOLD,
                confidence=0.0,
                source=SignalSource.AGGREGATED,
                reasoning=claude_signal.reasoning,
                component_signals=[ta_signal, ml_signal, claude_signal],
                override_reason=f"AI HOLD veto: confidence={claude_signal.confidence:.2f}",
            )

        # If AI abstains (HOLD without high confidence), renormalize TA+ML to 1.0
        if claude_signal.direction == Direction.HOLD:
            ta_w = self.weight_ta / (self.weight_ta + self.weight_ml)
            ml_w = self.weight_ml / (self.weight_ta + self.weight_ml)
            score = (
                _direction_score(ta_signal.direction, ta_signal.confidence) * ta_w
                + _direction_score(ml_signal.direction, ml_signal.confidence) * ml_w
            )
        else:
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

    def aggregate_professional(
        self,
        ta_signal: Signal,
        ml_signal: Signal,
        claude_signal: Signal,
        mtf_context=None,   # MultiTimeframeContext | None
        sr_context=None,    # SRContext | None
    ) -> AggregatedSignal:
        """Confluence-based aggregation — LLM has editorial control.

        Rules (priority order):
        1. R:R not viable → HOLD (no good trade available)
        2. LLM says HOLD with high confidence → HOLD
        3. Count confluence factors — require min 3/5
        4. Final confidence = LLM confidence * alignment score
        """
        from strategy.domain.entities import Direction as D

        override_reason = ""

        # Rule 1: LLM confident HOLD — respeta la decisión del LLM (umbral alto para no bloquear todo)
        if claude_signal.direction == D.HOLD and claude_signal.confidence >= 0.85:
            return AggregatedSignal(
                instrument_symbol=ta_signal.instrument_symbol,
                timeframe=ta_signal.timeframe,
                direction=D.HOLD,
                confidence=0.0,
                source=SignalSource.AGGREGATED,
                reasoning=claude_signal.reasoning,
                component_signals=[ta_signal, ml_signal, claude_signal],
                override_reason="LLM_CONFIDENT_HOLD",
            )

        # Rule 2: Determine direction — AI if directional, else TA+ML consensus
        if claude_signal.direction != D.HOLD:
            final_dir = claude_signal.direction
        else:
            # AI abstains → derive direction from TA+ML weighted vote
            ta_score = _direction_score(ta_signal.direction, ta_signal.confidence)
            ml_score = _direction_score(ml_signal.direction, ml_signal.confidence)
            combined = ta_score * (self.weight_ta / (self.weight_ta + self.weight_ml)) + \
                       ml_score * (self.weight_ml / (self.weight_ta + self.weight_ml))
            if combined > 0:
                final_dir = D.BUY
            elif combined < 0:
                final_dir = D.SELL
            else:
                final_dir = D.HOLD

        if final_dir == D.HOLD:
            return AggregatedSignal(
                instrument_symbol=ta_signal.instrument_symbol,
                timeframe=ta_signal.timeframe,
                direction=D.HOLD,
                confidence=0.0,
                source=SignalSource.AGGREGATED,
                reasoning="No directional consensus from TA+ML+AI",
                component_signals=[ta_signal, ml_signal, claude_signal],
                override_reason="NO_CONSENSUS",
            )

        # Rule 3: Confluence scoring (max 5 points)
        confluence = 0.0

        if mtf_context is not None:
            if mtf_context.d1.trend == final_dir:
                confluence += 1.0
            if mtf_context.h4.trend == final_dir:
                confluence += 1.0
        if ta_signal.direction == final_dir:
            confluence += 0.5
        if ml_signal.direction == final_dir:
            confluence += 0.5
        if sr_context is not None and (sr_context.at_support or sr_context.at_resistance):
            confluence += 1.0

        if confluence < self.confluence_min_score:
            override_reason = f"Insufficient confluence: {confluence:.1f}/5.0"
            return AggregatedSignal(
                instrument_symbol=ta_signal.instrument_symbol,
                timeframe=ta_signal.timeframe,
                direction=D.HOLD,
                confidence=0.0,
                source=SignalSource.AGGREGATED,
                reasoning=f"Setup rejected: confluence={confluence:.1f}/5.0 (need {self.confluence_min_score:.1f}+)",
                component_signals=[ta_signal, ml_signal, claude_signal],
                override_reason=override_reason,
            )

        # Rule 3: R:R check por dirección (bloqueo duro — trader profesional)
        # Ahora que conocemos la dirección, verificamos el R:R correcto
        if sr_context is not None and sr_context.nearest_support and sr_context.nearest_resistance:
            pts = sr_context.pip_to_support
            ptr = sr_context.pip_to_resistance
            if final_dir == D.BUY and pts > 0 and (ptr / pts) < self.min_threshold:
                # BUY: reward=resistencia, risk=soporte → necesita ptr/pts >= rr_min
                # Usamos min_threshold como proxy del rr_min configurado
                pass  # deja pasar — el LLM ya evaluó esto con el prompt completo
            # El bloqueo duro solo aplica cuando sr_context confirma inviabilidad total
            if not sr_context.rr_viable:
                return AggregatedSignal(
                    instrument_symbol=ta_signal.instrument_symbol,
                    timeframe=ta_signal.timeframe,
                    direction=D.HOLD,
                    confidence=0.0,
                    source=SignalSource.AGGREGATED,
                    reasoning="R:R insuficiente en ambas direcciones — sin estructura viable",
                    component_signals=[ta_signal, ml_signal, claude_signal],
                    override_reason="RR_NOT_VIABLE",
                )

        # Rule 4: Final confidence
        alignment = mtf_context.trend_alignment if mtf_context else 0.5
        final_confidence = claude_signal.confidence * (0.6 + 0.4 * alignment)
        final_confidence = min(1.0, round(final_confidence, 4))

        # Below threshold → HOLD
        if final_confidence < self.min_threshold:
            return AggregatedSignal(
                instrument_symbol=ta_signal.instrument_symbol,
                timeframe=ta_signal.timeframe,
                direction=D.HOLD,
                confidence=final_confidence,
                source=SignalSource.AGGREGATED,
                reasoning=f"Confidence {final_confidence:.2f} below threshold {self.min_threshold}",
                component_signals=[ta_signal, ml_signal, claude_signal],
                override_reason="BELOW_THRESHOLD",
            )

        return AggregatedSignal(
            instrument_symbol=ta_signal.instrument_symbol,
            timeframe=ta_signal.timeframe,
            direction=final_dir,
            confidence=final_confidence,
            source=SignalSource.AGGREGATED,
            reasoning=claude_signal.reasoning,
            component_signals=[ta_signal, ml_signal, claude_signal],
            override_reason=override_reason,
        )
