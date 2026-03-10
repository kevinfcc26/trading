"""
Unit tests for GenerateSignalUseCase — all dependencies mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from domain.entities import AggregatedSignal, Direction, Signal, SignalSource
from domain.services import SignalAggregator
from domain.value_objects import Timeframe
from domain.entities import CandleSeries
from application.use_cases.generate_signal import GenerateSignalUseCase

SYMBOL = "EURUSD"
TF = Timeframe.H1


def _mock_signal(direction: Direction, confidence: float, source: SignalSource) -> Signal:
    return Signal(
        instrument_symbol=SYMBOL,
        timeframe=TF,
        direction=direction,
        confidence=confidence,
        source=source,
    )


@pytest.fixture
def mock_candles():
    return CandleSeries(instrument_symbol=SYMBOL, timeframe=TF, candles=[])


@pytest.fixture
def use_case(mock_candles):
    data_provider = AsyncMock()
    data_provider.get_candles.return_value = mock_candles

    ta_generator = AsyncMock()
    ta_generator.generate.return_value = _mock_signal(Direction.BUY, 0.75, SignalSource.TA)

    ml_adapter = AsyncMock()
    ml_adapter.generate.return_value = _mock_signal(Direction.BUY, 0.72, SignalSource.ML)

    claude_adapter = AsyncMock()
    claude_adapter.generate.return_value = _mock_signal(Direction.BUY, 0.68, SignalSource.CLAUDE)

    aggregator = SignalAggregator()

    signal_repo = AsyncMock()
    signal_repo.save.side_effect = lambda s: s  # return same signal

    return GenerateSignalUseCase(
        data_provider=data_provider,
        ta_generator=ta_generator,
        ml_adapter=ml_adapter,
        claude_adapter=claude_adapter,
        signal_aggregator=aggregator,
        signal_repository=signal_repo,
    )


@pytest.mark.asyncio
async def test_generate_signal_returns_aggregated(use_case):
    result = await use_case.execute(SYMBOL, TF)
    assert isinstance(result, AggregatedSignal)
    assert result.direction == Direction.BUY


@pytest.mark.asyncio
async def test_generate_signal_persists_to_repo(use_case):
    result = await use_case.execute(SYMBOL, TF)
    # signal_repo.save was called once
    use_case._repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_generate_signal_calls_all_generators(use_case):
    await use_case.execute(SYMBOL, TF)
    use_case._ta.generate.assert_called_once()
    use_case._ml.generate.assert_called_once()
    use_case._claude.generate.assert_called_once()
