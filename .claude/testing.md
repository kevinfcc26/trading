# Testing Guide

## Test Structure

```
tests/
├── unit/           ← fast, no I/O, no Docker required
│   ├── risk/       ← RiskPipeline, KillSwitch, PositionSizer
│   ├── strategy/   ← SignalAggregator, TAStrategy
│   ├── simulation/ ← BacktestEngine, PerformanceMetrics
│   ├── learning/   ← FeatureEngineer, XGBoostTrainer, TradingEnv
│   ├── application/← use cases (mocked ports)
│   └── domain/     ← legacy (3 pre-existing failures — do not fix without careful analysis)
└── integration/    ← require running PostgreSQL + Redis
```

## Running Tests

```bash
# All passing unit tests (57 tests)
poetry run pytest tests/unit/ -v

# Specific bounded context
poetry run pytest tests/unit/risk/ -v
poetry run pytest tests/unit/strategy/ -v
poetry run pytest tests/unit/simulation/ -v
poetry run pytest tests/unit/learning/ -v

# Single test file
poetry run pytest tests/unit/risk/test_pipeline.py -v

# Single test
poetry run pytest tests/unit/risk/test_pipeline.py::test_kill_switch_blocks_trade -v

# With output (useful for debugging)
poetry run pytest tests/unit/ -v -s
```

## Baseline

57 unit tests pass. **3 pre-existing failures** exist in `tests/unit/domain/` (legacy code).
Do not modify those legacy tests without explicit user instruction.
After any change, confirm `poetry run pytest tests/unit/ -v` is still ≥57 passing.

---

## Test File Conventions

```python
"""Tests for RiskPipeline — covers AC-1 through AC-5."""
from __future__ import annotations

import pytest
from risk.domain.services.pipeline import RiskPipeline
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.entities import RiskPolicy
from strategy.domain.entities import AggregatedSignal, Direction, SignalSource


# --- Fixtures ---

@pytest.fixture
def kill_switch() -> KillSwitch:
    return KillSwitch()


@pytest.fixture
def policy() -> RiskPolicy:
    return RiskPolicy(
        risk_per_trade=0.01,
        max_open_positions=5,
        max_daily_drawdown=0.05,
    )


@pytest.fixture
def pipeline(kill_switch: KillSwitch, policy: RiskPolicy) -> RiskPipeline:
    return RiskPipeline(kill_switch=kill_switch, policy=policy)


def _make_signal(direction: Direction = Direction.BUY, confidence: float = 0.75) -> AggregatedSignal:
    """Helper to build a minimal AggregatedSignal for tests."""
    return AggregatedSignal(
        instrument_symbol="EURUSD",
        timeframe="H1",
        direction=direction,
        confidence=confidence,
        source=SignalSource.AGGREGATED,
    )


# --- Tests ---

@pytest.mark.asyncio
async def test_pipeline_approves_valid_signal(pipeline: RiskPipeline) -> None:
    """AC-1: A valid BUY signal with healthy account should be approved."""
    signal = _make_signal(Direction.BUY, confidence=0.80)
    result = await pipeline.evaluate(
        signal=signal,
        current_price=1.1000,
        account_balance=10_000.0,
        open_positions_count=0,
    )
    assert result.approved is True
    assert result.volume > 0
    assert result.stop_loss > 0
    assert result.take_profit > result.stop_loss  # for BUY


@pytest.mark.asyncio
async def test_kill_switch_blocks_trade(pipeline: RiskPipeline, kill_switch: KillSwitch) -> None:
    """AC-2: An engaged kill switch must reject all signals."""
    kill_switch.engage("manual test stop")
    signal = _make_signal(Direction.BUY)
    result = await pipeline.evaluate(
        signal=signal, current_price=1.1, account_balance=10_000.0, open_positions_count=0
    )
    assert result.approved is False
    assert "kill" in result.reason.lower()
```

---

## Mocking External Services

### Mocking Claude (Anthropic SDK)

```python
from unittest.mock import AsyncMock, patch
from strategy.infrastructure.claude_strategy import ClaudeStrategy

@pytest.fixture
def claude_strategy() -> ClaudeStrategy:
    return ClaudeStrategy(api_key="test-key-not-real")

@pytest.mark.asyncio
async def test_claude_returns_buy_signal(claude_strategy: ClaudeStrategy) -> None:
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text='{"direction": "BUY", "confidence": 0.85, "reasoning": "test"}')]

    with patch.object(claude_strategy._client.messages, "create", return_value=mock_response):
        signal = await claude_strategy.generate(candles)

    assert signal.direction == Direction.BUY
```

### Mocking BrokerPort

```python
from unittest.mock import AsyncMock
from execution.domain.ports import BrokerPort

@pytest.fixture
def mock_broker() -> BrokerPort:
    broker = AsyncMock()
    broker.get_balance.return_value = 10_000.0
    broker.fetch_positions.return_value = []
    broker.submit_order.side_effect = lambda order: order  # echo back
    return broker
```

### Mocking EventBus

```python
from events.bus.in_memory_bus import InMemoryEventBus

@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()
    # Subscribe a list collector to assert events published:
    # published = []
    # event_bus.subscribe(SomeEvent, lambda e: published.append(e))
```

---

## BacktestEngine Tests

```python
@pytest.mark.asyncio
async def test_backtest_runs_without_error() -> None:
    """Smoke test: engine completes a full run on synthetic candles."""
    from simulation.engine.backtest_engine import BacktestEngine, BacktestConfig
    from market.domain.value_objects import Timeframe

    candles = _generate_synthetic_candles(200)  # helper in conftest
    config = BacktestConfig(symbol="EURUSD", timeframe=Timeframe.H1)
    engine = BacktestEngine(config=config, ta_strategy=TAStrategy(), ...)
    report = await engine.run(candles)

    assert report.total_trades >= 0
    assert isinstance(report.metrics.sharpe_ratio, float)
```

---

## Feature Engineering Tests

```python
def test_feature_matrix_columns_match_feature_names() -> None:
    """Column order must exactly match FEATURE_NAMES — model depends on it."""
    from learning.infrastructure.feature_engineering import FeatureEngineer, FEATURE_NAMES

    df = _load_sample_ohlcv()  # helper
    fe = FeatureEngineer()
    features = fe.build_feature_matrix(df)

    assert list(features.columns) == FEATURE_NAMES
```

---

## Anti-Patterns in Tests

- **Do not** mock `domain` classes — test them directly, they are pure.
- **Do not** use `time.sleep()` — use `asyncio.sleep(0)` for event loop yields.
- **Do not** write integration tests in `tests/unit/` — keep it fast and infra-free.
- **Do not** assert on exact float values without tolerance — use `pytest.approx()`.
- **Do not** import from `src/domain/` (legacy) in new tests — use bounded context paths.
- **Always** use `@pytest.mark.asyncio` for `async def` tests.
- **Always** document which AC a test covers in its docstring.
