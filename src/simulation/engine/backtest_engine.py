"""BacktestEngine — event-driven historical replay engine.

Flow per bar:
  1. Advance SimulatedClock to candle.time
  2. Update PaperBrokerAdapter price
  3. Check open positions for SL/TP hits
  4. Publish MarketDataReceived
  5. Build MTF context from pre-fetched D1/H4 slices (if available)
  6. Detect S/R levels from H4 slice (if sr_detector provided)
  7. Run TA / ML / AI signals
  8. Aggregate with aggregate_professional() when context available, else aggregate()
  9. Run EvaluateRiskUseCase
  10. If approved → submit order to PaperBrokerAdapter
  11. Accumulate trade records for PerformanceAnalyzer
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from events.bus.in_memory_bus import InMemoryEventBus
from events.trading_events import MarketDataReceived
from execution.infrastructure.paper.adapter import PaperBrokerAdapter
from market.domain.entities import Candle, CandleSeries
from market.domain.value_objects import Timeframe
from risk.domain.entities import RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from simulation.engine.clock import SimulatedClock
from simulation.performance.metrics import PerformanceMetrics
from simulation.performance.report import BacktestReport
from strategy.domain.entities import Direction
from strategy.domain.services import SignalAggregator
from strategy.infrastructure.ta_strategy import TAStrategy
from trading.domain.entities import Order, OrderType, Position, Trade
from trading.domain.services import calculate_pnl

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    symbol: str
    timeframe: Timeframe
    initial_balance: float = 10_000.0
    spread_pips: float = 0.0002
    commission_per_lot: float = 7.0
    slippage_pips: float = 0.0001
    warmup_candles: int = 50        # minimum candles before first signal
    atr_multiplier: float = 2.0     # overridden per timeframe
    rr_ratio: float = 2.0           # overridden per timeframe
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)

    def __post_init__(self):
        # Apply TF-aware values to the risk policy
        self.risk_policy.atr_multiplier = self.atr_multiplier
        self.risk_policy.rr_ratio = self.rr_ratio


class BacktestEngine:
    """Replays historical candles and runs the full trading pipeline."""

    def __init__(
        self,
        config: BacktestConfig,
        ta_strategy: TAStrategy,
        ml_strategy,           # MLStrategy | None
        claude_strategy,       # AI strategy | None
        aggregator: SignalAggregator,
        sr_detector=None,      # SRDetector | None
    ) -> None:
        self._config = config
        self._ta = ta_strategy
        self._ml = ml_strategy
        self._claude = claude_strategy
        self._aggregator = aggregator
        self._sr_detector = sr_detector
        self._clock = SimulatedClock(start=None)
        self._bus = InMemoryEventBus()
        self._broker = PaperBrokerAdapter(
            initial_balance=config.initial_balance,
            spread_pips=config.spread_pips,
            commission_per_lot=config.commission_per_lot,
            slippage_pips=config.slippage_pips,
        )
        self._kill_switch = KillSwitch()
        self._pipeline = RiskPipeline(self._kill_switch, config.risk_policy)
        self._completed_trades: list[Trade] = []
        self._equity_curve: list[tuple[datetime, float]] = []

    async def run(
        self,
        candles: CandleSeries,
        d1_candles: CandleSeries | None = None,
        h4_candles: CandleSeries | None = None,
    ) -> BacktestReport:
        """Run the backtest over the given candle series.

        Args:
            candles: H1 (entry timeframe) candle series.
            d1_candles: Pre-fetched D1 series for MTF context (optional).
            h4_candles: Pre-fetched H4 series for MTF context + S/R (optional).
        """
        await self._broker.connect()
        all_candles = candles.candles

        if all_candles:
            self._clock = SimulatedClock(start=all_candles[0].time)

        use_professional = (
            d1_candles is not None
            and h4_candles is not None
            and self._sr_detector is not None
        )

        for i, candle in enumerate(all_candles):
            if i < self._config.warmup_candles:
                continue

            self._clock.advance(candle.time)
            self._broker.set_current_price(candle.close)

            await self._check_stops(candle)

            window = CandleSeries(
                instrument_symbol=candles.instrument_symbol,
                timeframe=candles.timeframe,
                candles=all_candles[: i + 1],
            )

            await self._bus.publish(
                MarketDataReceived(
                    symbol=candles.instrument_symbol,
                    timeframe=candles.timeframe.value,
                    close=candle.close,
                    candle_time=candle.time,
                )
            )

            # Build MTF + S/R context from pre-fetched higher-TF candles
            mtf_context = None
            sr_context = None
            if use_professional:
                mtf_context = _build_mtf_context(
                    candles.instrument_symbol, candle.time,
                    d1_candles, h4_candles, window,
                )
                h4_slice = _slice_before(h4_candles, candle.time)
                if h4_slice is not None:
                    sr_context = self._sr_detector.detect(h4_slice, candle.close)

            # Generate signals
            ta_signal = await self._ta.generate(window, mtf_context=mtf_context)

            if self._ml is not None:
                try:
                    ml_signal = await self._ml.generate(window)
                except Exception:
                    ml_signal = ta_signal
            else:
                ml_signal = ta_signal

            if self._claude is not None:
                try:
                    claude_signal = await self._claude.generate(
                        window,
                        ta_signal=ta_signal,
                        ml_signal=ml_signal,
                        mtf_context=mtf_context,
                        sr_context=sr_context,
                    )
                except Exception:
                    claude_signal = ta_signal
            else:
                claude_signal = ta_signal

            # Aggregate — professional only when AI is active (has real context to evaluate)
            # Without AI, use simple weighted aggregate to avoid over-filtering
            if use_professional and self._claude is not None:
                aggregated = self._aggregator.aggregate_professional(
                    ta_signal, ml_signal, claude_signal,
                    mtf_context=mtf_context,
                    sr_context=sr_context,
                )
            else:
                aggregated = self._aggregator.aggregate(ta_signal, ml_signal, claude_signal)

            logger.info(
                "[%s] TA=%s(%.2f) ML=%s(%.2f) AI=%s(%.2f) → %s(%.2f)%s",
                candle.time.strftime("%Y-%m-%d %H:%M"),
                ta_signal.direction.value, ta_signal.confidence,
                ml_signal.direction.value, ml_signal.confidence,
                claude_signal.direction.value, claude_signal.confidence,
                aggregated.direction.value, aggregated.confidence,
                f" [{aggregated.override_reason}]" if aggregated.override_reason else "",
            )

            if aggregated.direction == Direction.HOLD:
                self._equity_curve.append((candle.time, self._broker._balance))
                continue

            open_positions = await self._broker.fetch_positions()
            balance = await self._broker.get_balance()

            assessment = await self._pipeline.evaluate(
                signal=aggregated,
                current_price=candle.close,
                account_balance=balance,
                open_positions_count=len(open_positions),
            )

            if not assessment.approved:
                logger.debug("Risk rejected: %s", assessment.reason)
                self._equity_curve.append((candle.time, self._broker._balance))
                continue

            order = Order(
                instrument_symbol=candles.instrument_symbol,
                direction=aggregated.direction,
                volume=assessment.volume,
                order_type=OrderType.MARKET,
                stop_loss=assessment.stop_loss,
                take_profit=assessment.take_profit,
                signal_id=aggregated.id,
            )
            await self._broker.submit_order(order)

            self._equity_curve.append((candle.time, self._broker._balance))

        open_positions = await self._broker.fetch_positions()
        for pos in open_positions:
            await self._broker.close_position(pos)

        return self._build_report(candles)

    async def _check_stops(self, candle: Candle) -> None:
        """Close positions that have hit SL or TP on this candle."""
        open_positions = await self._broker.fetch_positions()
        for pos in open_positions:
            hit_sl = hit_tp = False

            if pos.stop_loss is not None:
                if pos.side == Direction.BUY and candle.low <= pos.stop_loss:
                    hit_sl = True
                elif pos.side == Direction.SELL and candle.high >= pos.stop_loss:
                    hit_sl = True

            if pos.take_profit is not None:
                if pos.side == Direction.BUY and candle.high >= pos.take_profit:
                    hit_tp = True
                elif pos.side == Direction.SELL and candle.low <= pos.take_profit:
                    hit_tp = True

            if hit_sl or hit_tp:
                close_price = (pos.stop_loss if hit_sl else pos.take_profit) or candle.close
                self._broker.set_current_price(close_price)
                await self._broker.close_position(pos)

                pnl = calculate_pnl(pos.side, pos.entry_price, close_price, pos.volume)
                trade = Trade(
                    instrument_symbol=pos.instrument_symbol,
                    side=pos.side,
                    volume=pos.volume,
                    entry_price=pos.entry_price,
                    exit_price=close_price,
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
                    realized_pnl=pnl,
                    opened_at=pos.opened_at,
                    closed_at=self._clock.now(),
                )
                self._completed_trades.append(trade)
                logger.debug(
                    "SL/TP hit: %s PnL=%.2f %s",
                    pos.instrument_symbol, pnl,
                    "SL" if hit_sl else "TP",
                )

    def _build_report(self, candles: CandleSeries) -> BacktestReport:
        metrics = PerformanceMetrics.from_trades(
            trades=self._completed_trades,
            equity_curve=self._equity_curve,
            initial_balance=self._config.initial_balance,
        )
        return BacktestReport(
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
            total_candles=len(candles),
            trades=self._completed_trades,
            metrics=metrics,
            equity_curve=self._equity_curve,
        )


# ── Helpers for MTF context from pre-fetched data ─────────────────────────────

def _slice_before(series: CandleSeries, bar_time: datetime) -> CandleSeries | None:
    """Return candles with time <= bar_time (no lookahead)."""
    sliced = [c for c in series.candles if c.time <= bar_time]
    if not sliced:
        return None
    return CandleSeries(
        instrument_symbol=series.instrument_symbol,
        timeframe=series.timeframe,
        candles=sliced,
    )


def _build_mtf_context(
    symbol: str,
    bar_time: datetime,
    d1_candles: CandleSeries,
    h4_candles: CandleSeries,
    h1_window: CandleSeries,
):
    """Build MultiTimeframeContext from sliced higher-TF series."""
    from datetime import timezone
    from strategy.domain.value_objects import MultiTimeframeContext
    from strategy.infrastructure.multi_timeframe_analyzer import _analyze_trend

    d1_slice = _slice_before(d1_candles, bar_time)
    h4_slice = _slice_before(h4_candles, bar_time)

    d1_analysis = _analyze_trend(d1_slice) if d1_slice else _analyze_trend(h1_window)
    h4_analysis = _analyze_trend(h4_slice) if h4_slice else _analyze_trend(h1_window)
    h1_analysis = _analyze_trend(h1_window)

    tz = bar_time.tzinfo or timezone.utc
    return MultiTimeframeContext(
        symbol=symbol,
        analysis_time=bar_time.replace(tzinfo=tz),
        d1=d1_analysis,
        h4=h4_analysis,
        h1=h1_analysis,
    )
