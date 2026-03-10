"""
RunBacktestUseCase — walk-forward backtesting over historical candles.
Splits CandleSeries into windows, runs the full signal pipeline on each.
No broker orders are placed — trades are simulated.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from domain.entities import AggregatedSignal, CandleSeries, Direction
from domain.services import calculate_pnl, summarize_trades, SignalAggregator
from domain.entities import Trade
from domain.value_objects import Timeframe
from infrastructure.signals.ai.claude_adapter import ClaudeAdapter
from infrastructure.signals.ml.ml_model_adapter import MLModelAdapter
from infrastructure.signals.technical_analysis.ta_signal_generator import TASignalGenerator

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    symbol: str
    timeframe: Timeframe
    start: datetime
    end: datetime
    trades: list[Trade] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class RunBacktestUseCase:
    def __init__(
        self,
        ta_generator: TASignalGenerator,
        ml_adapter: MLModelAdapter,
        claude_adapter: ClaudeAdapter,
        signal_aggregator: SignalAggregator,
        window_size: int = 200,
        step_size: int = 1,
        sl_pips: float = 0.0020,
        tp_pips: float = 0.0040,
        volume: float = 0.01,
    ) -> None:
        self._ta = ta_generator
        self._ml = ml_adapter
        self._claude = claude_adapter
        self._aggregator = signal_aggregator
        self.window_size = window_size
        self.step_size = step_size
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.volume = volume

    async def execute(self, full_series: CandleSeries) -> BacktestResult:
        candles = full_series.candles
        trades: list[Trade] = []

        logger.info(
            "Starting backtest: %s %s | %d candles",
            full_series.instrument_symbol,
            full_series.timeframe.value,
            len(candles),
        )

        for i in range(self.window_size, len(candles), self.step_size):
            window_candles = candles[i - self.window_size : i]
            window_series = CandleSeries(
                instrument_symbol=full_series.instrument_symbol,
                timeframe=full_series.timeframe,
                candles=window_candles,
            )

            ta_signal = await self._ta.generate(window_series)
            ml_signal = await self._ml.generate(window_series)
            claude_signal = await self._claude.generate(
                window_series, ta_signal=ta_signal, ml_signal=ml_signal
            )
            aggregated = self._aggregator.aggregate(ta_signal, ml_signal, claude_signal)

            if aggregated.direction == Direction.HOLD:
                continue

            entry = candles[i].open
            if aggregated.direction == Direction.BUY:
                sl = entry - self.sl_pips
                tp = entry + self.tp_pips
            else:
                sl = entry + self.sl_pips
                tp = entry - self.tp_pips

            # Simulate outcome against next candle's high/low
            if i >= len(candles):
                break
            next_candle = candles[i]
            exit_price = entry

            if aggregated.direction == Direction.BUY:
                if next_candle.low <= sl:
                    exit_price = sl
                elif next_candle.high >= tp:
                    exit_price = tp
            else:
                if next_candle.high >= sl:
                    exit_price = sl
                elif next_candle.low <= tp:
                    exit_price = tp

            pnl = calculate_pnl(aggregated.direction, entry, exit_price, self.volume)

            trade = Trade(
                instrument_symbol=full_series.instrument_symbol,
                side=aggregated.direction,
                volume=self.volume,
                entry_price=entry,
                exit_price=exit_price,
                stop_loss=sl,
                take_profit=tp,
                realized_pnl=pnl,
                opened_at=window_candles[-1].time,
                signal_id=aggregated.id,
            )
            trades.append(trade)

        summary = summarize_trades(trades)
        logger.info("Backtest complete: %s", summary)

        return BacktestResult(
            symbol=full_series.instrument_symbol,
            timeframe=full_series.timeframe,
            start=candles[0].time if candles else datetime.utcnow(),
            end=candles[-1].time if candles else datetime.utcnow(),
            trades=trades,
            summary=summary,
        )
