"""Tests for RiskPipeline chain of validators."""
import pytest
from datetime import datetime
from uuid import uuid4

from market.domain.value_objects import Timeframe
from risk.domain.entities import RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from strategy.domain.entities import AggregatedSignal, Direction, Signal, SignalSource


def _make_aggregated(direction: Direction, confidence: float = 0.75) -> AggregatedSignal:
    ta = Signal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=direction,
        confidence=confidence,
        source=SignalSource.TA,
    )
    ml = Signal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=direction,
        confidence=confidence,
        source=SignalSource.ML,
    )
    claude = Signal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=direction,
        confidence=confidence,
        source=SignalSource.CLAUDE,
    )
    return AggregatedSignal(
        instrument_symbol="EURUSD",
        timeframe=Timeframe.H1,
        direction=direction,
        confidence=confidence,
        source=SignalSource.AGGREGATED,
        component_signals=[ta, ml, claude],
    )


@pytest.mark.asyncio
async def test_pipeline_approves_valid_signal():
    ks = KillSwitch()
    policy = RiskPolicy(max_open_positions=3, risk_per_trade=0.01)
    pipeline = RiskPipeline(ks, policy)
    signal = _make_aggregated(Direction.BUY)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=1.10000,
        account_balance=10_000.0,
        open_positions_count=0,
    )

    assert assessment.approved
    assert assessment.volume > 0
    assert assessment.stop_loss is not None
    assert assessment.take_profit is not None


@pytest.mark.asyncio
async def test_pipeline_rejects_hold_signal():
    ks = KillSwitch()
    pipeline = RiskPipeline(ks)
    signal = _make_aggregated(Direction.HOLD)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=1.10000,
        account_balance=10_000.0,
        open_positions_count=0,
    )

    assert not assessment.approved
    assert "HOLD" in assessment.reason


@pytest.mark.asyncio
async def test_pipeline_rejects_when_kill_switch_engaged():
    ks = KillSwitch()
    ks.engage("Test kill")
    pipeline = RiskPipeline(ks)
    signal = _make_aggregated(Direction.BUY)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=1.10000,
        account_balance=10_000.0,
        open_positions_count=0,
    )

    assert not assessment.approved
    assert "kill switch" in assessment.reason.lower()


@pytest.mark.asyncio
async def test_pipeline_rejects_max_positions_reached():
    ks = KillSwitch()
    policy = RiskPolicy(max_open_positions=2)
    pipeline = RiskPipeline(ks, policy)
    signal = _make_aggregated(Direction.BUY)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=1.10000,
        account_balance=10_000.0,
        open_positions_count=2,  # at limit
    )

    assert not assessment.approved
    assert "Max open positions" in assessment.reason


@pytest.mark.asyncio
async def test_pipeline_engages_kill_switch_on_daily_drawdown():
    ks = KillSwitch()
    policy = RiskPolicy(max_daily_drawdown=0.05)
    pipeline = RiskPipeline(ks, policy)
    signal = _make_aggregated(Direction.BUY)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=1.10000,
        account_balance=9_500.0,
        open_positions_count=0,
        daily_drawdown_pct=0.06,  # exceeds 5% limit
    )

    assert not assessment.approved
    assert ks.is_engaged  # kill switch should auto-engage


@pytest.mark.asyncio
async def test_pipeline_rejects_zero_price():
    ks = KillSwitch()
    pipeline = RiskPipeline(ks)
    signal = _make_aggregated(Direction.BUY)

    assessment = await pipeline.evaluate(
        signal=signal,
        current_price=0.0,  # invalid
        account_balance=10_000.0,
        open_positions_count=0,
    )

    assert not assessment.approved
