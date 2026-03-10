"""GenerateSignalUseCase — runs the full strategy pipeline and publishes an event."""
from __future__ import annotations

import logging

from events.bus.event_bus import EventBus
from events.trading_events import SignalGenerated
from market.domain.entities import CandleSeries
from market.domain.ports import MarketDataPort
from market.domain.value_objects import Timeframe
from strategy.domain.entities import AggregatedSignal, Direction
from strategy.domain.ports import SignalRepository, StrategyPort
from strategy.domain.services import SignalAggregator

logger = logging.getLogger(__name__)


class GenerateSignalUseCase:
    """Orchestrates the TA → ML → Claude → Aggregate pipeline.

    After aggregation, the result is persisted and a SignalGenerated
    event is published so downstream contexts (risk, execution) can react.
    """

    def __init__(
        self,
        data_provider: MarketDataPort,
        ta_strategy: StrategyPort,
        ml_strategy: StrategyPort,
        claude_strategy: StrategyPort,
        aggregator: SignalAggregator,
        signal_repository: SignalRepository,
        event_bus: EventBus,
        candle_count: int = 200,
    ) -> None:
        self._data = data_provider
        self._ta = ta_strategy
        self._ml = ml_strategy
        self._claude = claude_strategy
        self._aggregator = aggregator
        self._repo = signal_repository
        self._bus = event_bus
        self._candle_count = candle_count

    async def execute(self, symbol: str, timeframe: Timeframe) -> AggregatedSignal:
        candles = await self._data.get_candles(symbol, timeframe, count=self._candle_count)

        ta_signal = await self._ta.generate(candles)
        ml_signal = await self._ml.generate(candles)
        claude_signal = await self._claude.generate(candles, ta_signal=ta_signal, ml_signal=ml_signal)

        aggregated = self._aggregator.aggregate(ta_signal, ml_signal, claude_signal)
        saved = await self._repo.save(aggregated)

        await self._bus.publish(
            SignalGenerated(
                signal_id=saved.id,
                symbol=saved.instrument_symbol,
                timeframe=saved.timeframe.value,
                direction=saved.direction.value,
                confidence=saved.confidence,
                reasoning=saved.reasoning,
                override_reason=saved.override_reason,
            )
        )

        logger.info(
            "Signal: %s %s dir=%s conf=%.2f",
            symbol,
            timeframe.value,
            saved.direction.value,
            saved.confidence,
        )
        return saved
