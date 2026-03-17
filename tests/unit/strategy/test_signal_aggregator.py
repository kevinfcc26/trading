"""Tests for the migrated SignalAggregator."""
import pytest
from market.domain.value_objects import Timeframe
from strategy.domain.entities import AggregatedSignal, Direction, Signal, SignalSource
from strategy.domain.services import SignalAggregator


def _make_signal(direction: Direction, confidence: float, source: SignalSource) -> Signal:
    return Signal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=direction,
        confidence=confidence,
        source=source,
    )


def test_aggregator_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        SignalAggregator(weight_ta=0.5, weight_ml=0.5, weight_claude=0.5)


def test_aggregator_buy_consensus():
    agg = SignalAggregator()
    ta = _make_signal(Direction.BUY, 0.8, SignalSource.TA)
    ml = _make_signal(Direction.BUY, 0.9, SignalSource.ML)
    claude = _make_signal(Direction.BUY, 0.85, SignalSource.CLAUDE)

    result = agg.aggregate(ta, ml, claude)

    assert result.direction == Direction.BUY
    assert result.confidence > 0.6
    assert result.override_reason == ""


def test_aggregator_hold_when_below_threshold():
    agg = SignalAggregator(min_threshold=0.60)
    ta = _make_signal(Direction.BUY, 0.3, SignalSource.TA)
    ml = _make_signal(Direction.SELL, 0.3, SignalSource.ML)
    claude = _make_signal(Direction.HOLD, 0.0, SignalSource.CLAUDE)

    result = agg.aggregate(ta, ml, claude)

    assert result.direction == Direction.HOLD


def test_claude_veto_overrides_consensus():
    agg = SignalAggregator(claude_veto_threshold=0.70)
    ta = _make_signal(Direction.BUY, 0.8, SignalSource.TA)
    ml = _make_signal(Direction.BUY, 0.9, SignalSource.ML)
    # Claude confidently disagrees
    claude = _make_signal(Direction.SELL, 0.80, SignalSource.CLAUDE)

    result = agg.aggregate(ta, ml, claude)

    assert result.direction == Direction.SELL
    assert "VETO" in result.override_reason


def test_claude_hold_above_threshold_applies_hold_veto():
    agg = SignalAggregator(claude_veto_threshold=0.70)
    ta = _make_signal(Direction.BUY, 0.8, SignalSource.TA)
    ml = _make_signal(Direction.BUY, 0.8, SignalSource.ML)
    claude = _make_signal(Direction.HOLD, 0.90, SignalSource.CLAUDE)  # HOLD + high confidence

    result = agg.aggregate(ta, ml, claude)

    # AI HOLD veto: Claude HOLD >= veto_threshold forces the result to HOLD
    assert result.direction == Direction.HOLD
    assert "AI HOLD veto" in result.override_reason


def test_aggregated_signal_preserves_components():
    agg = SignalAggregator()
    ta = _make_signal(Direction.BUY, 0.8, SignalSource.TA)
    ml = _make_signal(Direction.BUY, 0.9, SignalSource.ML)
    claude = _make_signal(Direction.BUY, 0.85, SignalSource.CLAUDE)

    result = agg.aggregate(ta, ml, claude)

    assert len(result.component_signals) == 3
    assert result.source == SignalSource.AGGREGATED
