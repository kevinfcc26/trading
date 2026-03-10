"""
Unit tests for SignalAggregator — Claude veto, weighting, edge cases.
"""
import pytest

from domain.entities import AggregatedSignal, Direction, Signal, SignalSource
from domain.services import SignalAggregator
from domain.value_objects import Timeframe

SYMBOL = "EURUSD"
TF = Timeframe.H1


def _make_signal(direction: Direction, confidence: float, source: SignalSource) -> Signal:
    return Signal(
        instrument_symbol=SYMBOL,
        timeframe=TF,
        direction=direction,
        confidence=confidence,
        source=source,
    )


@pytest.fixture
def aggregator():
    return SignalAggregator(
        weight_ta=0.25,
        weight_ml=0.35,
        weight_claude=0.40,
        min_threshold=0.60,
        claude_veto_threshold=0.70,
    )


class TestWeightedVote:
    def test_all_buy_produces_buy(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.BUY, 0.70, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.BUY
        assert result.confidence > 0.60

    def test_all_sell_produces_sell(self, aggregator):
        ta = _make_signal(Direction.SELL, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.SELL, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.SELL, 0.70, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.SELL

    def test_low_confidence_produces_hold(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.30, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.35, SignalSource.ML)
        claude = _make_signal(Direction.HOLD, 0.00, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.HOLD

    def test_conflicting_signals_below_threshold(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.70, SignalSource.TA)
        ml = _make_signal(Direction.SELL, 0.70, SignalSource.ML)
        claude = _make_signal(Direction.HOLD, 0.00, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        # Score ≈ 0.70*0.25 - 0.70*0.35 = -0.07 → direction=SELL, confidence=0.07 < 0.60
        assert result.direction == Direction.HOLD


class TestClaudeVeto:
    def test_claude_veto_overrides_buy_consensus(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.SELL, 0.75, SignalSource.CLAUDE)  # veto threshold 0.70
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.SELL
        assert result.override_reason != ""

    def test_claude_below_veto_threshold_does_not_override(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.SELL, 0.65, SignalSource.CLAUDE)  # below threshold
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.BUY
        assert result.override_reason == ""

    def test_claude_hold_does_not_veto(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.HOLD, 0.80, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert result.direction == Direction.BUY
        assert result.override_reason == ""


class TestAggregatedSignalStructure:
    def test_component_signals_stored(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.BUY, 0.70, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert len(result.component_signals) == 3
        assert isinstance(result, AggregatedSignal)

    def test_source_is_aggregated(self, aggregator):
        ta = _make_signal(Direction.BUY, 0.80, SignalSource.TA)
        ml = _make_signal(Direction.BUY, 0.75, SignalSource.ML)
        claude = _make_signal(Direction.BUY, 0.70, SignalSource.CLAUDE)
        result = aggregator.aggregate(ta, ml, claude)
        assert result.source == SignalSource.AGGREGATED


class TestWeightValidation:
    def test_weights_not_summing_to_one_raises(self):
        with pytest.raises(ValueError):
            SignalAggregator(weight_ta=0.30, weight_ml=0.30, weight_claude=0.30)
