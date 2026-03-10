"""
GenerateSignalUseCase — full signal pipeline:
  CandleSeries → TA → ML → Claude → SignalAggregator → persist → return
"""
import logging

from domain.entities import AggregatedSignal, Direction
from domain.ports import IDataProvider, ISignalRepository
from domain.services import SignalAggregator
from domain.value_objects import Timeframe
from infrastructure.signals.ai.claude_adapter import ClaudeAdapter
from infrastructure.signals.ml.ml_model_adapter import MLModelAdapter
from infrastructure.signals.technical_analysis.ta_signal_generator import TASignalGenerator

logger = logging.getLogger(__name__)


class GenerateSignalUseCase:
    def __init__(
        self,
        data_provider: IDataProvider,
        ta_generator: TASignalGenerator,
        ml_adapter: MLModelAdapter,
        claude_adapter: ClaudeAdapter,
        signal_aggregator: SignalAggregator,
        signal_repository: ISignalRepository,
        candle_count: int = 200,
    ) -> None:
        self._data = data_provider
        self._ta = ta_generator
        self._ml = ml_adapter
        self._claude = claude_adapter
        self._aggregator = signal_aggregator
        self._repo = signal_repository
        self._candle_count = candle_count

    async def execute(self, symbol: str, timeframe: Timeframe) -> AggregatedSignal:
        # 1. Fetch candles
        candles = await self._data.get_candles(symbol, timeframe, count=self._candle_count)
        logger.info("Fetched %d candles for %s %s", len(candles), symbol, timeframe.value)

        # 2. TA signal
        ta_signal = await self._ta.generate(candles)
        logger.info("TA signal: %s %.2f", ta_signal.direction.value, ta_signal.confidence)

        # 3. ML signal
        ml_signal = await self._ml.generate(candles)
        logger.info("ML signal: %s %.2f", ml_signal.direction.value, ml_signal.confidence)

        # 4. Claude signal (receives TA + ML context)
        claude_signal = await self._claude.generate(candles, ta_signal=ta_signal, ml_signal=ml_signal)
        logger.info(
            "Claude signal: %s %.2f | %s",
            claude_signal.direction.value,
            claude_signal.confidence,
            claude_signal.reasoning[:80],
        )

        # 5. Aggregate
        aggregated = self._aggregator.aggregate(ta_signal, ml_signal, claude_signal)
        logger.info(
            "Aggregated: %s %.2f%s",
            aggregated.direction.value,
            aggregated.confidence,
            f" [VETO: {aggregated.override_reason}]" if aggregated.override_reason else "",
        )

        # 6. Persist signal
        saved = await self._repo.save(aggregated)
        return saved
