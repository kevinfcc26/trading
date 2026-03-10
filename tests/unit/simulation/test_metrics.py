"""Tests for PerformanceMetrics calculation."""
import pytest
from datetime import datetime, timedelta

from simulation.performance.metrics import PerformanceMetrics
from trading.domain.entities import Direction, Trade


def _make_trade(pnl: float, direction: Direction = Direction.BUY) -> Trade:
    now = datetime.utcnow()
    trade = Trade(
        instrument_symbol="EURUSD",
        side=direction,
        volume=0.01,
        entry_price=1.10000,
        exit_price=1.10100 if pnl > 0 else 1.09900,
        realized_pnl=pnl,
        opened_at=now - timedelta(hours=2),
        closed_at=now,
    )
    return trade


def test_empty_trades_returns_zero_metrics():
    metrics = PerformanceMetrics.from_trades([], [], initial_balance=10_000.0)
    assert metrics.total_trades == 0
    assert metrics.total_pnl == 0.0
    assert metrics.win_rate == 0.0


def test_win_rate_calculation():
    trades = [_make_trade(100), _make_trade(50), _make_trade(-30), _make_trade(-20)]
    metrics = PerformanceMetrics.from_trades(trades, [], initial_balance=10_000.0)

    assert metrics.total_trades == 4
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 2
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.total_pnl == pytest.approx(100)


def test_profit_factor():
    trades = [_make_trade(200), _make_trade(-100)]
    metrics = PerformanceMetrics.from_trades(trades, [], initial_balance=10_000.0)

    assert metrics.profit_factor == pytest.approx(2.0)


def test_max_drawdown_from_equity_curve():
    equity = [
        (datetime.utcnow(), 10_000.0),
        (datetime.utcnow(), 11_000.0),
        (datetime.utcnow(), 9_000.0),
        (datetime.utcnow(), 10_500.0),
    ]
    metrics = PerformanceMetrics.from_trades([], equity, initial_balance=10_000.0)

    # Peak was 11_000, trough was 9_000 → drawdown = 2000/11000 ≈ 18.2%
    assert metrics.max_drawdown == pytest.approx(2000.0)
    assert metrics.max_drawdown_pct == pytest.approx(2000.0 / 11000.0, rel=0.01)


def test_return_pct():
    equity = [
        (datetime.utcnow(), 10_000.0),
        (datetime.utcnow(), 12_000.0),
    ]
    metrics = PerformanceMetrics.from_trades([], equity, initial_balance=10_000.0)

    assert metrics.final_balance == 12_000.0
    assert metrics.return_pct == pytest.approx(0.20)
